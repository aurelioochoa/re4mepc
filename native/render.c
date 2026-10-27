/* Host-owned fixed-function draw snapshots. Never invokes or writes the guest.
 * GLES1 client arrays are copied before the engine reuses their backing memory.
 * Replays preserve driver state and interpolate only matching draw identities.
 */
#define GL_GLEXT_PROTOTYPES
#include <GL/gl.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <pthread.h>

#define UNITS 8
#define MAX_COMMANDS 2048
#define MAX_BYTES (32u * 1024u * 1024u)
#define MAX_VERTICES 65536

static const GLenum caps[] = {GL_DEPTH_TEST, GL_ALPHA_TEST, GL_BLEND,
    GL_CULL_FACE, GL_SCISSOR_TEST, GL_FOG, GL_LIGHTING, GL_COLOR_MATERIAL,
    GL_NORMALIZE, GL_RESCALE_NORMAL, GL_DITHER, GL_STENCIL_TEST,
    GL_POLYGON_OFFSET_FILL, GL_LINE_SMOOTH, GL_POINT_SMOOTH};
#define CAPS (sizeof(caps)/sizeof(caps[0]))

struct array {
    GLint components, type, stride;
    uintptr_t identity;
    size_t bytes;
    unsigned char *data, *mixed;
    GLboolean enabled;
};
struct texture {
    GLint binding, env;
    GLboolean enabled;
    GLfloat matrix[16], color[4];
    GLint combine_rgb, combine_alpha, source_rgb[3], source_alpha[3];
    GLint operand_rgb[3], operand_alpha[3], rgb_scale, alpha_scale;
};
struct light {
    GLboolean enabled;
    GLfloat ambient[4], diffuse[4], specular[4], position[4], direction[3];
    GLfloat exponent, cutoff, attenuation[3];
};
struct material { GLfloat ambient[4], diffuse[4], specular[4], emission[4], shininess; };
struct state {
    GLfloat model[16], projection[16], color[4], normal[3];
    GLboolean enabled[CAPS], color_mask[4], depth_mask;
    GLint viewport[4], scissor[4], depth_func, blend_src, blend_dst;
    GLint alpha_func, cull, front, shade, stencil_func, stencil_ref;
    GLint stencil_value_mask, stencil_write_mask, stencil_fail, stencil_zfail, stencil_zpass;
    GLint color_material_face, color_material_parameter;
    GLfloat depth_range[2], alpha_ref, polygon_factor, polygon_units, line_width, point_size;
    GLfloat fog_color[4], fog_density, fog_start, fog_end;
    GLint fog_mode, light_two_side, light_local_viewer;
    GLfloat light_ambient[4];
    struct material material[2];
    struct light lights[8];
    struct texture textures[UNITS];
};
struct command {
    int clear;
    int previous, pass;
    GLbitfield mask, pass_mask;
    GLfloat clear_color[4], clear_depth;
    GLint clear_stencil;
    struct state state;
    GLenum mode, index_type;
    GLint first;
    GLsizei count, vertices;
    unsigned char *indices;
    size_t index_bytes;
    struct array vertex, normal, color, uv[UNITS];
};
struct frame { struct command *commands; size_t count, bytes; int valid; GLsync fence; };
struct pixels { GLuint texture; GLsync written, read; int width, height; };
struct renderer {
    struct frame previous, current, next;
    int recording, units, lights, sync_supported;
    uint64_t captures, replays, interpolated, resets, rejected;
    uint64_t matched_draws, unmatched_draws, changed_sequences;
    pthread_mutex_t mutex;
    struct pixels pixels[3]; int published;
    GLsync consumed;
};

static void match_history(struct renderer *r);

