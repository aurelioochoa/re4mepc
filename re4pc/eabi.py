"""ARM math helper implementations executed within Unicorn, avoiding Python callbacks."""
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM

# libmc_eruption carries libgcc's ARM soft-float routines, and libbio4af's
# imports resolve to them too. Each audited entry's first instruction becomes a
# branch to a VFP helper; the original word is checked first. fsub and frsub
# negate an operand and enter fadd. The fcmp* wrappers would otherwise reach
# __cmpsf2 through cfcmple/cfrcmple, about 20 instructions per comparison.
#
# This libgcc build treats denormals and NaN payloads differently from VFP.
# Conversions and comparisons match for every input. Arithmetic takes the VFP
# result only for normal or zero operands with a normal or exact-zero result;
# otherwise it runs the displaced first instruction and resumes the original
# routine. cfcmple/cfrcmple return VFP's NZCV, which equals libgcc's for
# ordered operands; unordered ones set V, so they resume the original.
# cfrcmple returns with r0/r1 swapped, as the original does.
# tools/verify_softfloat.py compares each helper bit for bit.
SOFT_FLOAT_MODULE = 'libmc_eruption_for_android_jni.so'
# symbol: (first instruction word, displaced instruction, helper body)
SOFT_FLOAT = {
    '__aeabi_fadd': (0xe1b02080, 'lsls r2, r0, #1', 'vadd'),
    '__aeabi_fmul': (0xe3a0c0ff, 'mov ip, #0xff', 'vmul'),
    '__aeabi_fdiv': (0xe3a0c0ff, 'mov ip, #0xff', 'vdiv'),
    '__aeabi_i2f': (0xe2103102, None, '__aeabi_i2f'),
    '__aeabi_ui2f': (0xe3a03000, None, '__aeabi_ui2f'),
    '__aeabi_f2iz': (0xe1a02080, None, '__aeabi_f2iz'),
    '__gtsf2': (0xe3e0c000, None, '__gtsf2'),
    '__ltsf2': (0xe3a0c001, None, '__ltsf2'),
    '__cmpsf2': (0xe3a0c001, None, '__cmpsf2'),
    # cfcmpeq is an alias of cfcmple; the fcmp* entries call one of these.
    '__aeabi_cfcmple': (0xe92d400f, 'push {r0, r1, r2, r3, lr}', 'cfcmple'),
    '__aeabi_cfrcmple': (0xe1a0c000, 'mov ip, r0', 'cfrcmple'),
    '__aeabi_fcmpeq': (0xe52de008, None, '__aeabi_fcmpeq'),
    '__aeabi_fcmplt': (0xe52de008, None, '__aeabi_fcmplt'),
    '__aeabi_fcmple': (0xe52de008, None, '__aeabi_fcmple'),
    '__aeabi_fcmpge': (0xe52de008, None, '__aeabi_fcmpge'),
    '__aeabi_fcmpgt': (0xe52de008, None, '__aeabi_fcmpgt'),
}
# Flag-returning comparisons: (code before the VFP compare, code on the
# unordered path, resume offset, audited words between the entry and it).
FLAG_COMPARE = {
    'cfcmple': ('', 'push {r0, r1, r2, r3, lr}', 4, ()),
    # mov ip, r0; mov r0, r1; mov r1, ip; b cfcmple (at +12)
    'cfrcmple': ('mov ip, r0; mov r0, r1; mov r1, ip; ', '', 12, (0xe1a00001, 0xe1a0100c)),
}


def _finite(register, scratch, zero):
    """Branch to slow unless register is normal; zero goes to ``zero``."""
    return (f'lsls {scratch}, {register}, #1; beq {zero}; lsrs {scratch}, {scratch}, #24; beq slow; '
            f'cmp {scratch}, #255; beq slow; ')


