"""ARM math helper implementations executed within Unicorn, avoiding Python callbacks."""
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM


def install(arm):
    assembler = Ks(KS_ARCH_ARM, KS_MODE_ARM)
    position = arm.base + 10 * 1024 * 1024
    helpers = {}
    for name, operation in (('fadd', 'vadd'), ('fsub', 'vsub'), ('fmul', 'vmul'), ('fdiv', 'vdiv')):
        helpers[name] = f'vmov s0,r0; vmov s1,r1; {operation}.f32 s0,s0,s1; vmov r0,s0; bx lr'
    for name, condition in (('fcmpeq','eq'),('fcmplt','mi'),('fcmple','ls'),('fcmpge','ge'),('fcmpgt','gt')):
        helpers[name] = f'vmov s0,r0; vmov s1,r1; vcmp.f32 s0,s1; vmrs APSR_nzcv,fpscr; mov r0,#0; mov{condition} r0,#1; movvs r0,#0; bx lr'
    helpers['f2iz'] = 'vmov s0,r0; vcvt.s32.f32 s0,s0; vmov r0,s0; bx lr'
    helpers['i2f'] = 'vmov s0,r0; vcvt.f32.s32 s0,s0; vmov r0,s0; bx lr'
    helpers['ui2f'] = 'vmov s0,r0; vcvt.f32.u32 s0,s0; vmov r0,s0; bx lr'
    helpers['f2d'] = 'vmov s0,r0; vcvt.f64.f32 d0,s0; vmov r0,r1,d0; bx lr'
    for name, source in helpers.items():
        code, _ = assembler.asm(source)
        arm.write(position, bytes(code))
        arm.imports['__aeabi_' + name] = position
        position += (len(code) + 15) & ~15
