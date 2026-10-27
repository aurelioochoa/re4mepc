/* Host display quality for the engine's GL context: supersampling, optional
 * horizontal widescreen and texture filtering. The engine keeps its logical
 * 800x480 coordinates; only the host's GL state is mapped. Both the native
 * import bridge and the Python GL path call these, so they cannot diverge.
 * Only the emulation thread calls them; presentation replays captured state.
 */
#define GL_GLEXT_PROTOTYPES
#include <GL/gl.h>
#include <GL/glext.h>
#include <math.h>
#include <string.h>

#ifndef GL_TEXTURE_MAX_ANISOTROPY
#define GL_TEXTURE_MAX_ANISOTROPY 0x84FE
#endif

static struct {
    int scale, logical_w, logical_h, surface_w, filtering;
    float anisotropy;
    GLenum matrix_mode;
    int perspective;
    GLint viewport[4], scissor[4];
} d = {1, 800, 480, 800, 0, 1.0f, GL_MODELVIEW, 0, {0, 0, 800, 480}, {0, 0, 800, 480}};

/* Map a logical rectangle to the host surface. Full-width rectangles extend
 * into widescreen margins when `wide`; others stay centered on the 5:3 area. */
void re4_display_map(int wide, const int in[4], int out[4]) {
    int margin = (d.surface_w - d.logical_w) / 2;
    int full = in[0] <= 0 && in[0] + in[2] >= d.logical_w - 1;
    out[0] = (wide && full ? in[0] : in[0] + margin) * d.scale;
    out[1] = in[1] * d.scale;
    out[2] = (wide && full ? in[2] + 2 * margin : in[2]) * d.scale;
    out[3] = in[3] * d.scale;
}
static void apply_viewport(void) {
    int out[4]; re4_display_map(d.perspective, d.viewport, out);
    glViewport(out[0], out[1], out[2], out[3]);
}
void re4_display_configure(int scale, int logical_w, int logical_h, int surface_w,
                           int filtering, float anisotropy) {
    d.scale = scale > 0 ? scale : 1;
    d.logical_w = logical_w; d.logical_h = logical_h;
    d.surface_w = surface_w >= logical_w ? surface_w : logical_w;
    d.filtering = filtering; d.anisotropy = anisotropy >= 1 ? anisotropy : 1;
    d.matrix_mode = GL_MODELVIEW; d.perspective = 0;
    d.viewport[0] = d.viewport[1] = d.scissor[0] = d.scissor[1] = 0;
    d.viewport[2] = d.scissor[2] = logical_w; d.viewport[3] = d.scissor[3] = logical_h;
}
void re4_display_viewport(int x, int y, int w, int h) {
    d.viewport[0] = x; d.viewport[1] = y; d.viewport[2] = w; d.viewport[3] = h;
    apply_viewport();
}
void re4_display_scissor(int x, int y, int w, int h) {
    /* A scissor only restricts. Full-width boxes always cover the margins so
     * clears reach them whatever projection the previous frame left bound. */
    int in[4] = {x, y, w, h}, out[4];
    memcpy(d.scissor, in, sizeof(in));
    re4_display_map(1, in, out);
    glScissor(out[0], out[1], out[2], out[3]);
}
void re4_display_matrix_mode(unsigned mode) {
    d.matrix_mode = mode;
    glMatrixMode(mode);
}
/* Returns 1 for a perspective projection, which widescreen widens. */
int re4_display_projection(const float *m, float *out) {
    memcpy(out, m, 16 * sizeof(float));
    int perspective = fabsf(m[11] + 1) < 1e-3f && fabsf(m[15]) < 1e-3f;
    if (perspective && d.surface_w != d.logical_w)
        out[0] = m[0] * (float)d.logical_w / (float)d.surface_w;
    return perspective;
}
void re4_display_load_matrix(const float *m) {
    if (d.matrix_mode != GL_PROJECTION || d.surface_w == d.logical_w) { glLoadMatrixf(m); return; }
    float adjusted[16];
    int perspective = re4_display_projection(m, adjusted);
    glLoadMatrixf(adjusted);
    if (perspective != d.perspective) { d.perspective = perspective; apply_viewport(); }
}
/* 0: engine filters; 1: trilinear; 2: trilinear and anisotropic. Uploads
 * generate mipmaps whenever this is nonzero, so textures stay complete. */
