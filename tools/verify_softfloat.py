"""Compare the engine's libgcc soft-float routines with the VFP helpers bit for bit.

Both run inside Unicorn on the same inputs: special values (signed zeros,
denormals, extremes, infinities, quiet and signalling NaNs with payloads,
integer conversion boundaries), every pair of those, and seeded random bit
patterns, including operands with close exponents to exercise cancellation
and rounding. Requires your imported game; nothing is written to it.
"""
import argparse
import itertools
import random
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from re4pc.arm import ArmRuntime
from re4pc.assets import validate_libraries
from unicorn.arm_const import UC_ARM_REG_CPSR, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3
from re4pc.eabi import FLAG_COMPARE, SOFT_FLOAT, SOFT_FLOAT_MODULE, install, redirect_soft_float
from re4pc.paths import game_dir

SPECIAL = sorted({
    0x00000000, 0x80000000, 0x00000001, 0x80000001, 0x007fffff, 0x807fffff,
    0x00800000, 0x80800000, 0x00800001, 0x7f7fffff, 0xff7fffff, 0x7f800000, 0xff800000,
    0x7fc00000, 0xffc00000, 0x7f800001, 0xff800001, 0x7fbfffff, 0x7fc12345, 0xffa54321,
    0x3f800000, 0xbf800000, 0x3f000000, 0xbf000000, 0x3fc00000, 0x40000000, 0x3effffff,
    0x34000000, 0x33800000, 0x4b000000, 0x4b7fffff, 0x4effffff, 0x4f000000, 0xcf000000,
    0xcf000001, 0x4f800000, 0x5f000000, 0xdf000000, 0x0c000000, 0x73000000, 0x1f800000,
    0x3f800001, 0xbf7fffff, 0x7effffff, 0x01000000, 0x00400000,
})
INTEGERS = sorted({0, 1, 2, 3, 0x7f, 0x80, 0xffffff, 0x1000000, 0x1000001, 0x1000003, 0x7fffff80,
                   0x7fffffbf, 0x7fffffc0, 0x7fffffff, 0x80000000, 0x80000001, 0x800000c0,
                   0xfffffffe, 0xffffffff, 0xff000001, 0xfeffffff})


def operands(seed, count):
    generator = random.Random(seed)
    pairs = list(itertools.product(SPECIAL, repeat=2))
    for _ in range(count):
        a = generator.getrandbits(32)
        pairs.append((a, generator.getrandbits(32)))
        # Close exponents: cancellation, alignment shifts and ties to even.
        shift = generator.randrange(0, 30) << 23
        sign = generator.getrandbits(1) << 31
        pairs.append((a, ((a & 0x7fffffff) + generator.choice((-1, 1)) * shift
                          + generator.getrandbits(8)) & 0x7fffffff | sign))
        # Exact cancellation, and operands near the denormal boundary whose
        # sums, products and quotients underflow or become denormal.
        pairs.append((a, a ^ 0x80000000))
        tiny = (generator.randrange(1, 40) << 23) | generator.getrandbits(23) | (generator.getrandbits(1) << 31)
        pairs.append((tiny, (generator.randrange(1, 140) << 23) | generator.getrandbits(23)))
        pairs.append((tiny, (generator.randrange(110, 254) << 23) | generator.getrandbits(23)))
    return pairs


def singles(seed, count):
    generator = random.Random(seed)
    values = SPECIAL + INTEGERS + [generator.getrandbits(32) for _ in range(count)]
    # Floats around every power of two cover integer truncation boundaries.
    values += [(exponent << 23) | generator.getrandbits(23) | sign
               for exponent in range(100, 170) for sign in (0, 1 << 31) for _ in range(20)]
    return values


FLAG_STATE = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)


def flag_call(arm, address, *arguments):
    """NZCV and r0-r3 after a flag-returning comparison (r2/r3 seeded)."""
    arm.call(address, *arguments, 0x2468ace0, 0x13579bdf)
    return (arm.uc.reg_read(UC_ARM_REG_CPSR) >> 28,) + tuple(arm.uc.reg_read(r) for r in FLAG_STATE)


def compare(arm, original, helper, inputs, unary, flags=False):
    mismatches = []
    call = (lambda address, *a: flag_call(arm, address, *a)) if flags else arm.call
    for value in inputs:
        arguments = (value,) if unary else value
        expected, actual = call(original, *arguments), call(helper, *arguments)
        if expected != actual:
            mismatches.append((arguments, expected, actual))
    return mismatches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=game_dir())
    parser.add_argument('--random', type=int, default=50000, help='random cases per routine')
    parser.add_argument('--seed', type=int, default=4)
    args = parser.parse_args()
    validate_libraries(args.game)
    arm = ArmRuntime()
    try:
        arm.load(args.game / 'lib' / SOFT_FLOAT_MODULE, 0)
        install(arm, redirect=False)
        binary, unary = operands(args.seed, args.random), singles(args.seed, args.random)
        failed = False
        for symbol in SOFT_FLOAT:
            one = symbol in ('__aeabi_i2f', '__aeabi_ui2f', '__aeabi_f2iz')
            inputs = unary if one else binary
            flags = SOFT_FLOAT[symbol][2] in FLAG_COMPARE
            mismatches = compare(arm, arm.symbols[symbol], arm.soft_float[symbol], inputs, one, flags)
            print(f'{symbol:16} {len(inputs):7} cases  {len(mismatches)} mismatches', flush=True)
            for arguments, expected, actual in mismatches[:8]:
                print('   ', ' '.join(f'{value:08x}' for value in arguments), f'original={expected} helper={actual}')
            failed |= bool(mismatches)
        # The patched entries and the routines that fall into them.
        redirect_soft_float(arm)
        for symbol, a, b, expected in (('__aeabi_fsub', 0x40400000, 0x3f800000, 2.0),
                                       ('__aeabi_frsub', 0x3f800000, 0x40400000, 2.0),
                                       ('__aeabi_fadd', 0x3f800000, 0x40000000, 3.0),
                                       ('__aeabi_fcmplt', 0x3f800000, 0x40000000, 1),
                                       ('__aeabi_fcmpge', 0x7fc00000, 0x3f800000, 0),
                                       ('__aeabi_fcmpgt', 0x40000000, 0x3f800000, 1),
                                       ('__aeabi_fcmpeq', 0x7fc00000, 0x7fc00000, 0)):
            result = arm.call(arm.symbols[symbol], a, b)
            value = struct.unpack('<f', struct.pack('<I', result))[0] if isinstance(expected, float) else result
            if value != expected:
                print('PATCHED_ENTRY_FAIL', symbol, value)
                failed = True
    finally:
        arm.close()
    print('SOFTFLOAT_MISMATCH' if failed else 'SOFTFLOAT_IDENTICAL')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
