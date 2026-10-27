"""Run the engine's hottest soft-float math functions as native Rust code.

The supported engine was built without a hardware float ABI, so each multiply
and add is a libgcc call. Bone skinning, vector dot products and transform
multiplication alone issue most of the ~200,000 such calls per gameplay tick;
collision distance and plane-side tests follow. native/math.rs implements
these functions with the same rounding and returns to the original ARM
routine for any input outside the verified soft-float domain (see that file
for the exact rules).

Each function's first four bytes (two plain Thumb-1 instructions) become a
branch to a Thumb trampoline in host-owned guest memory:

    +0   bx lr               hooked: Rust computes, writes and returns
    +2   nop
    +4   push {r4, lr}       shadow mode: call the original ...
    +6   bl original
    +10  pop {r4, pc}        ... hooked here to compare its results
    +12  nop; nop
    +16  <displaced 4 bytes>; b.w entry+4   (the original routine)

Shadow mode never uses the host result; it runs the original for every call
and counts mismatches. tools/verify_native_math.py uses it with your game.
"""
import ctypes as C
import hashlib
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
from unicorn.unicorn_py3.unicorn import uclib
from .paths import native_library

# symbol: its first four bytes in the supported engine (Thumb-1, no PC use)
FUNCTIONS = {
    '_mceBoneDeformer_transPoints': bytes.fromhex('f0b55f46'),  # push {r4-r7,lr}; mov r7, fp
    'mceVector3D_dot': bytes.fromhex('70b5051c'),               # push {r4-r6,lr}; adds r5, r0, #0
    '_mceTransform_multiply2': bytes.fromhex('f0b55646'),       # push {r4-r7,lr}; mov r6, sl
    # push {r4, lr}; sub sp, #0x18
    '_ZN17GM_Util_Collision19Check_ReiCrossPlaneEP17GM_Geometry_PlaneP11tagVector3DS3_': bytes.fromhex('10b586b0'),
    '_ZN11ERP_CalcVec11Get_Dis_PosEP11tagVector3DS1_': bytes.fromhex('10b586b0'),
    # push {r4, r5, lr}; sub sp, #0x1c
    '_ZN17GM_Util_Collision20Check_InsideTriangleEP20GM_Geometry_TriangleP11tagVector3D': bytes.fromhex('30b587b0'),
    # push {r4, r5, lr}; sub sp, #0x34
    '_ZN17GM_Util_Collision20Check_ReiCrossSphereEP18GM_Geometry_SphereP11tagVector3DS3_': bytes.fromhex('30b58db0'),
    # push {r4, lr}; sub sp, #0x20 / #0x38
    '_ZN17GM_Util_Collision23Set_ReiPlane_CrossPointEP11tagVector3DP17GM_Geometry_PlaneS1_S1_': bytes.fromhex('10b588b0'),
    '_ZN17GM_Util_Collision20Get_PointCrossLinePtEP11tagVector3DS1_S1_S1_': bytes.fromhex('10b58eb0'),
}
# Distances call this table-driven routine; Rust reads its table and two
# constants at fixed offsets, so its code must be exactly this.
SQRT = 'mceUtil3D_sqrt'
SQRT_BYTES = 0x78
SQRT_SHA256 = '7e85a5191db152128441c4bcab5bb798297f7e737bed617d95200e95796b8319'
TRAMPOLINES = 11 * 1024 * 1024  # between the soft-float (10 MiB) and memory (12 MiB) helpers
SITE_BYTES = 32


class Counters(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in ('handled', 'fallbacks', 'verified', 'mismatches')]


def _address(function):
    return C.cast(function, C.c_void_p).value


def sqrt_entry(arm):
    """mceUtil3D_sqrt's code address, after checking its exact bytes."""
    entry = arm.symbols.get(SQRT)
    if entry is None or not entry & 1:
        raise RuntimeError(f'Unsupported native math entry: {SQRT}')
    if hashlib.sha256(arm.read(entry & ~1, SQRT_BYTES)).hexdigest() != SQRT_SHA256:
        raise RuntimeError(f'Unexpected native math code at {SQRT}')
    return entry & ~1


