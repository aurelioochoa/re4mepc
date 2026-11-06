/* The few Unicorn entry points the helpers use, bound at runtime.
 *
 * Python passes the addresses of the functions exported by the libunicorn it
 * already loaded (re4_uc_bind), so the helpers never link a second copy of
 * Unicorn and build identically on Linux, Windows and macOS. Constants match
 * unicorn/unicorn_const.py and arm_const.py; tests/test_native_abi.py checks them.
 */
#ifndef RE4_UC_API_H
#define RE4_UC_API_H
#include <stddef.h>
#include <stdint.h>

typedef struct uc_struct uc_engine;
typedef size_t uc_hook;
typedef int uc_err;
#define UC_ERR_OK 0
#define UC_HOOK_CODE 4
#define UC_ARM_REG_R0 66
#define UC_ARM_REG_R1 67
#define UC_ARM_REG_R2 68
#define UC_ARM_REG_R3 69

struct re4_uc_api {
    uc_err (*hook_add)(uc_engine *, uc_hook *, int, void *, void *, uint64_t, uint64_t, ...);
    uc_err (*hook_del)(uc_engine *, uc_hook);
    uc_err (*reg_read_batch)(uc_engine *, const int *, void **, int);
    uc_err (*reg_write)(uc_engine *, int, const void *);
    uc_err (*emu_stop)(uc_engine *);
};
extern struct re4_uc_api re4_uc;
#define uc_hook_add re4_uc.hook_add
#define uc_hook_del re4_uc.hook_del
#define uc_reg_read_batch re4_uc.reg_read_batch
#define uc_reg_write re4_uc.reg_write
#define uc_emu_stop re4_uc.emu_stop
#endif