void re4_display_tex_parameter(unsigned target, unsigned name, float value) {
    if (d.filtering && name == GL_TEXTURE_MIN_FILTER) {
        glTexParameteri(target, name, GL_LINEAR_MIPMAP_LINEAR);
        if (d.filtering > 1) glTexParameterf(target, GL_TEXTURE_MAX_ANISOTROPY, d.anisotropy);
    } else if (d.filtering && name == GL_TEXTURE_MAG_FILTER) glTexParameteri(target, name, GL_LINEAR);
    else glTexParameterf(target, name, value);
}
int re4_display_filtering(void) { return d.filtering; }

/* Widescreen: untextured orthographic draws covering the whole logical screen
 * (fades, story and loading covers) extend over the margins. Textured art stays
 * 5:3 so title and menu images are never distorted. Returns 1 when the caller
 * must call re4_display_cover_end() after submitting the draw. */
static GLint saved_viewport[4];
int re4_display_cover(int first, int count, unsigned index_type, const void *indices) {
    if (d.surface_w == d.logical_w || d.perspective || count < 3 || count > 6) return 0;
    if (glIsEnabled(GL_TEXTURE_2D) || !glIsEnabled(GL_VERTEX_ARRAY)) return 0;
    GLint buffer, size, type, stride; void *pointer = NULL;
    glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &buffer);
    if (index_type) { GLint elements; glGetIntegerv(GL_ELEMENT_ARRAY_BUFFER_BINDING, &elements); if (elements) return 0; }
    glGetIntegerv(GL_VERTEX_ARRAY_SIZE, &size); glGetIntegerv(GL_VERTEX_ARRAY_TYPE, &type);
    glGetIntegerv(GL_VERTEX_ARRAY_STRIDE, &stride); glGetPointerv(GL_VERTEX_ARRAY_POINTER, &pointer);
    if (buffer || !pointer || type != GL_FLOAT || size < 2 || (index_type && !indices)) return 0;
    GLfloat model[16], projection[16];
    glGetFloatv(GL_MODELVIEW_MATRIX, model); glGetFloatv(GL_PROJECTION_MATRIX, projection);
    size_t step = stride ? (size_t)stride : (size_t)size * sizeof(float);
    float low[2] = {2, 2}, high[2] = {-2, -2};
    for (int i = 0; i < count; ++i) {
        unsigned index = (unsigned)(first + i);
        if (index_type == GL_UNSIGNED_SHORT) index = ((const GLushort *)indices)[i];
        else if (index_type == GL_UNSIGNED_BYTE) index = ((const GLubyte *)indices)[i];
        else if (index_type == GL_UNSIGNED_INT) index = ((const GLuint *)indices)[i];
        else if (index_type) return 0;
        if (index > 64) return 0;
        float v[4] = {0, 0, 0, 1}, eye[4], clip[4];
        memcpy(v, (const unsigned char *)pointer + index * step, (size_t)(size < 4 ? size : 4) * sizeof(float));
        for (int r = 0; r < 4; ++r) eye[r] = model[r]*v[0] + model[4+r]*v[1] + model[8+r]*v[2] + model[12+r]*v[3];
        for (int r = 0; r < 4; ++r) clip[r] = projection[r]*eye[0] + projection[4+r]*eye[1] + projection[8+r]*eye[2] + projection[12+r]*eye[3];
        if (!(fabsf(clip[3]) > 1e-6f)) return 0;
        for (int axis = 0; axis < 2; ++axis) {
            float ndc = clip[axis] / clip[3];
            if (ndc < low[axis]) low[axis] = ndc;
            if (ndc > high[axis]) high[axis] = ndc;
        }
    }
    if (low[0] > -0.99f || high[0] < 0.99f || low[1] > -0.99f || high[1] < 0.99f) return 0;
    int out[4]; re4_display_map(1, d.viewport, out);
    glGetIntegerv(GL_VIEWPORT, saved_viewport);
    glViewport(out[0], out[1], out[2], out[3]);
    return 1;
}
void re4_display_cover_end(void) {
    glViewport(saved_viewport[0], saved_viewport[1], saved_viewport[2], saved_viewport[3]);
}