static void release_array(struct array *a) { free(a->data); free(a->mixed); }
static void release_frame(struct frame *f) {
    if (f->fence) glDeleteSync(f->fence);
    for (size_t i=0; i<f->count; ++i) {
        struct command *c=&f->commands[i];
        release_array(&c->vertex); release_array(&c->normal); release_array(&c->color);
        for (int j=0; j<UNITS; ++j) release_array(&c->uv[j]);
        free(c->indices);
    }
    free(f->commands); memset(f,0,sizeof(*f));
}
void *re4_render_open(void) {
    struct renderer *r=calloc(1,sizeof(*r));
    if (!r) return NULL;
    r->published=-1;
    if (pthread_mutex_init(&r->mutex,NULL)) { free(r); return NULL; }
    glGetIntegerv(GL_MAX_TEXTURE_UNITS,&r->units);
    glGetIntegerv(GL_MAX_LIGHTS,&r->lights);
    const char *extensions=(const char *)glGetString(GL_EXTENSIONS);
    r->sync_supported=extensions && strstr(extensions,"GL_ARB_sync");
    if (r->units<1 || r->units>UNITS || r->lights<0 || r->lights>8) { pthread_mutex_destroy(&r->mutex); free(r); return NULL; }
    return r;
}
void re4_render_reset(void *handle) {
    struct renderer *r=handle;
    pthread_mutex_lock(&r->mutex);
    if (r->consumed) { glWaitSync(r->consumed,0,GL_TIMEOUT_IGNORED); glDeleteSync(r->consumed); r->consumed=NULL; }
    release_frame(&r->previous); release_frame(&r->current);
    r->next.valid=0; ++r->resets;
    pthread_mutex_unlock(&r->mutex);
}
void re4_render_begin(void *handle) {
    struct renderer *r=handle;
    release_frame(&r->next); r->next.valid=1; r->recording=1;
}
void re4_render_dirty(void *handle) {
    re4_render_reset(handle);
}
void re4_render_publish(void *handle, int width, int height) {
    struct renderer *r=handle;
    pthread_mutex_lock(&r->mutex);
    int index=(r->published+1)%3;
    struct pixels *p=&r->pixels[index];
    if (p->read) { glWaitSync(p->read,0,GL_TIMEOUT_IGNORED); glDeleteSync(p->read); p->read=NULL; }
    if (p->written) { glDeleteSync(p->written); p->written=NULL; }
    glPushAttrib(GL_TEXTURE_BIT|GL_PIXEL_MODE_BIT);
    if (!p->texture) glGenTextures(1,&p->texture);
    glBindTexture(GL_TEXTURE_2D,p->texture);
    if (p->width!=width || p->height!=height) {
        glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,width,height,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
        p->width=width; p->height=height;
    }
    glReadBuffer(GL_COLOR_ATTACHMENT0);
    glCopyTexSubImage2D(GL_TEXTURE_2D,0,0,0,0,0,width,height);
    glPopAttrib();
    if (r->sync_supported) { p->written=glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE,0); glFlush(); }
    else glFinish();
    r->published=index;
    pthread_mutex_unlock(&r->mutex);
}
int re4_render_blit(void *handle, unsigned read_framebuffer) {
    struct renderer *r=handle;
    pthread_mutex_lock(&r->mutex);
    if (r->published<0) { pthread_mutex_unlock(&r->mutex); return 0; }
    struct pixels *p=&r->pixels[r->published];
    if (p->written) glWaitSync(p->written,0,GL_TIMEOUT_IGNORED);
    GLint read_binding; glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&read_binding);
    glPushAttrib(GL_ALL_ATTRIB_BITS);
    glBindFramebuffer(GL_READ_FRAMEBUFFER,read_framebuffer);
    glFramebufferTexture2D(GL_READ_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,p->texture,0);
    glReadBuffer(GL_COLOR_ATTACHMENT0); glDrawBuffer(GL_COLOR_ATTACHMENT0);
    glDisable(GL_SCISSOR_TEST); glColorMask(1,1,1,1);
    glBlitFramebuffer(0,0,p->width,p->height,0,0,p->width,p->height,GL_COLOR_BUFFER_BIT,GL_NEAREST);
    glBindFramebuffer(GL_READ_FRAMEBUFFER,read_binding); glPopAttrib();
    if (p->read) glDeleteSync(p->read);
    if (r->sync_supported) { p->read=glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE,0); glFlush(); }
    else glFinish();
    pthread_mutex_unlock(&r->mutex);
    return 1;
}
static struct command *append(struct renderer *r) {
    if (!r->recording || !r->next.valid) return NULL;
    if (r->next.count>=MAX_COMMANDS) { r->next.valid=0; return NULL; }
    void *p=realloc(r->next.commands,(r->next.count+1)*sizeof(struct command));
    if (!p) { r->next.valid=0; return NULL; }
    r->next.commands=p;
    struct command *c=&r->next.commands[r->next.count++];
    memset(c,0,sizeof(*c));
    return c;
}
static void capture_masks(struct state *s) {
    glGetIntegerv(GL_VIEWPORT,s->viewport); glGetIntegerv(GL_SCISSOR_BOX,s->scissor);
    glGetBooleanv(GL_COLOR_WRITEMASK,s->color_mask); glGetBooleanv(GL_DEPTH_WRITEMASK,&s->depth_mask);
    for (size_t i=0; i<CAPS; ++i) s->enabled[i]=glIsEnabled(caps[i]);
    glGetIntegerv(GL_STENCIL_WRITEMASK,&s->stencil_write_mask);
}
void re4_render_clear(void *handle, unsigned mask) {
    struct renderer *r=handle;
    struct command *c=append(r);
    if (!c) return;
    c->clear=1; c->mask=mask; capture_masks(&c->state);
    glGetFloatv(GL_COLOR_CLEAR_VALUE,c->clear_color);
    glGetFloatv(GL_DEPTH_CLEAR_VALUE,&c->clear_depth);
    glGetIntegerv(GL_STENCIL_CLEAR_VALUE,&c->clear_stencil);
}
static void capture_state(struct renderer *r, struct state *s) {
    capture_masks(s);
    glGetFloatv(GL_MODELVIEW_MATRIX,s->model); glGetFloatv(GL_PROJECTION_MATRIX,s->projection);
    glGetFloatv(GL_CURRENT_COLOR,s->color); glGetFloatv(GL_CURRENT_NORMAL,s->normal);
    glGetIntegerv(GL_DEPTH_FUNC,&s->depth_func); glGetFloatv(GL_DEPTH_RANGE,s->depth_range);
    glGetIntegerv(GL_BLEND_SRC,&s->blend_src); glGetIntegerv(GL_BLEND_DST,&s->blend_dst);
    glGetIntegerv(GL_ALPHA_TEST_FUNC,&s->alpha_func); glGetFloatv(GL_ALPHA_TEST_REF,&s->alpha_ref);
    glGetIntegerv(GL_CULL_FACE_MODE,&s->cull); glGetIntegerv(GL_FRONT_FACE,&s->front);
    glGetIntegerv(GL_SHADE_MODEL,&s->shade);
    glGetFloatv(GL_POLYGON_OFFSET_FACTOR,&s->polygon_factor); glGetFloatv(GL_POLYGON_OFFSET_UNITS,&s->polygon_units);
    glGetFloatv(GL_LINE_WIDTH,&s->line_width); glGetFloatv(GL_POINT_SIZE,&s->point_size);
    glGetIntegerv(GL_STENCIL_FUNC,&s->stencil_func); glGetIntegerv(GL_STENCIL_REF,&s->stencil_ref);
    glGetIntegerv(GL_STENCIL_VALUE_MASK,&s->stencil_value_mask); glGetIntegerv(GL_STENCIL_FAIL,&s->stencil_fail);
    glGetIntegerv(GL_STENCIL_PASS_DEPTH_FAIL,&s->stencil_zfail); glGetIntegerv(GL_STENCIL_PASS_DEPTH_PASS,&s->stencil_zpass);
    if (glIsEnabled(GL_FOG)) {
        glGetIntegerv(GL_FOG_MODE,&s->fog_mode); glGetFloatv(GL_FOG_COLOR,s->fog_color);
        glGetFloatv(GL_FOG_DENSITY,&s->fog_density); glGetFloatv(GL_FOG_START,&s->fog_start); glGetFloatv(GL_FOG_END,&s->fog_end);
    }
    if (glIsEnabled(GL_LIGHTING)) {
        glGetFloatv(GL_LIGHT_MODEL_AMBIENT,s->light_ambient);
        glGetIntegerv(GL_LIGHT_MODEL_TWO_SIDE,&s->light_two_side);
        glGetIntegerv(GL_LIGHT_MODEL_LOCAL_VIEWER,&s->light_local_viewer);
        glGetIntegerv(GL_COLOR_MATERIAL_FACE,&s->color_material_face);
        glGetIntegerv(GL_COLOR_MATERIAL_PARAMETER,&s->color_material_parameter);
        for (int i=0; i<2; ++i) {
            GLenum face=i?GL_BACK:GL_FRONT;
            struct material *m=&s->material[i];
            glGetMaterialfv(face,GL_AMBIENT,m->ambient); glGetMaterialfv(face,GL_DIFFUSE,m->diffuse);
            glGetMaterialfv(face,GL_SPECULAR,m->specular); glGetMaterialfv(face,GL_EMISSION,m->emission);
            glGetMaterialfv(face,GL_SHININESS,&m->shininess);
        }
        for (int i=0; i<r->lights; ++i) {
            struct light *l=&s->lights[i]; GLenum light=GL_LIGHT0+i;
            if (!(l->enabled=glIsEnabled(light))) continue;
            glGetLightfv(light,GL_AMBIENT,l->ambient); glGetLightfv(light,GL_DIFFUSE,l->diffuse);
            glGetLightfv(light,GL_SPECULAR,l->specular); glGetLightfv(light,GL_POSITION,l->position);
            glGetLightfv(light,GL_SPOT_DIRECTION,l->direction); glGetLightfv(light,GL_SPOT_EXPONENT,&l->exponent);
            glGetLightfv(light,GL_SPOT_CUTOFF,&l->cutoff);
            glGetLightfv(light,GL_CONSTANT_ATTENUATION,&l->attenuation[0]);
            glGetLightfv(light,GL_LINEAR_ATTENUATION,&l->attenuation[1]);
            glGetLightfv(light,GL_QUADRATIC_ATTENUATION,&l->attenuation[2]);
        }
    }
    GLint active; glGetIntegerv(GL_ACTIVE_TEXTURE,&active);
    for (int i=0; i<r->units; ++i) {
        struct texture *t=&s->textures[i];
        glActiveTexture(GL_TEXTURE0+i); t->enabled=glIsEnabled(GL_TEXTURE_2D);
        glGetIntegerv(GL_TEXTURE_BINDING_2D,&t->binding); glGetFloatv(GL_TEXTURE_MATRIX,t->matrix);
        glGetTexEnviv(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,&t->env);
        glGetTexEnvfv(GL_TEXTURE_ENV,GL_TEXTURE_ENV_COLOR,t->color);
        if (t->env==GL_COMBINE) {
            glGetTexEnviv(GL_TEXTURE_ENV,GL_COMBINE_RGB,&t->combine_rgb);
            glGetTexEnviv(GL_TEXTURE_ENV,GL_COMBINE_ALPHA,&t->combine_alpha);
            glGetTexEnviv(GL_TEXTURE_ENV,GL_RGB_SCALE,&t->rgb_scale);
            glGetTexEnviv(GL_TEXTURE_ENV,GL_ALPHA_SCALE,&t->alpha_scale);
            for (int j=0; j<3; ++j) {
                glGetTexEnviv(GL_TEXTURE_ENV,GL_SOURCE0_RGB+j,&t->source_rgb[j]);
                glGetTexEnviv(GL_TEXTURE_ENV,GL_SOURCE0_ALPHA+j,&t->source_alpha[j]);
                glGetTexEnviv(GL_TEXTURE_ENV,GL_OPERAND0_RGB+j,&t->operand_rgb[j]);
                glGetTexEnviv(GL_TEXTURE_ENV,GL_OPERAND0_ALPHA+j,&t->operand_alpha[j]);
            }
        }
    }
    glActiveTexture(active);
}
static size_t type_bytes(GLenum type) {
    switch (type) {
    case GL_BYTE: case GL_UNSIGNED_BYTE: return 1;
    case GL_SHORT: case GL_UNSIGNED_SHORT: return 2;
    case GL_FLOAT: case GL_INT: case GL_UNSIGNED_INT: return 4;
    case GL_DOUBLE: return 8;
    default: return 0;
    }
}
static int copy_array(struct renderer *r, struct array *a, GLenum enabled,
                      GLenum size, GLenum type, GLenum stride, GLenum pointer, unsigned vertices) {
    if (!(a->enabled=glIsEnabled(enabled))) return 1;
    a->components=3;
    if (size) glGetIntegerv(size,&a->components);
    glGetIntegerv(type,&a->type); glGetIntegerv(stride,&a->stride);
    void *p=NULL; glGetPointerv(pointer,&p); a->identity=(uintptr_t)p;
    size_t width=type_bytes(a->type)*a->components;
    size_t step=a->stride?(size_t)a->stride:width;
    if (!p || a->components<1 || a->components>4 || !width || step<width) return 0;
    a->bytes=(vertices-1)*step+width;
    if (a->bytes>MAX_BYTES/2 || r->next.bytes>MAX_BYTES-a->bytes*2) return 0;
    a->data=malloc(a->bytes); a->mixed=malloc(a->bytes);
    if (!a->data || !a->mixed) return 0;
    memcpy(a->data,p,a->bytes); r->next.bytes+=a->bytes*2;
    return 1;
}
void re4_render_draw(void *handle, unsigned mode, int first, int count, unsigned index_type, const void *indices) {
    struct renderer *r=handle;
    if (count<=0) return;
    struct command *c=append(r);
    if (!c) return;
    c->mode=mode; c->first=first; c->count=count; c->index_type=index_type;
    GLint buffer; glGetIntegerv(GL_ARRAY_BUFFER_BINDING,&buffer);
    if (buffer || first<0 || count>MAX_VERTICES) goto invalid;
    unsigned vertices=(unsigned)first+count;
    if (index_type) {
        glGetIntegerv(GL_ELEMENT_ARRAY_BUFFER_BINDING,&buffer);
        if (buffer || !indices || (index_type!=GL_UNSIGNED_BYTE && index_type!=GL_UNSIGNED_SHORT && index_type!=GL_UNSIGNED_INT)) goto invalid;
        c->index_bytes=(size_t)count*type_bytes(index_type);
        c->indices=malloc(c->index_bytes);
        if (!c->indices) goto invalid;
        memcpy(c->indices,indices,c->index_bytes); vertices=0;
        for (int i=0; i<count; ++i) {
            uint32_t value=0;
            memcpy(&value,c->indices+i*type_bytes(index_type),type_bytes(index_type));
            if (value>=MAX_VERTICES) goto invalid;
            if (value+1>vertices) vertices=value+1;
        }
    }
    if (!vertices || vertices>MAX_VERTICES) goto invalid;
    c->vertices=vertices;
    capture_state(r,&c->state);
    if (!copy_array(r,&c->vertex,GL_VERTEX_ARRAY,GL_VERTEX_ARRAY_SIZE,GL_VERTEX_ARRAY_TYPE,GL_VERTEX_ARRAY_STRIDE,GL_VERTEX_ARRAY_POINTER,vertices) ||
        !copy_array(r,&c->normal,GL_NORMAL_ARRAY,0,GL_NORMAL_ARRAY_TYPE,GL_NORMAL_ARRAY_STRIDE,GL_NORMAL_ARRAY_POINTER,vertices) ||
        !copy_array(r,&c->color,GL_COLOR_ARRAY,GL_COLOR_ARRAY_SIZE,GL_COLOR_ARRAY_TYPE,GL_COLOR_ARRAY_STRIDE,GL_COLOR_ARRAY_POINTER,vertices)) goto invalid;
    GLint active; glGetIntegerv(GL_CLIENT_ACTIVE_TEXTURE,&active);
    int good=1;
    for (int i=0; i<r->units; ++i) {
        glClientActiveTexture(GL_TEXTURE0+i);
        if (!copy_array(r,&c->uv[i],GL_TEXTURE_COORD_ARRAY,GL_TEXTURE_COORD_ARRAY_SIZE,GL_TEXTURE_COORD_ARRAY_TYPE,GL_TEXTURE_COORD_ARRAY_STRIDE,GL_TEXTURE_COORD_ARRAY_POINTER,vertices)) good=0;
    }
    glClientActiveTexture(active);
    if (!good || !c->vertex.enabled) goto invalid;
    ++r->captures;
    return;
invalid:
    r->next.valid=0; ++r->rejected;
}
void re4_render_end(void *handle, int eligible) {
    struct renderer *r=handle; r->recording=0;
    pthread_mutex_lock(&r->mutex);
    release_frame(&r->previous);
    if (!eligible || !r->next.valid || !r->next.count || !r->next.commands[0].clear) {
        release_frame(&r->current); release_frame(&r->next); ++r->resets;
        pthread_mutex_unlock(&r->mutex); return;
    }
    if (r->sync_supported) { r->next.fence=glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE,0); glFlush(); }
    else glFinish();
    r->previous=r->current; r->current=r->next; memset(&r->next,0,sizeof(r->next));
    match_history(r);
    pthread_mutex_unlock(&r->mutex);
}
static void enable(GLenum cap, GLboolean value) { if (value) glEnable(cap); else glDisable(cap); }
static void client_enable(GLenum cap, GLboolean value) { if (value) glEnableClientState(cap); else glDisableClientState(cap); }
static void masks(const struct state *s) {
    glViewport(s->viewport[0],s->viewport[1],s->viewport[2],s->viewport[3]);
    glScissor(s->scissor[0],s->scissor[1],s->scissor[2],s->scissor[3]);
    for (size_t i=0; i<CAPS; ++i) enable(caps[i],s->enabled[i]);
    glColorMask(s->color_mask[0],s->color_mask[1],s->color_mask[2],s->color_mask[3]);
    glDepthMask(s->depth_mask); glStencilMask(s->stencil_write_mask);
}
static void mix(float *out, const float *a, const float *b, unsigned count, float alpha) {
    for (unsigned i=0; i<count; ++i) out[i]=a[i]+(b[i]-a[i])*alpha;
}
static void apply_state(struct renderer *r, const struct state *s, const struct state *old, float alpha) {
    GLfloat matrix[16];
    masks(s);
    glDepthFunc(s->depth_func); glDepthRange(s->depth_range[0],s->depth_range[1]);
    glBlendFunc(s->blend_src,s->blend_dst); glAlphaFunc(s->alpha_func,s->alpha_ref);
    glCullFace(s->cull); glFrontFace(s->front); glShadeModel(s->shade);
    glPolygonOffset(s->polygon_factor,s->polygon_units); glLineWidth(s->line_width); glPointSize(s->point_size);
    glStencilFunc(s->stencil_func,s->stencil_ref,s->stencil_value_mask);
    glStencilOp(s->stencil_fail,s->stencil_zfail,s->stencil_zpass);
    if (glIsEnabled(GL_FOG)) {
        glFogi(GL_FOG_MODE,s->fog_mode); glFogfv(GL_FOG_COLOR,s->fog_color);
        glFogf(GL_FOG_DENSITY,s->fog_density); glFogf(GL_FOG_START,s->fog_start); glFogf(GL_FOG_END,s->fog_end);
    }
    glMatrixMode(GL_MODELVIEW); glLoadIdentity();
    if (glIsEnabled(GL_LIGHTING)) {
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT,s->light_ambient);
        glLightModeli(GL_LIGHT_MODEL_TWO_SIDE,s->light_two_side);
        glLightModeli(GL_LIGHT_MODEL_LOCAL_VIEWER,s->light_local_viewer);
        /* Positions and spot directions returned by GL are already in eye space. */
        for (int i=0; i<r->lights; ++i) {
            const struct light *l=&s->lights[i]; GLenum light=GL_LIGHT0+i;
            enable(light,l->enabled); if (!l->enabled) continue;
            glLightfv(light,GL_AMBIENT,l->ambient); glLightfv(light,GL_DIFFUSE,l->diffuse);
            glLightfv(light,GL_SPECULAR,l->specular); glLightfv(light,GL_POSITION,l->position);
            glLightfv(light,GL_SPOT_DIRECTION,l->direction); glLightf(light,GL_SPOT_EXPONENT,l->exponent);
            glLightf(light,GL_SPOT_CUTOFF,l->cutoff); glLightf(light,GL_CONSTANT_ATTENUATION,l->attenuation[0]);
            glLightf(light,GL_LINEAR_ATTENUATION,l->attenuation[1]); glLightf(light,GL_QUADRATIC_ATTENUATION,l->attenuation[2]);
        }
        glDisable(GL_COLOR_MATERIAL);
        for (int i=0; i<2; ++i) {
            GLenum face=i?GL_BACK:GL_FRONT; const struct material *m=&s->material[i];
            glMaterialfv(face,GL_AMBIENT,m->ambient); glMaterialfv(face,GL_DIFFUSE,m->diffuse);
            glMaterialfv(face,GL_SPECULAR,m->specular); glMaterialfv(face,GL_EMISSION,m->emission);
            glMaterialf(face,GL_SHININESS,m->shininess);
        }
        glColorMaterial(s->color_material_face,s->color_material_parameter);
        enable(GL_COLOR_MATERIAL,s->enabled[7]);
    }
    glMatrixMode(GL_PROJECTION); glLoadMatrixf(s->projection);
    glMatrixMode(GL_MODELVIEW);
    if (old && alpha<=0) glLoadMatrixf(old->model);
    else if (old && alpha<1) { mix(matrix,old->model,s->model,16,alpha); glLoadMatrixf(matrix); }
    else glLoadMatrixf(s->model);
    glColor4fv(s->color); glNormal3fv(s->normal);
    for (int i=0; i<r->units; ++i) {
        const struct texture *t=&s->textures[i]; glActiveTexture(GL_TEXTURE0+i);
        enable(GL_TEXTURE_2D,t->enabled); glBindTexture(GL_TEXTURE_2D,t->binding);
        glMatrixMode(GL_TEXTURE); glLoadMatrixf(t->matrix);
        glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,t->env);
        glTexEnvfv(GL_TEXTURE_ENV,GL_TEXTURE_ENV_COLOR,t->color);
        if (t->env==GL_COMBINE) {
            glTexEnvi(GL_TEXTURE_ENV,GL_COMBINE_RGB,t->combine_rgb);
            glTexEnvi(GL_TEXTURE_ENV,GL_COMBINE_ALPHA,t->combine_alpha);
            glTexEnvi(GL_TEXTURE_ENV,GL_RGB_SCALE,t->rgb_scale); glTexEnvi(GL_TEXTURE_ENV,GL_ALPHA_SCALE,t->alpha_scale);
            for (int j=0; j<3; ++j) {
                glTexEnvi(GL_TEXTURE_ENV,GL_SOURCE0_RGB+j,t->source_rgb[j]);
                glTexEnvi(GL_TEXTURE_ENV,GL_SOURCE0_ALPHA+j,t->source_alpha[j]);
                glTexEnvi(GL_TEXTURE_ENV,GL_OPERAND0_RGB+j,t->operand_rgb[j]);
                glTexEnvi(GL_TEXTURE_ENV,GL_OPERAND0_ALPHA+j,t->operand_alpha[j]);
            }
        }
    }
}
static int same_array(const struct array *a, const struct array *b, int content) {
    if (a->enabled!=b->enabled) return 0;
    if (!a->enabled) return 1;
    if (a->identity!=b->identity || a->components!=b->components || a->type!=b->type || a->stride!=b->stride || a->bytes!=b->bytes) return 0;
    if (content) {
        size_t width=type_bytes(a->type)*a->components, step=a->stride?(size_t)a->stride:width;
        for (size_t offset=0; offset+width<=a->bytes; offset+=step)
            if (memcmp(a->data+offset,b->data+offset,width)) return 0;
    }
    return 1;
}
static int matching(struct renderer *r, const struct command *a, const struct command *b) {
    if (a->clear!=b->clear || a->mask!=b->mask) return 0;
    if (a->clear) return 1;
    if (a->mode!=b->mode || a->count!=b->count || a->first!=b->first || a->vertices!=b->vertices ||
        a->index_type!=b->index_type || a->index_bytes!=b->index_bytes ||
        (a->index_bytes && memcmp(a->indices,b->indices,a->index_bytes)) ||
        memcmp(a->state.projection,b->state.projection,sizeof(a->state.projection)) ||
        !same_array(&a->vertex,&b->vertex,0) || !same_array(&a->normal,&b->normal,0) || !same_array(&a->color,&b->color,1)) return 0;
    for (int i=0; i<r->units; ++i) {
        if (a->state.textures[i].binding!=b->state.textures[i].binding ||
            a->state.textures[i].enabled!=b->state.textures[i].enabled || !same_array(&a->uv[i],&b->uv[i],1)) return 0;
    }
    /* A camera cut/teleport must snap. Restrict interpolation to small affine
     * steps; perspective/orthographic projection changes already fail above. */
    float turn=0;
    for (int i=0; i<12; ++i) turn+=fabsf(a->state.model[i]-b->state.model[i]);
    if (turn>3) return 0;
    for (int i=12; i<15; ++i) if (fabsf(a->state.model[i]-b->state.model[i])>256) return 0;
    if (a->vertex.type==GL_FLOAT) {
        size_t width=a->vertex.components*sizeof(float), step=a->vertex.stride?(size_t)a->vertex.stride:width;
        for (int i=0; i<a->vertices; ++i) for (int j=0; j<a->vertex.components; ++j) {
            float x,y; size_t offset=i*step+j*sizeof(float);
            memcpy(&x,a->vertex.data+offset,sizeof(float)); memcpy(&y,b->vertex.data+offset,sizeof(float));
            if (!isfinite(x) || !isfinite(y) || fabsf(x-y)>256) return 0;
        }
    }
    return 1;
}
/* Visibility changes insert/remove draws during camera turns. Match surviving
 * geometry by its owned array identity instead of requiring identical command
 * counts/positions. Resolve once per tick, not at every display refresh.
 * Ambiguous instances snap; a previous draw can never feed two current draws.
 * Clear boundaries delimit passes so history cannot cross a render pass. */
