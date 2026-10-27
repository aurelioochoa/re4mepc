"""Rust math replacements on synthetic Thumb routines that share the engine's entry bytes."""
import hashlib
import random
import struct
import unittest
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
from re4pc import native_math
from re4pc.arm import ArmRuntime
from re4pc.native_math import FUNCTIONS, SQRT, SQRT_BYTES, NativeMath

TRANS, DOT, MULTIPLY, CROSS, DISTANCE, INSIDE, SPHERE, PLANE_POINT, LINE_POINT = FUNCTIONS
DENORMAL = 0x00000001
# Original-routine bodies placed after each function's real four-byte prologue.
VFP_DOT = ('vldr s0, [r5]; vldr s1, [r1]; vmul.f32 s0, s0, s1; '
           'vldr s2, [r5, #4]; vldr s3, [r1, #4]; vmul.f32 s2, s2, s3; vadd.f32 s0, s0, s2; '
           'vldr s2, [r5, #8]; vldr s3, [r1, #8]; vmul.f32 s2, s2, s3; vadd.f32 s0, s0, s2; '
           'vmov r0, s0; pop {r4, r5, r6, pc}')
SENTINEL_DOT = 'movw r0, #0x5678; movt r0, #0x1234; pop {r4, r5, r6, pc}'
# Marks the routine's first argument at +0x43 (multiply2) or the object at +0x300.
MARK_MULTIPLY = 'movs r4, #0xa5; strb r4, [r0, #0x43]; pop {r4, r5, r6, r7, pc}'
MARK_TRANS = 'movs r4, #0xa5; movs r5, #0xc0; lsls r5, r5, #2; strb r4, [r1, r5]; pop {r4, r5, r6, r7, pc}'
# Collision routines: after push {r4, lr}; sub sp, #0x18, return a marker.
MARKER = 0x5a
MARK_SMALL = f'movs r0, #{MARKER}; add sp, #0x18; pop {{r4, pc}}'
MARK_INSIDE = f'movs r0, #{MARKER}; add sp, #0x1c; pop {{r4, r5, pc}}'
MARK_SPHERE = f'movs r0, #{MARKER}; add sp, #0x34; pop {{r4, r5, pc}}'
MARK_PLANE_POINT = f'movs r0, #{MARKER}; add sp, #0x20; pop {{r4, pc}}'
MARK_LINE_POINT = f'movs r0, #{MARKER}; add sp, #0x38; pop {{r4, pc}}'
# A synthetic mceUtil3D_sqrt: the table offset and both constants sit where
# the engine's routine keeps them; the table follows the routine.
SQRT_K1, SQRT_K2 = 0xb505, 0x3504f334
SQRT_TABLE = [random.Random(3).getrandbits(32) for _ in range(24)]