class NativeMath:
    def __init__(self, arm, shadow=False):
        self.arm = arm
        self.shadow = shadow
        self.handle = None
        self.lib = C.CDLL(str(native_library('libre4math.so')))
        if self.lib.re4_math_functions() != len(FUNCTIONS):
            raise RuntimeError('libre4math.so does not match re4pc.native_math; run make build')
        self.lib.re4_math_open.restype = C.c_void_p
        self.lib.re4_math_open.argtypes = (C.c_void_p,) * 5 + (C.c_uint64, C.c_uint64, C.c_int, C.POINTER(C.c_uint32),
                                                              C.c_uint32)
        self.lib.re4_math_counters.restype = Counters
        self.lib.re4_math_counters.argtypes = (C.c_void_p, C.c_size_t)
        self.lib.re4_math_mismatch.argtypes = (C.c_void_p, C.c_size_t, C.POINTER(C.c_uint32))
        self.lib.re4_math_close.argtypes = (C.c_void_p,)

    def install(self):
        """Patch the loaded engine before any of its code is translated."""
        arm = self.arm
        assembler = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
        def assemble(text, address):
            return bytes(assembler.asm(text, address)[0])
        entries = []
        for name, displaced in FUNCTIONS.items():
            entry = arm.symbols.get(name)
            if entry is None or not entry & 1:
                raise RuntimeError(f'Unsupported native math entry: {name}')
            if arm.read(entry & ~1, 4) != displaced:
                raise RuntimeError(f'Unexpected native math code at {name}')
            entries.append(entry & ~1)
        sqrt = sqrt_entry(arm)
        sites = []
        site = arm.base + TRAMPOLINES
        for entry, displaced in zip(entries, FUNCTIONS.values()):
            original = site + 16
            code = (b'\x70\x47\x00\xbf\x10\xb5' + assemble(f'bl #{original:#x}', site + 6) + b'\x10\xbd\x00\xbf\x00\xbf'
                    + displaced + assemble(f'b.w #{entry + 4:#x}', original + 4))
            if len(code) != 24:
                raise RuntimeError('Unexpected native math trampoline size')
            arm.write(site, code)
            sites += [site, site + 4, site + 10, original]
            site += SITE_BYTES
        self.handle = self.lib.re4_math_open(
            arm.uc._uch, _address(uclib.uc_hook_add), _address(uclib.uc_hook_del), _address(uclib.uc_reg_read),
            _address(uclib.uc_reg_write), arm.base, arm.SIZE, int(self.shadow), (C.c_uint32 * len(sites))(*sites), sqrt)
        if not self.handle:
            raise RuntimeError('Cannot create native math hooks')
        arm.native_math = self  # ArmRuntime.close releases the hooks
        # Branch last, once every trampoline and hook exists.
        for entry, start in zip(entries, sites[::4]):
            arm.write(entry, assemble(f'b.w #{start:#x}', entry))
        arm.uc.ctl_remove_cache(arm.base + TRAMPOLINES, site)
        for entry in entries:
            arm.uc.ctl_remove_cache(entry, entry + 4)

    def metrics(self):
        result = {'enabled': self.handle is not None, 'shadow': self.shadow}
        if self.handle:
            for index, name in enumerate(FUNCTIONS):
                counters = self.lib.re4_math_counters(self.handle, index)
                record = {field: getattr(counters, field) for field, _ in Counters._fields_}
                if record['mismatches']:
                    arguments = (C.c_uint32 * 4)()
                    self.lib.re4_math_mismatch(self.handle, index, arguments)
                    record['first_mismatch_arguments'] = [f'0x{value:08x}' for value in arguments]
                result[name] = record
        return result

    def close(self):
        if self.handle:
            self.lib.re4_math_close(self.handle)
            self.handle = None
