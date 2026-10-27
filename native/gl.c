/* Direct Unicorn -> desktop GL state submissions, avoiding Python per call.
 * Resource uploads, draws, queries and custom sights keep the checked Python
 * path. No GL state is cached: host overlays may change it between imports.
 * Viewport, scissor, projection and texture filters pass through display.c.
 */
#include <GL/gl.h>
#include <unicorn/unicorn.h>
#include <unicorn/arm.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <time.h>

struct gl_bridge {
    uc_engine *uc; uc_hook hook; uintptr_t base, end, start;
    uint64_t calls, nanoseconds, maximum_ns; int timed;
    uint64_t operations[40]; char error[160];
};
void re4_display_viewport(int x, int y, int w, int h);
void re4_display_scissor(int x, int y, int w, int h);
void re4_display_matrix_mode(unsigned mode);
void re4_display_load_matrix(const float *m);
void re4_display_tex_parameter(unsigned target, unsigned name, float value);
static float real(uint32_t v) { float f; memcpy(&f,&v,sizeof(f)); return f; }
static uint64_t nanos(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t);
    return (uint64_t)t.tv_sec*1000000000u+t.tv_nsec;
}
static int pointer(struct gl_bridge *b, uint32_t p, size_t n) {
    if (p && p>=b->base && (uint64_t)p+n<=b->end) return 1;
    snprintf(b->error,sizeof(b->error),"graphics pointer 0x%x + %zu outside guest memory",p,n);
    uc_emu_stop(b->uc); return 0;
}
static void invoke_gl(uc_engine *uc, uint64_t address, uint32_t size, void *context) {
    (void)size;
    struct gl_bridge *b=context;
    uint32_t a[4];
    int regs[]={UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3};
    void *p[]={&a[0],&a[1],&a[2],&a[3]};
    if (uc_reg_read_batch(uc,regs,p,4)!=UC_ERR_OK) { uc_emu_stop(uc); return; }
    unsigned op=(unsigned)((address-b->start)/4);
    uint64_t began=b->timed?nanos():0;
    switch (op) {
    case 0: glEnable(a[0]); break;
    case 1: glDisable(a[0]); break;
    case 2: glBindTexture(a[0],a[1]); break;
    case 3: glActiveTexture(a[0]); break;
    case 4: glClientActiveTexture(a[0]); break;
    case 5: glEnableClientState(a[0]); break;
    case 6: glDisableClientState(a[0]); break;
    case 7: if (a[3] && !pointer(b,a[3],1)) return; glVertexPointer(a[0],a[1],a[2],(void *)(uintptr_t)a[3]); break;
    case 8: if (a[3] && !pointer(b,a[3],1)) return; glColorPointer(a[0],a[1],a[2],(void *)(uintptr_t)a[3]); break;
    case 9: if (a[3] && !pointer(b,a[3],1)) return; glTexCoordPointer(a[0],a[1],a[2],(void *)(uintptr_t)a[3]); break;
    case 10: if (a[2] && !pointer(b,a[2],1)) return; glNormalPointer(a[0],a[1],(void *)(uintptr_t)a[2]); break;
    case 11: re4_display_matrix_mode(a[0]); break;
    case 12: if (!pointer(b,a[0],64)) return; re4_display_load_matrix((void *)(uintptr_t)a[0]); break;
    case 13: if (!pointer(b,a[0],64)) return; glMultMatrixf((void *)(uintptr_t)a[0]); break;
    case 14: glColor4f(real(a[0]),real(a[1]),real(a[2]),real(a[3])); break;
    case 15: glBlendFunc(a[0],a[1]); break;
    case 16: glTexEnvf(a[0],a[1],real(a[2])); break;
    case 17: if (!pointer(b,a[2],16)) return; glTexEnvfv(a[0],a[1],(void *)(uintptr_t)a[2]); break;
    case 18: glMaterialf(a[0],a[1],real(a[2])); break;
    case 19: if (!pointer(b,a[2],16)) return; glMaterialfv(a[0],a[1],(void *)(uintptr_t)a[2]); break;
    case 20: glLightf(a[0],a[1],real(a[2])); break;
    case 21: if (!pointer(b,a[2],16)) return; glLightfv(a[0],a[1],(void *)(uintptr_t)a[2]); break;
    case 22: glLightModelf(a[0],real(a[1])); break;
    case 23: if (!pointer(b,a[1],16)) return; glLightModelfv(a[0],(void *)(uintptr_t)a[1]); break;
    case 24: glFogf(a[0],real(a[1])); break;
    case 25: if (!pointer(b,a[1],16)) return; glFogfv(a[0],(void *)(uintptr_t)a[1]); break;
    case 26: glDepthFunc(a[0]); break;
    case 27: glDepthMask(a[0]); break;
    case 28: glColorMask(a[0],a[1],a[2],a[3]); break;
    case 29: glAlphaFunc(a[0],real(a[1])); break;
    case 30: glCullFace(a[0]); break;
    case 31: glFrontFace(a[0]); break;
    case 32: glShadeModel(a[0]); break;
    case 33: glPolygonOffset(real(a[0]),real(a[1])); break;
    case 34: re4_display_viewport(a[0],a[1],a[2],a[3]); break;
    case 35: re4_display_scissor(a[0],a[1],a[2],a[3]); break;
    case 36: glStencilFunc(a[0],a[1],a[2]); break;
    case 37: glStencilOp(a[0],a[1],a[2]); break;
    case 38: glHint(a[0],a[1]); break;
    case 39: re4_display_tex_parameter(a[0],a[1],real(a[2])); break;
    default: snprintf(b->error,sizeof(b->error),"unknown graphics import %u",op); uc_emu_stop(uc); return;
    }
    ++b->calls; ++b->operations[op];
    if (b->timed) {
        uint64_t elapsed=nanos()-began; b->nanoseconds+=elapsed;
        if (elapsed>b->maximum_ns) b->maximum_ns=elapsed;
    }
    uint32_t result=0; uc_reg_write(uc,UC_ARM_REG_R0,&result);
}
void *re4_gl_open(void *uc, uintptr_t base, size_t bytes, uintptr_t start, int timed) {
    struct gl_bridge *b=calloc(1,sizeof(*b));
    if (!b) return NULL;
    b->uc=uc; b->base=base; b->end=base+bytes; b->start=start; b->timed=timed;
    if (uc_hook_add(b->uc,&b->hook,UC_HOOK_CODE,(void *)invoke_gl,b,start,start+39*4)) { free(b); return NULL; }
    return b;
}
const char *re4_gl_error(void *handle) { return ((struct gl_bridge *)handle)->error; }
uint64_t re4_gl_measure(void *handle, unsigned key) {
    struct gl_bridge *b=handle;
    if (key==0) return b->calls;
    if (key==1) return b->nanoseconds;
    if (key==2) return b->maximum_ns;
    return key-3<40?b->operations[key-3]:0;
}
void re4_gl_close(void *handle) {
    struct gl_bridge *b=handle;
    if (b) { uc_hook_del(b->uc,b->hook); free(b); }
}
