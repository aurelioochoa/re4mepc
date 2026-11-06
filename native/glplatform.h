/* Desktop OpenGL headers and post-1.1 entry points on every host.
 *
 * Linux links libGL and declares extension prototypes directly. Windows'
 * opengl32 only exports OpenGL 1.1 and macOS headers hide newer entry points
 * from legacy contexts, so there the few newer functions resolve on first use
 * (wglGetProcAddress or dlsym) once a context is current.
 */
#ifndef RE4_GLPLATFORM_H
#define RE4_GLPLATFORM_H
#include <stdint.h>
#include <stddef.h>
#if defined(_WIN32)
#  define WIN32_LEAN_AND_MEAN
#  include <windows.h>
#  include <GL/gl.h>
#elif defined(__APPLE__)
#  define GL_SILENCE_DEPRECATION
#  include <OpenGL/gl.h>
#  include <dlfcn.h>
#else
#  define GL_GLEXT_PROTOTYPES
#  include <GL/gl.h>
#  include <GL/glext.h>
#endif

#if defined(_WIN32) || defined(__APPLE__)
#ifndef APIENTRY
#define APIENTRY
#endif
#define RE4_GL_RUNTIME 1
#ifndef GL_TEXTURE0
#define GL_TEXTURE0 0x84C0
#endif
#ifndef GL_ACTIVE_TEXTURE
#define GL_ACTIVE_TEXTURE 0x84E0
#endif
#ifndef GL_CLIENT_ACTIVE_TEXTURE
#define GL_CLIENT_ACTIVE_TEXTURE 0x84E1
#endif
#ifndef GL_MAX_TEXTURE_UNITS
#define GL_MAX_TEXTURE_UNITS 0x84E2
#endif
#ifndef GL_COMBINE
#define GL_COMBINE 0x8570
#endif
#ifndef GL_COMBINE_RGB
#define GL_COMBINE_RGB 0x8571
#endif
#ifndef GL_COMBINE_ALPHA
#define GL_COMBINE_ALPHA 0x8572
#endif
#ifndef GL_RGB_SCALE
#define GL_RGB_SCALE 0x8573
#endif
#ifndef GL_SOURCE0_RGB
#define GL_SOURCE0_RGB 0x8580
#endif
#ifndef GL_SOURCE0_ALPHA
#define GL_SOURCE0_ALPHA 0x8588
#endif
#ifndef GL_OPERAND0_RGB
#define GL_OPERAND0_RGB 0x8590
#endif
#ifndef GL_OPERAND0_ALPHA
#define GL_OPERAND0_ALPHA 0x8598
#endif
#ifndef GL_RESCALE_NORMAL
#define GL_RESCALE_NORMAL 0x803A
#endif
#ifndef GL_ARRAY_BUFFER_BINDING
#define GL_ARRAY_BUFFER_BINDING 0x8894
#endif
#ifndef GL_ELEMENT_ARRAY_BUFFER_BINDING
#define GL_ELEMENT_ARRAY_BUFFER_BINDING 0x8895
#endif
#ifndef GL_LINEAR_MIPMAP_LINEAR
#define GL_LINEAR_MIPMAP_LINEAR 0x2703
#endif
#ifndef GL_RGBA8
#define GL_RGBA8 0x8058
#endif
#ifndef GL_READ_FRAMEBUFFER
#define GL_READ_FRAMEBUFFER 0x8CA8
#endif
#ifndef GL_READ_FRAMEBUFFER_BINDING
#define GL_READ_FRAMEBUFFER_BINDING 0x8CAA
#endif
#ifndef GL_COLOR_ATTACHMENT0
#define GL_COLOR_ATTACHMENT0 0x8CE0
#endif
#ifndef GL_SYNC_GPU_COMMANDS_COMPLETE
#define GL_SYNC_GPU_COMMANDS_COMPLETE 0x9117
#endif
#ifndef GL_TIMEOUT_IGNORED
#define GL_TIMEOUT_IGNORED 0xFFFFFFFFFFFFFFFFull
#endif
#ifndef GL_TEXTURE_MAX_ANISOTROPY
#define GL_TEXTURE_MAX_ANISOTROPY 0x84FE
#endif

typedef struct re4_gl_sync *re4_GLsync;
#define GLsync re4_GLsync

static inline void *re4_gl_proc(const char *name) {
#if defined(_WIN32)
    void *p = (void *)wglGetProcAddress(name);
    if (!p || p == (void *)1 || p == (void *)2 || p == (void *)3 || p == (void *)-1) {
        HMODULE module = GetModuleHandleA("opengl32.dll");
        p = module ? (void *)GetProcAddress(module, name) : NULL;
    }
    return p;
#else
    return dlsym(RTLD_DEFAULT, name);
#endif
}

/* Each wrapper resolves once; calling an entry point the driver lacks is a
 * programming error the callers already guard with extension checks. */
#define RE4_GL_VOID(name, params, args) \
    static inline void APIENTRY re4_##name params { \
        typedef void (APIENTRY *function) params; static function f; \
        if (!f) f = (function)re4_gl_proc(#name); \
        if (f) f args; \
    }
#define RE4_GL_RETURN(type, name, params, args) \
    static inline type APIENTRY re4_##name params { \
        typedef type (APIENTRY *function) params; static function f; \
        if (!f) f = (function)re4_gl_proc(#name); \
        return f ? f args : (type)0; \
    }
RE4_GL_VOID(glActiveTexture, (GLenum t), (t))
RE4_GL_VOID(glClientActiveTexture, (GLenum t), (t))
RE4_GL_VOID(glBindFramebuffer, (GLenum target, GLuint framebuffer), (target, framebuffer))
RE4_GL_VOID(glFramebufferTexture2D, (GLenum target, GLenum attachment, GLenum textarget, GLuint texture, GLint level),
            (target, attachment, textarget, texture, level))
RE4_GL_VOID(glBlitFramebuffer, (GLint a, GLint b, GLint c, GLint d, GLint e, GLint f2, GLint g, GLint h, GLbitfield mask, GLenum filter),
            (a, b, c, d, e, f2, g, h, mask, filter))
RE4_GL_RETURN(GLsync, glFenceSync, (GLenum condition, GLbitfield flags), (condition, flags))
RE4_GL_VOID(glWaitSync, (GLsync sync, GLbitfield flags, uint64_t timeout), (sync, flags, timeout))
RE4_GL_VOID(glDeleteSync, (GLsync sync), (sync))
#define glActiveTexture re4_glActiveTexture
#define glClientActiveTexture re4_glClientActiveTexture
#define glBindFramebuffer re4_glBindFramebuffer
#define glFramebufferTexture2D re4_glFramebufferTexture2D
#define glBlitFramebuffer re4_glBlitFramebuffer
#define glFenceSync re4_glFenceSync
#define glWaitSync re4_glWaitSync
#define glDeleteSync re4_glDeleteSync
#endif
#endif
