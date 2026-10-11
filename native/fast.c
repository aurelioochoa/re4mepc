/* Native implementations of hot libc imports for the shared ARM address space. */
#include <unicorn/unicorn.h>
#include <unicorn/arm.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <stdio.h>

struct bridge { uc_engine *uc; uc_hook hook; uintptr_t base, end, start; uint64_t calls; char error[160]; };
static int valid(struct bridge *b, uint32_t p, size_t n) {
    if (!n) return 1;
    if (p >= b->base && (uint64_t)p + n <= b->end) return 1;
    snprintf(b->error,sizeof(b->error),"native import pointer 0x%x + %zu outside guest memory",p,n);
    uc_emu_stop(b->uc); return 0;
}
static size_t length(struct bridge *b, uint32_t p) {
    if (!valid(b,p,1)) return 0;
    size_t maximum=b->end-p;
    if (maximum > 65536) maximum=65536;
    size_t n=strnlen((char *)(uintptr_t)p,maximum);
    if (n==maximum) { snprintf(b->error,sizeof(b->error),"unterminated native import string");uc_emu_stop(b->uc); }
    return n;
}
static void invoke(uc_engine *uc, uint64_t address, uint32_t size, void *context) {
    (void)size;
    struct bridge *b=context;
    uint32_t a[4];
    int regs[]={UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3};
    void *pointers[]={&a[0],&a[1],&a[2],&a[3]};
    uc_reg_read_batch(uc,regs,pointers,4);
    unsigned operation=(unsigned)((address-b->start)/4);
    uint32_t result=0;
    size_t n=0,m=0;
    char *dst=(char *)(uintptr_t)a[0], *src=(char *)(uintptr_t)a[1];
    b->calls++;
    switch (operation) {
    case 0: case 1:
        if (!valid(b,a[0],a[2]) || !valid(b,a[1],a[2])) return;
        if (a[2]) { memmove(dst,src,a[2]); }
        result=a[0]; break;
    case 2:
        if (!valid(b,a[0],a[2])) return;
        if (a[2]) { memset(dst,(int)a[1],a[2]); }
        result=a[0]; break;
    case 3:
        if (!valid(b,a[0],a[2]) || !valid(b,a[1],a[2])) return;
        result=a[2]?(uint32_t)memcmp(dst,src,a[2]):0; break;
    case 4: result=(uint32_t)length(b,a[0]); break;
    case 5:
        n=length(b,a[0]);m=length(b,a[1]);
        if (!b->error[0] && valid(b,a[0],n+1) && valid(b,a[1],m+1)) { result=(uint32_t)strcmp(dst,src); }
        break;
    case 6:
        if (!valid(b,a[0],a[2]) || !valid(b,a[1],a[2])) return;
        result=(uint32_t)strncmp(dst,src,a[2]); break;
    case 7:
        n=length(b,a[1]); if (!valid(b,a[0],n+1)) return;
        if (!b->error[0]) { memcpy(dst,src,n+1); }
        result=a[0];break;
    case 8:
        n=length(b,a[1]); if (!valid(b,a[0],a[2])) return;
        if (!b->error[0]) { strncpy(dst,src,a[2]); }
        result=a[0];break;
    case 9:
        if (!valid(b,a[0],4)) return;
        m=(b->end-a[0])/sizeof(wchar_t);
        if (m>65536) m=65536;
        n=wcsnlen((wchar_t *)dst,m);
        if (n==m) { snprintf(b->error,sizeof(b->error),"unterminated native import wide string");uc_emu_stop(uc);return; }
        result=(uint32_t)n;break;
    default:
        snprintf(b->error,sizeof(b->error),"unknown native operation %u",operation);uc_emu_stop(uc);return;
    }
    if (!b->error[0]) uc_reg_write(uc,UC_ARM_REG_R0,&result);
}
void *re4_fast_open(void *uc, uintptr_t base, size_t bytes, uintptr_t start) {
    struct bridge *b=calloc(1,sizeof(*b));if(!b)return NULL;
    b->uc=uc;b->base=base;b->end=base+bytes;b->start=start;
    if (uc_hook_add(b->uc,&b->hook,UC_HOOK_CODE,(void *)invoke,b,start,start+39)) { free(b);return NULL; }
    return b;
}
const char *re4_fast_error(void *bridge) { return ((struct bridge *)bridge)->error; }
uint64_t re4_fast_calls(void *bridge) { return ((struct bridge *)bridge)->calls; }
void re4_fast_close(void *bridge) {
    struct bridge *b=bridge;uc_hook_del(b->uc,b->hook);free(b);
}
