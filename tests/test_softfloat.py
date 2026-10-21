import struct
import unittest
from pathlib import Path

from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM

from re4pc.arm import ArmRuntime
from re4pc.eabi import SOFT_FLOAT, SOFT_FLOAT_MODULE, install

MARKER = 42  # Returned by the synthetic "original" routine bodies.


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def single(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


class SoftFloatTests(unittest.TestCase):
    """Synthetic libgcc stand-ins: the audited first word, then a marker body.

    Reaching the marker means the helper resumed the original routine.
    """
    def setUp(self):
        self.arm = ArmRuntime()
        self.addCleanup(self.arm.close)
        assembler = Ks(KS_ARCH_ARM, KS_MODE_ARM)
        base = self.arm.base + 0x40000
        self.arm.modules.append({'path': Path(SOFT_FLOAT_MODULE), 'base': base})
        body = bytes(assembler.asm(f'mov r0, #{MARKER}; bx lr')[0])
        for index, (symbol, (original, _, _)) in enumerate(SOFT_FLOAT.items()):
            entry = base + 0x100 * index
            self.arm.write(entry, struct.pack('<I', original) + body)
            self.arm.symbols[symbol] = entry

    def call(self, symbol, *arguments):
        return self.arm.call(self.arm.symbols[symbol], *arguments)

    def test_normal_arithmetic_uses_vfp_with_ieee_single_rounding(self):
        install(self.arm)
        for a, b in ((1.5, 2.25), (1e10, -3.0), (0.1, 0.2), (3.0, 7.0), (-2.5e-20, 4e8), (1.0, 2**-24)):
            for symbol, operation in (('__aeabi_fadd', lambda x, y: x + y),
                                      ('__aeabi_fmul', lambda x, y: x * y),
                                      ('__aeabi_fdiv', lambda x, y: x / y)):
                x, y = single(bits(a)), single(bits(b))
                # Double precision then one rounding to single is exact for
                # +, * and / of single operands (53 >= 2*24 + 2).
                self.assertEqual(self.call(symbol, bits(x), bits(y)), bits(operation(x, y)), (symbol, a, b))

    def test_special_operands_and_results_resume_the_original_routine(self):
        install(self.arm)
        denormal, infinity, nan, tiny, huge = 0x00000001, 0x7f800000, 0x7fc00000, bits(1e-30), bits(3e38)
        for symbol in ('__aeabi_fadd', '__aeabi_fmul', '__aeabi_fdiv'):
            for a, b in ((denormal, bits(1.0)), (bits(1.0), infinity), (nan, bits(2.0)), (bits(2.0), nan | 0x80000000)):
                self.assertEqual(self.call(symbol, a, b), MARKER, (symbol, hex(a), hex(b)))
        # Overflow, underflow to zero and a denormal sum.
        self.assertEqual(self.call('__aeabi_fadd', huge, huge), MARKER)
        self.assertEqual(self.call('__aeabi_fmul', tiny, tiny), MARKER)
        self.assertEqual(self.call('__aeabi_fdiv', tiny, huge), MARKER)
        self.assertEqual(self.call('__aeabi_fadd', 0x00800001, 0x80800000), MARKER)

    def test_zero_operands_and_exact_cancellation_stay_on_the_fast_path(self):
        install(self.arm)
        self.assertEqual(self.call('__aeabi_fadd', bits(5.0), bits(-5.0)), 0)
        self.assertEqual(self.call('__aeabi_fadd', 0x80000000, 0x80000000), 0x80000000)
        self.assertEqual(self.call('__aeabi_fmul', 0, bits(-3.0)), 0x80000000)
        self.assertEqual(self.call('__aeabi_fdiv', 0x80000000, bits(2.0)), 0x80000000)
        self.assertEqual(self.call('__aeabi_fadd', 0, bits(7.0)), bits(7.0))

    def test_conversions_and_comparisons(self):
        install(self.arm)
        self.assertEqual(self.call('__aeabi_i2f', 0xffffffff), bits(-1.0))
        self.assertEqual(self.call('__aeabi_ui2f', 0xffffffff), bits(4294967296.0))
        self.assertEqual(self.call('__aeabi_f2iz', bits(-7.9)), 0xfffffff9)
        for symbol, unordered in (('__gtsf2', 0xffffffff), ('__ltsf2', 1), ('__cmpsf2', 1)):
            self.assertEqual(self.call(symbol, bits(1.0), bits(2.0)), 0xffffffff)
            self.assertEqual(self.call(symbol, bits(2.0), bits(1.0)), 1)
            self.assertEqual(self.call(symbol, 0x80000000, 0), 0)
            self.assertEqual(self.call(symbol, 0x7fc00000, bits(1.0)), unordered)

    def test_unexpected_code_is_never_patched(self):
        entry = self.arm.symbols['__aeabi_fmul']
        self.arm.w32(entry, 0xe1a00000)
        with self.assertRaisesRegex(RuntimeError, 'Unexpected soft-float code'):
            install(self.arm)
        self.assertEqual(self.arm.u32(self.arm.symbols['__aeabi_fadd']), SOFT_FLOAT['__aeabi_fadd'][0])

    def test_redirect_can_be_deferred_and_without_the_module_is_a_no_op(self):
        install(self.arm, redirect=False)
        self.assertEqual(self.arm.u32(self.arm.symbols['__aeabi_fadd']), SOFT_FLOAT['__aeabi_fadd'][0])
        self.assertEqual(self.call('__aeabi_fadd', bits(1.0), bits(2.0)), MARKER)
        bare = ArmRuntime()
        try:
            install(bare)
            self.assertEqual(bare.soft_float, {})
        finally:
            bare.close()


if __name__ == '__main__':
    unittest.main()