def sqrt_routine():
    code = bytearray(b'\x70\x47' * (SQRT_BYTES // 2))  # bx lr
    code[0x6c:0x78] = struct.pack('<III', (SQRT_BYTES - 0x82) & 0xffffffff, SQRT_K1, SQRT_K2)
    return bytes(code) + struct.pack('<24I', *SQRT_TABLE)


def reference_sqrt(v):
    """mceUtil3D_sqrt's integer interpolation, as read from the engine."""
    if single(v) <= 0:
        return 0
    m = 0xffffffff
    exponent, row, fraction = (v << 1 & m) >> 24, (v << 9 & m) >> 29, (v << 12 & m) >> 19
    t0, t1, t2 = SQRT_TABLE[3 * row:3 * row + 3]
    slope = ((t1 - ((t2 * fraction & m) >> 2)) & m) >> 16
    root = ((t0 + 0x8000 + slope * fraction) & m) >> 16
    mantissa = root << 14 & m if exponent & 1 else (((root * SQRT_K1 & m) >> 1) + SQRT_K2) & m
    halved = (exponent - (((exponent - 0x7e) & m) >> 1)) & m
    return (mantissa >> 8 | halved << 23) & m


def single(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


# Exact products/sums of two singles fit a double, so rounding once matches f32.
def mul(a, b): return f32(a * b)
def add(a, b): return f32(a + b)


def runtime(dot=VFP_DOT, multiply=MARK_MULTIPLY, trans=MARK_TRANS, shadow=False):
    arm = ArmRuntime()
    assembler = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    address = arm.base + 1024 * 1024
    for name, body in ((TRANS, trans), (DOT, dot), (MULTIPLY, multiply), (CROSS, MARK_SMALL), (DISTANCE, MARK_SMALL),
                       (INSIDE, MARK_INSIDE), (SPHERE, MARK_SPHERE), (PLANE_POINT, MARK_PLANE_POINT),
                       (LINE_POINT, MARK_LINE_POINT)):
        code = FUNCTIONS[name] + bytes(assembler.asm(body, address + 4)[0])
        arm.write(address, code)
        arm.symbols[name] = address | 1
        address += (len(code) + 63) & ~15
    routine = sqrt_routine()
    arm.write(address, routine)
    arm.symbols[SQRT] = address | 1
    native_math.SQRT_SHA256 = hashlib.sha256(routine[:SQRT_BYTES]).hexdigest()
    math = NativeMath(arm, shadow=shadow)
    math.install()
    return arm, math


def floats(arm, values):
    pointer = arm.alloc(4 * len(values) + 4)
    arm.write(pointer, struct.pack(f'<{len(values)}f', *values))
    return pointer


def read_floats(arm, pointer, count):
    return list(struct.unpack(f'<{count}f', arm.read(pointer, 4 * count)))


def counters(math, name):
    return math.metrics()[name]


class DotTests(unittest.TestCase):
    def test_replacement_matches_vfp_for_random_normal_vectors(self):
        arm, math = runtime()
        self.addCleanup(arm.close)
        generator = random.Random(4)
        for _ in range(200):
            a = [f32(generator.uniform(-1e3, 1e3)) for _ in range(3)]
            b = [f32(generator.uniform(-1e3, 1e3)) for _ in range(3)]
            expected = add(add(mul(a[0], b[0]), mul(a[1], b[1])), mul(a[2], b[2]))
            self.assertEqual(arm.call(DOT, floats(arm, a), floats(arm, b)), bits(expected))
        self.assertEqual(counters(math, DOT)['handled'], 200)

    def test_signed_zero_and_exact_cancellation(self):
        arm, math = runtime(dot=SENTINEL_DOT)
        self.addCleanup(arm.close)
        self.assertEqual(arm.call(DOT, floats(arm, [-0.0, 0, 0]), floats(arm, [1, 0, 0])), 0)
        self.assertEqual(arm.call(DOT, floats(arm, [2, -2, 0]), floats(arm, [3, 3, 5])), 0)
        self.assertEqual(counters(math, DOT), {'handled': 2, 'fallbacks': 0, 'verified': 0, 'mismatches': 0})

    def test_denormal_infinite_and_overflow_inputs_run_the_original(self):
        arm, math = runtime(dot=SENTINEL_DOT)
        self.addCleanup(arm.close)
        denormal = arm.alloc(16)
        arm.write(denormal, struct.pack('<III', DENORMAL, 0, 0))
        for a, b in ((denormal, floats(arm, [1, 1, 1])), (floats(arm, [float('inf'), 0, 0]), floats(arm, [1, 1, 1])),
                     (floats(arm, [3e38, 0, 0]), floats(arm, [10, 0, 0])), (floats(arm, [1e-30, 0, 0]), floats(arm, [1e-30, 0, 0]))):
            self.assertEqual(arm.call(DOT, a, b), 0x12345678)
        self.assertEqual(counters(math, DOT)['fallbacks'], 4)
        self.assertEqual(counters(math, DOT)['handled'], 0)

    def test_shadow_mode_runs_the_original_and_counts_agreement(self):
        arm, math = runtime(shadow=True)
        self.addCleanup(arm.close)
        a, b = floats(arm, [1.5, 2, 3]), floats(arm, [4, 5, 0.25])
        self.assertEqual(arm.call(DOT, a, b), bits(16.75))
        self.assertEqual(counters(math, DOT), {'handled': 0, 'fallbacks': 0, 'verified': 1, 'mismatches': 0})

    def test_shadow_mode_reports_the_first_disagreeing_call(self):
        arm, math = runtime(dot=SENTINEL_DOT, shadow=True)
        self.addCleanup(arm.close)
        a, b = floats(arm, [1, 2, 3]), floats(arm, [4, 5, 6])
        self.assertEqual(arm.call(DOT, a, b), 0x12345678)
        arm.call(DOT, b, a)
        record = counters(math, DOT)
        self.assertEqual((record['verified'], record['mismatches']), (0, 2))
        self.assertEqual(record['first_mismatch_arguments'][:2], [f'0x{a:08x}', f'0x{b:08x}'])

    def test_closing_the_runtime_releases_hooks(self):
        arm, math = runtime()
        arm.close()
        self.assertIsNone(math.handle)
        self.assertIsNone(arm.native_math)


def write_transform(arm, values, flags=(0, 0, 0)):
    pointer = arm.alloc(0x48)
    arm.write(pointer, struct.pack('<16f', *values) + bytes(flags) + b'\0')
    return pointer


def reference_multiply(a, b):
    out = [0.0] * 16
    for column in (0, 4, 8, 12):
        for c in range(3):
            value = add(add(mul(b[column], a[c]), mul(b[column + 1], a[c + 4])), mul(b[column + 2], a[c + 8]))
            out[column + c] = add(value, a[12 + c]) if column == 12 else value
    out[15] = 1.0
    return out


IDENTITY = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def affine(generator):
    values = [f32(generator.uniform(-4, 4)) for _ in range(16)]
    values[3] = values[7] = values[11] = 0.0
    values[15] = 1.0
    return values


class MultiplyTests(unittest.TestCase):
    def setUp(self):
        self.arm, self.math = runtime()
        self.addCleanup(self.arm.close)
        self.generator = random.Random(9)

    def flags(self, pointer):
        return tuple(self.arm.read(pointer + 0x40, 4))

    def test_product_flags_and_identity_caches(self):
        a_values, b_values = affine(self.generator), affine(self.generator)
        a = write_transform(self.arm, a_values, (0, 1, 1))
        b = write_transform(self.arm, b_values, (0, 1, 0))
        out = write_transform(self.arm, [9.0] * 16, (7, 7, 7))
        self.arm.call(MULTIPLY, out, a, b)
        self.assertEqual(read_floats(self.arm, out, 16), reference_multiply(a_values, b_values))
        # Product clears its cache; flags are the inputs' joint flags.
        self.assertEqual(self.flags(out)[:3], (0, 1, 0))
        # Both inputs were compared and cached as non-identity.
        self.assertEqual(self.flags(a)[0], 2)
        self.assertEqual(self.flags(b)[0], 2)
        self.assertEqual(self.flags(out)[3], 0)  # the original's marker never ran

    def test_identity_operand_copies_the_other_transform(self):
        values = affine(self.generator)
        identity = write_transform(self.arm, IDENTITY)
        other = write_transform(self.arm, values, (2, 0, 1))
        out = write_transform(self.arm, [0.0] * 16)
        self.arm.call(MULTIPLY, out, identity, other)
        self.assertEqual(read_floats(self.arm, out, 16), values)
        self.assertEqual(self.flags(out)[:3], (2, 0, 1))
        self.assertEqual(self.flags(identity)[:3], (1, 1, 1))
        out2 = write_transform(self.arm, [0.0] * 16)
        self.arm.call(MULTIPLY, out2, other, identity)
        self.assertEqual(read_floats(self.arm, out2, 16), values)
        self.assertEqual(self.math.metrics()[MULTIPLY]['handled'], 2)

    def test_output_may_alias_an_input(self):
        a_values, b_values = affine(self.generator), affine(self.generator)
        a = write_transform(self.arm, a_values, (0, 1, 1))
        b = write_transform(self.arm, b_values, (0, 1, 1))
        self.arm.call(MULTIPLY, a, a, b)
        self.assertEqual(read_floats(self.arm, a, 16), reference_multiply(a_values, b_values))
        self.assertEqual(self.flags(a)[:3], (0, 1, 1))

    def test_partial_overlap_and_denormal_entries_run_the_original(self):
        a = write_transform(self.arm, affine(self.generator))
        b = write_transform(self.arm, affine(self.generator))
        self.arm.write(b + 20, struct.pack('<I', DENORMAL))
        out = write_transform(self.arm, [0.0] * 16)
        self.arm.call(MULTIPLY, out, a, b)
        self.assertEqual(self.flags(out)[3], 0xa5)
        shifted = a + 4
        self.arm.call(MULTIPLY, shifted, a, write_transform(self.arm, affine(self.generator)))
        self.assertEqual(self.arm.read(shifted + 0x43, 1), b'\xa5')
        self.assertEqual(self.math.metrics()[MULTIPLY]['fallbacks'], 2)


class TransPointsTests(unittest.TestCase):
    """Synthetic deformer: one root matrix, two bones, three points."""

    def setUp(self):
        self.arm, self.math = runtime()
        self.addCleanup(self.arm.close)
        generator = random.Random(17)
        self.matrices = [affine(generator) for _ in range(3)]
        words = []
        for matrix in self.matrices:
            words += matrix + [0.0]  # 17-word transforms; bone k is transform k + 1
        self.matrix_table = floats(self.arm, words)
        self.skeleton = self.arm.alloc(0x20)
        self.arm.write(self.skeleton + 4, struct.pack('<I', self.matrix_table))
        self.arm.write(self.skeleton + 0x10, b'\x07')
        self.points = [[f32(generator.uniform(-50, 50)) for _ in range(3)] for _ in range(3)]
        self.point_table = floats(self.arm, sum(self.points, []))
        # Influences: root only, bone 1 only, then bones 0 and 1 weighted.
        self.weights = [f32(0.25), f32(0.75)]
        influence = struct.pack('<4f4BB3x', 0, 0, 0, 0, 0, 0, 0, 0, 0)
        influence += struct.pack('<4f4BB3x', 0, 0, 0, 0, 1, 0, 0, 0, 1)
        influence += struct.pack('<4f4BB3x', *self.weights, 0, 0, 0, 1, 0, 0, 2)
        self.influence = self.arm.alloc(len(influence))
        self.arm.write(self.influence, influence)
        self.duplicates = self.arm.alloc(4)
        self.arm.write(self.duplicates, bytes((1, 2, 1)))
        self.deformer = self.arm.alloc(0x50)
        self.arm.write(self.deformer + 0x24, struct.pack('<II', self.duplicates, self.influence))
        self.arm.write(self.deformer + 0x4c, struct.pack('<I', self.skeleton))
        self.output = self.arm.alloc(4 * 12)
        self.object = self.arm.alloc(0x400)
        self.arm.write(self.object + 0x28, b'\xff')
        self.arm.write(self.object + 0x2e, struct.pack('<H', 3))
        self.arm.write(self.object + 0xb0, struct.pack('<I', self.point_table))
        self.arm.write(self.object + 0xe0, struct.pack('<I', self.output))

    def apply(self, matrix, point):
        return [add(add(add(mul(point[0], matrix[c]), mul(point[1], matrix[c + 4])), mul(point[2], matrix[c + 8])),
                    matrix[c + 12]) for c in range(3)]

    def expected(self):
        root, bone0, bone1 = self.matrices
        first = self.apply(root, self.points[0])
        second = self.apply(bone1, self.points[1])
        third = [0.0, 0.0, 0.0]
        for weight, matrix in zip(self.weights, (bone0, bone1)):
            value = self.apply(matrix, self.points[2])
            third = [add(third[c], mul(value[c], weight)) for c in range(3)]
        return first + second + second + third

    def test_skinning_duplicates_and_serial_bookkeeping(self):
        self.arm.call(TRANS, self.deformer, self.object)
        self.assertEqual(read_floats(self.arm, self.output, 12), self.expected())
        # The serial wraps from 0xff past zero to one; the stamp is recorded.
        self.assertEqual(self.arm.read(self.object + 0x28, 2), b'\x01\x01')
        self.assertEqual(self.arm.read(self.object + 0x200, 1), b'\x01')
        self.assertEqual(self.arm.read(self.object + 0x1fc, 1), b'\x07')
        self.assertEqual(self.math.metrics()[TRANS]['handled'], 1)

    def test_matching_stamp_leaves_points_untouched(self):
        self.arm.write(self.object + 0x1fc, b'\x07')
        self.arm.call(TRANS, self.deformer, self.object)
        self.assertEqual(self.arm.read(self.output, 48), bytes(48))
        self.assertEqual(self.arm.read(self.object + 0x28, 1), b'\xff')

    def test_output_overlapping_inputs_runs_the_original(self):
        self.arm.write(self.object + 0xe0, struct.pack('<I', self.point_table + 12))
        self.arm.call(TRANS, self.deformer, self.object)
        self.assertEqual(self.arm.read(self.object + 0x300, 1), b'\xa5')
        self.assertEqual(self.math.metrics()[TRANS]['fallbacks'], 1)


def vector(arm, values):
    return floats(arm, [f32(v) for v in values])


class CrossPlaneTests(unittest.TestCase):
    """Plane y = 5: normal (0, 1, 0) and integer offset -5."""

    def setUp(self):
        self.arm, self.math = runtime()
        self.addCleanup(self.arm.close)
        self.plane = self.arm.alloc(16)
        self.arm.write(self.plane, struct.pack('<3fi', 0, 1, 0, -5))

    def cross(self, p, q):
        return self.arm.call(CROSS, self.plane, vector(self.arm, p), vector(self.arm, q))

    def test_same_side_is_zero_and_crossing_or_touching_is_one(self):
        self.assertEqual(self.cross([0, 10, 0], [3, 7, -2]), 0)
        self.assertEqual(self.cross([0, -1, 0], [1, 4, 1]), 0)
        self.assertEqual(self.cross([0, 10, 0], [0, 2, 0]), 1)
        self.assertEqual(self.cross([0, 5, 0], [0, 9, 0]), 1)   # on the plane
        self.assertEqual(self.math.metrics()[CROSS]['handled'], 4)

    def test_denormal_point_runs_the_original(self):
        point = self.arm.alloc(12)
        self.arm.write(point, struct.pack('<III', 0, DENORMAL, 0))
        self.assertEqual(self.arm.call(CROSS, self.plane, point, vector(self.arm, [0, 1, 0])), MARKER)
        self.assertEqual(self.math.metrics()[CROSS]['fallbacks'], 1)


class DistanceTests(unittest.TestCase):
    def setUp(self):
        self.arm, self.math = runtime()
        self.addCleanup(self.arm.close)

    def distance(self, a, b):
        return self.arm.call(DISTANCE, vector(self.arm, a), vector(self.arm, b))

    def test_distance_uses_the_engine_table_square_root(self):
        generator = random.Random(5)
        for _ in range(200):
            a = [f32(generator.uniform(-300, 300)) for _ in range(3)]
            b = [f32(generator.uniform(-300, 300)) for _ in range(3)]
            d = [f32(b[i] - a[i]) for i in range(3)]
            squared = add(add(mul(d[0], d[0]), mul(d[1], d[1])), mul(d[2], d[2]))
            self.assertEqual(self.distance(a, b), reference_sqrt(bits(squared)))
        self.assertEqual(self.math.metrics()[DISTANCE]['handled'], 200)

    def test_equal_points_take_the_scaled_retry_and_return_zero(self):
        self.assertEqual(self.distance([1.5, -2, 3], [1.5, -2, 3]), 0)
        self.assertEqual(self.math.metrics()[DISTANCE]['handled'], 1)

    def test_underflowing_squares_run_the_original(self):
        self.assertEqual(self.distance([0, 0, 0], [1e-25, 0, 0]), MARKER)
        self.assertEqual(self.math.metrics()[DISTANCE]['fallbacks'], 1)


class InsideTriangleTests(unittest.TestCase):
    def setUp(self):
        self.arm, self.math = runtime()
        self.addCleanup(self.arm.close)

    def triangle(self, normal, *vertices):
        pointer = self.arm.alloc(0x34)
        self.arm.write(pointer, struct.pack('<3fi9f', *normal, 0, *sum(vertices, [])))
        return pointer

    def inside(self, triangle, p):
        return self.arm.call(INSIDE, triangle, vector(self.arm, p))

    def test_each_dominant_axis_projects_onto_the_other_two(self):
        floor = self.triangle([0, 1, 0], [0, 0, 0], [10, 0, 0], [0, 0, 10])  # y: tests x and z
        self.assertEqual(self.inside(floor, [1, 50, 1]), 1)
        self.assertEqual(self.inside(floor, [8, 0, 8]), 0)
        self.assertEqual(self.inside(floor, [5, 0, 0]), 1)  # on an edge
        wall = self.triangle([-1, 0, 0], [0, 0, 0], [0, 10, 0], [0, 0, 10])  # x: tests y and z
        self.assertEqual(self.inside(wall, [-3, 2, 2]), 1)
        self.assertEqual(self.inside(wall, [0, -1, 2]), 0)
        facing = self.triangle([0, 0.6, -0.8], [0, 0, 0], [0, 10, 0], [10, 0, 0])  # z: tests x and y
        self.assertEqual(self.inside(facing, [2, 2, 9]), 1)
        self.assertEqual(self.inside(facing, [9, 9, 0]), 0)
        # Either winding counts as inside.
        reversed_floor = self.triangle([0, 1, 0], [0, 0, 0], [0, 0, 10], [10, 0, 0])
        self.assertEqual(self.inside(reversed_floor, [1, 0, 1]), 1)
        self.assertEqual(self.math.metrics()[INSIDE]['handled'], 8)

    def test_denormal_vertex_runs_the_original(self):
        floor = self.triangle([0, 1, 0], [0, 0, 0], [10, 0, 0], [0, 0, 10])
        self.arm.w32(floor + 0x10, DENORMAL)
        self.assertEqual(self.inside(floor, [1, 0, 1]), MARKER)
        self.assertEqual(self.math.metrics()[INSIDE]['fallbacks'], 1)


class CrossSphereTests(unittest.TestCase):
    """Sphere of radius 2 at the origin."""

    def setUp(self):
        self.arm, self.math = runtime()
        self.addCleanup(self.arm.close)
        self.sphere = self.arm.alloc(16)
        self.arm.write(self.sphere, struct.pack('<3fi', 0, 0, 0, 2))

    def cross(self, p, v):
        return single(self.arm.call(SPHERE, self.sphere, vector(self.arm, p), vector(self.arm, v)))

    def root(self, b, discriminant, a):
        """|(-b - sqrt(discriminant)) / 2a| with the engine's table root."""
        return abs(f32((-b - single(reference_sqrt(bits(discriminant)))) / f32(a + a)))

    def test_nearer_root_misses_and_rays_starting_beyond(self):
        # A = 1, B = -10 (or 10), C = 25 - 4, discriminant 100 - 84.
        self.assertEqual(self.cross([-5, 0, 0], [1, 0, 0]), self.root(-10.0, 16.0, 1.0))
        self.assertEqual(self.cross([-5, 5, 0], [1, 0, 0]), -1.0)
        self.assertEqual(self.cross([-5, 0, 0], [0, 0, 0]), -1.0)
        self.assertEqual(self.cross([5, 0, 0], [1, 0, 0]), self.root(10.0, 16.0, 1.0))
        self.assertEqual(self.math.metrics()[SPHERE]['handled'], 4)

    def test_infinite_direction_runs_the_original(self):
        self.assertEqual(self.arm.call(SPHERE, self.sphere, vector(self.arm, [1, 0, 0]),
                                       vector(self.arm, [float('inf'), 0, 0])), MARKER)
        self.assertEqual(self.math.metrics()[SPHERE]['fallbacks'], 1)


class PlaneCrossPointTests(unittest.TestCase):
    """Plane y = 5, as in CrossPlaneTests."""

    def setUp(self):
        self.arm, self.math = runtime()
        self.addCleanup(self.arm.close)
        self.plane = self.arm.alloc(16)
        self.arm.write(self.plane, struct.pack('<3fi', 0, 1, 0, -5))
        self.out = vector(self.arm, [9, 9, 9])

    def test_meeting_point_is_written_and_t_returned(self):
        result = self.arm.call(PLANE_POINT, self.out, self.plane, vector(self.arm, [1, 0, 2]), vector(self.arm, [0, 2, 0]))
        self.assertEqual(single(result), 2.5)
        self.assertEqual(read_floats(self.arm, self.out, 3), [1.0, 5.0, 2.0])

    def test_parallel_ray_returns_minus_one_without_writing(self):
        result = self.arm.call(PLANE_POINT, self.out, self.plane, vector(self.arm, [1, 0, 2]), vector(self.arm, [1, 0, 0]))
        self.assertEqual(single(result), -1.0)
        self.assertEqual(read_floats(self.arm, self.out, 3), [9.0, 9.0, 9.0])
        self.assertEqual(self.math.metrics()[PLANE_POINT]['handled'], 1)

    def test_output_partly_over_the_origin_runs_the_original(self):
        origin = vector(self.arm, [1, 0, 2, 0])
        self.assertEqual(self.arm.call(PLANE_POINT, origin + 4, self.plane, origin, vector(self.arm, [0, 2, 0])), MARKER)


class LineNearestPointTests(unittest.TestCase):
    """Segment from (0, 0, 0) to (10, 0, 0)."""

    def setUp(self):
        self.arm, self.math = runtime()
        self.addCleanup(self.arm.close)
        self.a, self.b = vector(self.arm, [0, 0, 0]), vector(self.arm, [10, 0, 0])

    def nearest(self, p):
        out = vector(self.arm, [0, 0, 0])
        result = self.arm.call(LINE_POINT, out, vector(self.arm, p), self.a, self.b)
        return result, read_floats(self.arm, out, 3)

    def expected_distance(self, p, q):
        d = [f32(q[i] - p[i]) for i in range(3)]
        return reference_sqrt(bits(add(add(mul(d[0], d[0]), mul(d[1], d[1])), mul(d[2], d[2]))))

    def test_interior_and_clamped_ends(self):
        for p, point in (([4, 3, 0], [4.0, 0.0, 0.0]), ([-5, 1, 0], [0.0, 0.0, 0.0]), ([20, 1, 0], [10.0, 0.0, 0.0])):
            result, out = self.nearest(p)
            self.assertEqual(out, point, p)
            self.assertEqual(result, self.expected_distance([f32(v) for v in p], point), p)
        self.assertEqual(self.math.metrics()[LINE_POINT]['handled'], 3)

    def test_output_over_the_point_runs_the_original(self):
        p = vector(self.arm, [4, 3, 0])
        self.assertEqual(self.arm.call(LINE_POINT, p, p, self.a, self.b), MARKER)
        self.assertEqual(self.math.metrics()[LINE_POINT]['fallbacks'], 1)


class InstallTests(unittest.TestCase):
    def test_unexpected_entry_bytes_are_rejected(self):
        arm = ArmRuntime()
        self.addCleanup(arm.close)
        address = arm.base + 1024 * 1024
        for name in FUNCTIONS:
            arm.write(address, b'\x00\xbf\x00\xbf')
            arm.symbols[name] = address | 1
            address += 16
        with self.assertRaisesRegex(RuntimeError, 'Unexpected native math code'):
            NativeMath(arm).install()

    def test_a_different_square_root_routine_is_rejected(self):
        arm, math = runtime()
        self.addCleanup(arm.close)
        math.close()
        arm.native_math = None
        arm.w32((arm.symbols[SQRT] & ~1) + 0x70, 0)
        with self.assertRaisesRegex(RuntimeError, f'Unexpected native math code at {SQRT}'):
            native_math.sqrt_entry(arm)


if __name__ == '__main__':
    unittest.main()