def _arithmetic(operation, displaced, entry):
    # r2, r3 and flags are scratch at a call boundary, and r0/r1 stay intact
    # until the result is chosen, so the slow path sees the original inputs.
    if operation == 'vadd':
        # Normal operands cannot round to zero: an exact zero is a true
        # cancellation, which VFP and libgcc both return as +0.
        result_zero = 'done'
    else:
        # A zero product or quotient of nonzero operands is an underflow.
        result_zero = 'zero'
    return ('check_a: ' + _finite('r0', 'r2', 'check_b') +
            'check_b: ' + _finite('r1', 'r2', 'compute') +
            f'compute: vmov s0, r0; vmov s1, r1; {operation}.f32 s0, s0, s1; vmov r2, s0; ' +
            _finite('r2', 'r3', result_zero) +
            'done: mov r0, r2; bx lr; ' +
            'zero: lsls r3, r0, #1; beq done; lsls r3, r1, #1; beq done; ' +
            f'slow: {displaced}; b {entry + 4:#x}')


def _flags(operation, displaced, entry):
    # Only ip, lr and the flags may change; s0/s1 are scratch as above.
    before, unordered, resume, _ = FLAG_COMPARE[operation]
    return (f'{before}vmov s0, r0; vmov s1, r1; vcmp.f32 s0, s1; vmrs APSR_nzcv, fpscr; bxvc lr; '
            f'{unordered + "; " if unordered else ""}b {entry + resume:#x}')


def install(arm, redirect=True):
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
    helpers = {'__aeabi_' + name: source for name, source in helpers.items()}
    # libgcc three-way comparisons: -1, 0 or 1; unordered yields -1 for
    # __gtsf2/__gesf2 and 1 for __ltsf2/__lesf2 and __cmpsf2/__eqsf2/__nesf2.
    compare = 'vmov s0,r0; vmov s1,r1; vcmp.f32 s0,s1; vmrs APSR_nzcv,fpscr; mov r0,#0; movgt r0,#1; mvnmi r0,#0; '
    helpers['__gtsf2'] = compare + 'mvnvs r0,#0; bx lr'
    helpers['__ltsf2'] = compare + 'movvs r0,#1; bx lr'
    helpers['__cmpsf2'] = helpers['__ltsf2']
    for name, source in helpers.items():
        code, _ = assembler.asm(source)
        arm.write(position, bytes(code))
        arm.imports[name] = position
        position += (len(code) + 15) & ~15
    arm.soft_float = soft_float_helpers(arm, assembler, position)
    if redirect:
        redirect_soft_float(arm)


def soft_float_helpers(arm, assembler, position):
    """Return {symbol: helper address} for the engine's soft-float entries."""
    module = next((m for m in arm.modules if m['path'].name == SOFT_FLOAT_MODULE), None)
    if module is None:
        return {}
    result = {}
    for symbol, (original, displaced, body) in SOFT_FLOAT.items():
        entry = arm.symbols.get(symbol)
        if entry is None or entry & 1 or not module['base'] <= entry < module['base'] + 0x100000:
            raise RuntimeError(f'Unsupported soft-float entry: {symbol}')
        audited = (original,) + (FLAG_COMPARE[body][3] if body in FLAG_COMPARE else ())
        if any(arm.u32(entry + 4 * i) != word for i, word in enumerate(audited)):
            raise RuntimeError(f'Unexpected soft-float code at {symbol}')
        if displaced is None:
            result[symbol] = arm.imports[body]
            continue
        source = _flags if body in FLAG_COMPARE else _arithmetic
        code, _ = assembler.asm(source(body, displaced, entry), position)
        arm.write(position, bytes(code))
        result[symbol] = position
        position += (len(code) + 15) & ~15
    return result


def redirect_soft_float(arm):
    """Branch the engine's soft-float entries to their helpers."""
    for symbol, helper in arm.soft_float.items():
        entry = arm.symbols[symbol]
        offset = helper - (entry + 8)
        if offset & 3 or not -(1 << 25) <= offset < 1 << 25:
            raise RuntimeError(f'Soft-float helper out of branch range: {symbol}')
        arm.w32(entry, 0xea000000 | ((offset >> 2) & 0xffffff))  # ARM b <helper>
    return len(arm.soft_float)