static unsigned history_bucket(const struct command *c) {
    uintptr_t key=c->vertex.identity;
    key^=key>>17; key^=(uintptr_t)c->count*2654435761u;
    key^=(uintptr_t)c->pass*2246822519u;
    return (unsigned)key & (MAX_COMMANDS*2-1);
}
static void match_history(struct renderer *r) {
    int heads[MAX_COMMANDS*2], next[MAX_COMMANDS], owner[MAX_COMMANDS];
    for (size_t i=0; i<MAX_COMMANDS*2; ++i) heads[i]=-1;
    for (size_t i=0; i<MAX_COMMANDS; ++i) owner[i]=-1;
    int pass=0;
    GLbitfield pass_mask=0;
    for (size_t i=0; i<r->previous.count; ++i) {
        struct command *c=&r->previous.commands[i];
        if (c->clear) { ++pass; pass_mask=c->mask; continue; }
        c->pass=pass; c->pass_mask=pass_mask;
        unsigned bucket=history_bucket(c);
        next[i]=heads[bucket]; heads[bucket]=(int)i;
    }
    if (r->previous.valid && r->previous.count!=r->current.count) ++r->changed_sequences;
    pass=0; pass_mask=0;
    for (size_t i=0; i<r->current.count; ++i) {
        struct command *c=&r->current.commands[i]; c->previous=-1;
        if (c->clear) { ++pass; pass_mask=c->mask; continue; }
        c->pass=pass; c->pass_mask=pass_mask;
        int found=-1;
        if (r->previous.valid) for (int j=heads[history_bucket(c)]; j>=0; j=next[j]) {
            const struct command *p=&r->previous.commands[j];
            if (p->pass!=pass || p->pass_mask!=pass_mask || !matching(r,p,c)) continue;
            if (found>=0) { found=-1; break; }
            found=j;
        }
        if (found<0) continue;
        if (owner[found]!=-1) {
            if (owner[found]>=0) r->current.commands[owner[found]].previous=-1;
            owner[found]=-2;
        } else {
            c->previous=found; owner[found]=(int)i;
        }
    }
    for (size_t i=0; i<r->current.count; ++i) if (!r->current.commands[i].clear) {
        if (r->current.commands[i].previous>=0) ++r->matched_draws;
        else ++r->unmatched_draws;
    }
}
static const void *array_data(struct array *a, const struct array *old, int vertices, float alpha) {
    if (!old || a->type!=GL_FLOAT) return a->data;
    if (alpha<=0) return old->data;
    if (alpha>=1) return a->data;
    size_t width=a->components*sizeof(float), step=a->stride?(size_t)a->stride:width;
    memcpy(a->mixed,a->data,a->bytes);
    for (int i=0; i<vertices; ++i) {
        for (int j=0; j<a->components; ++j) {
            float x,y; size_t offset=i*step+j*sizeof(float);
            memcpy(&x,old->data+offset,sizeof(float)); memcpy(&y,a->data+offset,sizeof(float));
            y=x+(y-x)*alpha; memcpy(a->mixed+offset,&y,sizeof(float));
        }
    }
    return a->mixed;
}
int re4_render_present(void *handle, float alpha) {
    struct renderer *r=handle;
    pthread_mutex_lock(&r->mutex);
    if (!r->current.valid || !r->current.count) { pthread_mutex_unlock(&r->mutex); return 0; }
    if (r->current.fence) glWaitSync(r->current.fence,0,GL_TIMEOUT_IGNORED);
    alpha=fmaxf(0,fminf(1,alpha));
    int compatible=0;
    GLint active,client,mode;
    glGetIntegerv(GL_ACTIVE_TEXTURE,&active); glGetIntegerv(GL_CLIENT_ACTIVE_TEXTURE,&client); glGetIntegerv(GL_MATRIX_MODE,&mode);
    glPushAttrib(GL_ALL_ATTRIB_BITS); glPushClientAttrib(GL_CLIENT_ALL_ATTRIB_BITS);
    glMatrixMode(GL_MODELVIEW); glPushMatrix(); glMatrixMode(GL_PROJECTION); glPushMatrix();
    for (int i=0; i<r->units; ++i) { glActiveTexture(GL_TEXTURE0+i); glMatrixMode(GL_TEXTURE); glPushMatrix(); }
    for (size_t i=0; i<r->current.count; ++i) {
        struct command *c=&r->current.commands[i];
        const struct command *old=c->previous>=0?&r->previous.commands[c->previous]:NULL;
        if (c->clear) {
            masks(&c->state); glClearColor(c->clear_color[0],c->clear_color[1],c->clear_color[2],c->clear_color[3]);
            glClearDepth(c->clear_depth); glClearStencil(c->clear_stencil); glClear(c->mask); continue;
        }
        if (old) compatible=1;
        apply_state(r,&c->state,old?&old->state:NULL,alpha);
        client_enable(GL_VERTEX_ARRAY,c->vertex.enabled);
        glVertexPointer(c->vertex.components,c->vertex.type,c->vertex.stride,array_data(&c->vertex,old?&old->vertex:NULL,c->vertices,alpha));
        client_enable(GL_NORMAL_ARRAY,c->normal.enabled);
        if (c->normal.enabled) glNormalPointer(c->normal.type,c->normal.stride,array_data(&c->normal,old?&old->normal:NULL,c->vertices,alpha));
        client_enable(GL_COLOR_ARRAY,c->color.enabled);
        if (c->color.enabled) glColorPointer(c->color.components,c->color.type,c->color.stride,c->color.data);
        for (int j=0; j<r->units; ++j) {
            struct array *a=&c->uv[j]; glClientActiveTexture(GL_TEXTURE0+j); client_enable(GL_TEXTURE_COORD_ARRAY,a->enabled);
            if (a->enabled) glTexCoordPointer(a->components,a->type,a->stride,a->data);
        }
        if (c->index_type) glDrawElements(c->mode,c->count,c->index_type,c->indices);
        else glDrawArrays(c->mode,c->first,c->count);
    }
    for (int i=r->units-1; i>=0; --i) { glActiveTexture(GL_TEXTURE0+i); glMatrixMode(GL_TEXTURE); glPopMatrix(); }
    glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW); glPopMatrix();
    glPopClientAttrib(); glPopAttrib(); glActiveTexture(active); glClientActiveTexture(client); glMatrixMode(mode);
    ++r->replays;
    if (compatible && alpha>0 && alpha<1) ++r->interpolated;
    if (r->consumed) glDeleteSync(r->consumed);
    if (r->sync_supported) { r->consumed=glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE,0); glFlush(); }
    else glFinish();
    pthread_mutex_unlock(&r->mutex);
    return compatible?2:1;
}
uint64_t re4_render_measure(void *handle, unsigned key) {
    struct renderer *r=handle;
    uint64_t result=0;
    pthread_mutex_lock(&r->mutex);
    switch (key) {
    case 0:result=r->captures; break; case 1:result=r->replays; break; case 2:result=r->interpolated; break;
    case 3:result=r->resets; break; case 4:result=r->rejected; break;
    case 5:result=r->current.bytes+r->previous.bytes+r->next.bytes; break;
    case 6:result=r->current.valid && r->current.count; break;
    case 7:result=r->matched_draws; break; case 8:result=r->unmatched_draws; break;
    case 9:result=r->changed_sequences; break;
    }
    pthread_mutex_unlock(&r->mutex);
    return result;
}
void re4_render_close(void *handle) {
    struct renderer *r=handle;
    if (!r) return;
    release_frame(&r->previous); release_frame(&r->current); release_frame(&r->next);
    if (r->consumed) { glWaitSync(r->consumed,0,GL_TIMEOUT_IGNORED); glDeleteSync(r->consumed); }
    for (int i=0; i<3; ++i) {
        struct pixels *p=&r->pixels[i];
        if (p->read) { glWaitSync(p->read,0,GL_TIMEOUT_IGNORED); glDeleteSync(p->read); }
        if (p->written) glDeleteSync(p->written);
        if (p->texture) glDeleteTextures(1,&p->texture);
    }
    pthread_mutex_destroy(&r->mutex); free(r);
}
