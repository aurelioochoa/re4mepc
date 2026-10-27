//! Host implementations of the engine's hottest soft-float math functions.
//!
//! The supported engine has no hardware float ABI: every multiply and add in
//! these functions is a libgcc call, and they account for most guest work per
//! gameplay tick. Each function's entry branches to a Thumb trampoline whose
//! first instruction (`bx lr`) carries a Unicorn code hook. The hook computes
//! the result here, writes it to guest memory and lets `bx lr` return to the
//! caller. Python (re4pc/native_math.py) builds the trampolines.
//!
//! Float operations accept exactly the domain in which the engine's VFP
//! helpers are verified equal to libgcc (tools/verify_softfloat.py): normal or
//! zero operands, normal results, exact-zero sums and zero products of a zero
//! operand. Anything else, an invalid pointer or a write that would alias a
//! later read returns `None` before any guest write, and the original ARM
//! routine runs instead. Shadow mode always runs the original and compares its
//! memory and R0 with the host result.
use std::collections::HashMap;
use std::ffi::{c_int, c_void};

type HookAdd = unsafe extern "C" fn(*mut c_void, *mut usize, c_int, *mut c_void, *mut c_void, u64, u64, ...) -> c_int;
type HookDel = unsafe extern "C" fn(*mut c_void, usize) -> c_int;
type RegAccess = unsafe extern "C" fn(*mut c_void, c_int, *mut c_void) -> c_int;

const UC_HOOK_CODE: c_int = 1 << 2;
const UC_ARM_REG_PC: c_int = 11;
const UC_ARM_REG_R0: c_int = 66;
const UC_ARM_REG_R1: c_int = 67;
const UC_ARM_REG_R2: c_int = 68;
const UC_ARM_REG_R3: c_int = 69;
const FUNCTIONS: usize = 9;
const ONE: u32 = 0x3f80_0000;
const TWO_POWER_EIGHT: u32 = 0x4380_0000; // 256.0
const MINUS_ONE: u32 = 0xbf80_0000;
const MINUS_FOUR: u32 = 0xc080_0000;
const SIGN: u32 = 0x8000_0000;

// ---- Soft-float domain --------------------------------------------------

fn is_zero(x: u32) -> bool { x << 1 == 0 }
fn is_normal(x: u32) -> bool { let e = (x >> 23) & 0xff; e != 0 && e != 0xff }
fn operand(x: u32) -> bool { is_zero(x) || is_normal(x) }

fn add(a: u32, b: u32) -> Option<u32> {
    if !operand(a) || !operand(b) { return None; }
    let r = (f32::from_bits(a) + f32::from_bits(b)).to_bits();
    // Normal operands cannot round to zero: a zero sum is exact cancellation.
    (is_zero(r) || is_normal(r)).then_some(r)
}

fn mul(a: u32, b: u32) -> Option<u32> {
    if !operand(a) || !operand(b) { return None; }
    let r = (f32::from_bits(a) * f32::from_bits(b)).to_bits();
    // A zero product of nonzero operands is an underflow.
    (is_normal(r) || (is_zero(r) && (is_zero(a) || is_zero(b)))).then_some(r)
}

// libgcc subtraction negates the second operand and adds.
fn sub(a: u32, b: u32) -> Option<u32> { add(a, b ^ 0x8000_0000) }

fn div(a: u32, b: u32) -> Option<u32> {
    if !operand(a) || !operand(b) { return None; }
    let r = (f32::from_bits(a) / f32::from_bits(b)).to_bits();
    // A zero quotient of a nonzero dividend is an underflow.
    (is_normal(r) || (is_zero(r) && is_zero(a))).then_some(r)
}

// __aeabi_i2f rounds to nearest, as Rust's conversion does.
fn i2f(x: u32) -> u32 { (x as i32 as f32).to_bits() }

// The __aeabi_fcmp* family matches IEEE comparison for every input, including NaN and -0.
fn fcmpeq(a: u32, b: u32) -> bool { f32::from_bits(a) == f32::from_bits(b) }
fn fcmplt(a: u32, b: u32) -> bool { f32::from_bits(a) < f32::from_bits(b) }
fn fcmple(a: u32, b: u32) -> bool { f32::from_bits(a) <= f32::from_bits(b) }
fn fcmpge(a: u32, b: u32) -> bool { f32::from_bits(a) >= f32::from_bits(b) }
fn fcmpgt(a: u32, b: u32) -> bool { f32::from_bits(a) > f32::from_bits(b) }

// ---- Guest memory: the ARM mapping shares host addresses ----------------

struct Memory { start: u64, end: u64 }

impl Memory {
    fn valid(&self, address: u32, bytes: u64) -> bool {
        address as u64 >= self.start && address as u64 + bytes <= self.end
    }
    fn u8(&self, address: u32) -> Option<u8> {
        // SAFETY: the range lies inside the live guest mapping.
        self.valid(address, 1).then(|| unsafe { *(address as usize as *const u8) })
    }
    fn u16(&self, address: u32) -> Option<u16> {
        self.valid(address, 2).then(|| unsafe { (address as usize as *const u16).read_unaligned() })
    }
    fn u32(&self, address: u32) -> Option<u32> {
        self.valid(address, 4).then(|| unsafe { (address as usize as *const u32).read_unaligned() })
    }
    fn vector(&self, address: u32) -> Option<[u32; 3]> {
        Some([self.u32(address)?, self.u32(address + 4)?, self.u32(address + 8)?])
    }
}

fn overlaps(a: (u32, u32), b: (u32, u32)) -> bool { a.0 < b.1 && b.0 < a.1 }

/// Guest writes in the original routine's order, plus an optional R0 result.
#[derive(Default)]
struct Effects { words: Vec<(u32, u32)>, bytes: Vec<(u32, u8)>, result: Option<u32> }

impl Effects {
    /// A byte as the original routine would read it after this plan's byte writes.
    fn byte(&self, memory: &Memory, address: u32) -> Option<u8> {
        self.bytes.iter().rev().find(|w| w.0 == address).map(|w| w.1).or_else(|| memory.u8(address))
    }
}

// ---- mceVector3D_dot(a, b) ----------------------------------------------

fn dot_values(a: [u32; 3], b: [u32; 3]) -> Option<u32> {
    add(add(mul(a[0], b[0])?, mul(a[1], b[1])?)?, mul(a[2], b[2])?)
}

fn dot(m: &Memory, a: u32, b: u32) -> Option<Effects> {
    Some(Effects { result: Some(dot_values(m.vector(a)?, m.vector(b)?)?), ..Effects::default() })
}

fn difference(a: [u32; 3], b: [u32; 3]) -> Option<[u32; 3]> {
    Some([sub(a[0], b[0])?, sub(a[1], b[1])?, sub(a[2], b[2])?])
}

/// The three words written at `out` from `origin + Mul(t, direction)`, in
/// order. Each component is written before the next is read, which is
/// equivalent only when `out` equals or avoids each read vector.
fn along(out: u32, origin: [u32; 3], direction: [u32; 3], t: u32) -> Option<Vec<(u32, u32)>> {
    let mut words = Vec::with_capacity(3);
    for c in 0..3 { words.push((out + 4 * c as u32, add(origin[c], mul(t, direction[c])?)?)); }
    Some(words)
}

fn aliases(out: u32, read: u32) -> bool { out != read && overlaps((out, out + 12), (read, read + 12)) }

// ---- mceUtil3D_sqrt(x): table interpolation on the float's bits ---------

/// `entry` is the routine's Thumb address; Python checks its bytes, which
/// hold the table offset and both constants PC-relative to the entry.
fn sqrt(m: &Memory, entry: u32, v: u32) -> Option<u32> {
    if fcmple(v, 0) { return Some(0); }
    let table = m.u32(entry + 0x6c)?.wrapping_add(entry + 0x22 + 0x60);
    let exponent = (v << 1) >> 24;
    let row = table.wrapping_add(12 * ((v << 9) >> 29));
    let fraction = (v << 12) >> 19;
    let slope = m.u32(row + 4)?.wrapping_sub(m.u32(row + 8)?.wrapping_mul(fraction) >> 2) >> 16;
    let root = m.u32(row)?.wrapping_add(0x8000).wrapping_add(slope.wrapping_mul(fraction)) >> 16;
    let mantissa = if exponent & 1 != 0 { root << 14 }
                   else { (root.wrapping_mul(m.u32(entry + 0x70)?) >> 1).wrapping_add(m.u32(entry + 0x74)?) };
    let halved = exponent.wrapping_sub(exponent.wrapping_sub(0x7e) >> 1);
    Some(mantissa >> 8 | halved << 23)
}

// ---- ERP_CalcVec::Get_Dis_Pos(a, b) --------------------------------------

fn length(m: &Memory, sqrt_entry: u32, d: [u32; 3]) -> Option<u32> {
    sqrt(m, sqrt_entry, add(add(mul(d[0], d[0])?, mul(d[1], d[1])?)?, mul(d[2], d[2])?)?)
}

fn distance_values(m: &Memory, sqrt_entry: u32, a: [u32; 3], b: [u32; 3]) -> Option<u32> {
    let d = difference(b, a)?;
    let result = length(m, sqrt_entry, d)?;
    if !fcmpeq(result, 0) { return Some(result); }
    // Retry scaled by 256 so tiny differences keep precision.
    let scaled = [mul(d[0], TWO_POWER_EIGHT)?, mul(d[1], TWO_POWER_EIGHT)?, mul(d[2], TWO_POWER_EIGHT)?];
    div(length(m, sqrt_entry, scaled)?, TWO_POWER_EIGHT)
}

fn distance(m: &Memory, sqrt_entry: u32, a: u32, b: u32) -> Option<Effects> {
    let result = distance_values(m, sqrt_entry, m.vector(a)?, m.vector(b)?)?;
    Some(Effects { result: Some(result), ..Effects::default() })
}

// ---- GM_Util_Collision::Check_ReiCrossPlane(plane, p, q) ----------------

/// 0 when both points lie strictly on the same side of the plane, else 1.
fn cross_plane(m: &Memory, plane: u32, p: u32, q: u32) -> Option<Effects> {
    let offset = i2f(m.u32(plane + 0xc)?);
    let a = add(dot(m, plane, p)?.result?, offset)?;
    let b = add(dot(m, plane, q)?.result?, offset)?;
    let same_side = (fcmpgt(a, 0) && fcmpgt(b, 0)) || (fcmplt(a, 0) && fcmplt(b, 0));
    Some(Effects { result: Some(!same_side as u32), ..Effects::default() })
}

// ---- GM_Util_Collision::Check_InsideTriangle(triangle, p) ---------------

/// Projects onto the plane of the two axes other than the normal's largest
/// component and tests p against each edge. 1 when p is inside or on an
/// edge (all edge values share a sign), else 0. Vertices start at +0x10.
fn inside_triangle(m: &Memory, triangle: u32, p: u32) -> Option<Effects> {
    let magnitude = |i: u32| m.u32(triangle + 4 * i).map(|x| if fcmplt(x, 0) { x ^ 0x8000_0000 } else { x });
    let (x, y, z) = (magnitude(0)?, magnitude(1)?, magnitude(2)?);
    let (i, j) = if fcmplt(x, y) { if fcmplt(y, z) { (0, 1) } else { (0, 2) } }
                 else if fcmplt(x, z) { (0, 1) } else { (1, 2) };
    let point = |c: u32| m.u32(p + 4 * c);
    let vertex = |k: u32, c: u32| m.u32(triangle + 0x10 + 12 * k + 4 * c);
    let mut edges = [0u32; 3];
    for (edge, (a, b)) in [(0, 1), (1, 2), (2, 0)].into_iter().enumerate() {
        edges[edge] = sub(mul(sub(point(i)?, vertex(a, i)?)?, sub(point(j)?, vertex(b, j)?)?)?,
                          mul(sub(point(j)?, vertex(a, j)?)?, sub(point(i)?, vertex(b, i)?)?)?)?;
    }
    let inside = edges.iter().all(|&e| fcmpge(e, 0)) || edges.iter().all(|&e| fcmple(e, 0));
    Some(Effects { result: Some(inside as u32), ..Effects::default() })
}

// ---- GM_Util_Collision::Check_ReiCrossSphere(sphere, p, v) --------------

/// The smaller root t of |p + t v - centre| = radius (an integer at +0xc),
/// made non-negative, or -1 when the ray misses or v is zero.
fn cross_sphere(m: &Memory, sqrt_entry: u32, sphere: u32, p: u32, v: u32) -> Option<Effects> {
    let v = m.vector(v)?;
    let w = difference(m.vector(p)?, m.vector(sphere)?)?;
    let a = dot_values(v, v)?;
    let half_b = dot_values(w, v)?;
    let b = add(half_b, half_b)?;
    let radius = i2f(m.u32(sphere + 0xc)?);
    let c = sub(dot_values(w, w)?, mul(radius, radius)?)?;
    let discriminant = add(mul(b, b)?, mul(mul(a, c)?, MINUS_FOUR)?)?;
    let result = if fcmplt(discriminant, 0) || fcmple(a, 0) { MINUS_ONE } else {
        let t = div(sub(b ^ SIGN, sqrt(m, sqrt_entry, discriminant)?)?, add(a, a)?)?;
        if fcmplt(t, 0) { t ^ SIGN } else { t }
    };
    Some(Effects { result: Some(result), ..Effects::default() })
}

// ---- GM_Util_Collision::Set_ReiPlane_CrossPoint(out, plane, p, v) -------

/// Where the ray p + t v meets the plane: writes it and returns t, or
/// returns -1 without writing when v is parallel to the plane.
fn plane_cross_point(m: &Memory, out: u32, plane: u32, p: u32, v: u32) -> Option<Effects> {
    let normal = m.vector(plane)?;
    let (origin, direction) = (m.vector(p)?, m.vector(v)?);
    let along_normal = dot_values(normal, direction)?;
    let start = dot_values(normal, origin)?;
    if fcmpeq(along_normal, 0) {
        return Some(Effects { result: Some(MINUS_ONE), ..Effects::default() });
    }
    if !m.valid(out, 12) || aliases(out, p) || aliases(out, v) { return None; }
    let t = div(add(i2f(m.u32(plane + 0xc)?), start)? ^ SIGN, along_normal)?;
    Some(Effects { words: along(out, origin, direction, t)?, bytes: Vec::new(), result: Some(t) })
}

// ---- GM_Util_Collision::Get_PointCrossLinePt(out, p, a, b) --------------

/// The point of segment ab nearest p: writes it and returns its distance.
fn line_nearest_point(m: &Memory, sqrt_entry: u32, out: u32, p: u32, a: u32, b: u32) -> Option<Effects> {
    let (point, start) = (m.vector(p)?, m.vector(a)?);
    let d = difference(m.vector(b)?, start)?;
    let projection = dot_values(difference(point, start)?, d)?;
    let squared = dot_values(d, d)?;
    let mut t = if fcmple(squared, 0) { 0 } else { div(projection, squared)? };
    if fcmplt(t, 0) { t = 0; } else if fcmpgt(t, ONE) { t = ONE; }
    // The distance re-reads p after the writes.
    if !m.valid(out, 12) || aliases(out, a) || overlaps((out, out + 12), (p, p + 12)) { return None; }
    let words = along(out, start, d, t)?;
    let nearest = [words[0].1, words[1].1, words[2].1];
    let result = distance_values(m, sqrt_entry, point, nearest)?;
    Some(Effects { words, bytes: Vec::new(), result: Some(result) })
}

// ---- _mceBoneDeformer_transPoints(deformer, object) ---------------------

/// Row `c` of a 4x4 column-major matrix applied to a point: ((x*m + y*m) + z*m) + t.
fn transform(m: &Memory, matrix: u32, p: (u32, u32, u32), c: u32) -> Option<u32> {
    let e = |i: u32| m.u32(matrix + 4 * i);
    add(add(add(mul(p.0, e(c)?)?, mul(p.1, e(c + 4)?)?)?, mul(p.2, e(c + 8)?)?)?, e(c + 12)?)
}

fn transform_point(m: &Memory, matrix: u32, p: (u32, u32, u32)) -> Option<[u32; 3]> {
    Some([transform(m, matrix, p, 0)?, transform(m, matrix, p, 1)?, transform(m, matrix, p, 2)?])
}

fn trans_points(m: &Memory, deformer: u32, object: u32) -> Option<Effects> {
    let skeleton = m.u32(deformer + 0x4c)?;
    let mut duplicates = m.u32(deformer + 0x24)?;
    let mut influence = m.u32(deformer + 0x28)?;
    let matrices = m.u32(skeleton + 4)?;
    let stamp = m.u8(skeleton + 0x10)?;
    let mut point = m.u32(object + 0xb0)?;
    let end = point.checked_add(m.u16(object + 0x2e)? as u32 * 12)?;
    let mut out = m.u32(object + 0xe0)?;
    let mut effects = Effects::default();
    if m.u8(object + 0x1fc)? == stamp {
        return Some(effects);
    }
    let (first_point, first_duplicate, first_influence, first_out) = (point, duplicates, influence, out);
    // Bone transforms are 17 words; transform k + 1 belongs to bone k.
    let bone = |index: u8| matrices + 4 * (index as u32 * 17 + 17);
    let mut matrix_words = 16;
    let mut influence_end = first_influence;
    while point < end {
        let p = (m.u32(point)?, m.u32(point + 4)?, m.u32(point + 8)?);
        let count = m.u8(influence + 0x14)? as u32;
        // Weights at +4i and bone indices at +0x10+i, even past the record for large counts.
        influence_end = influence_end.max(influence + 0x15).max(influence + 4 * count).max(influence + 0x10 + count);
        let value = match count {
            0 => transform_point(m, matrices, p)?,
            1 => {
                let index = m.u8(influence + 0x10)?;
                matrix_words = matrix_words.max(index as u32 * 17 + 33);
                transform_point(m, bone(index), p)?
            }
            _ => {
                let mut sum = [0u32; 3];
                for i in 0..count {
                    let weight = m.u32(influence + 4 * i)?;
                    let index = m.u8(influence + 0x10 + i)?;
                    matrix_words = matrix_words.max(index as u32 * 17 + 33);
                    let v = transform_point(m, bone(index), p)?;
                    for c in 0..3 { sum[c] = add(sum[c], mul(v[c], weight)?)?; }
                }
                sum
            }
        };
        for _ in 0..m.u8(duplicates)? {
            if !m.valid(out, 12) { return None; }
            effects.words.extend([(out, value[0]), (out + 4, value[1]), (out + 8, value[2])]);
            out += 12;
        }
        influence += 0x18;
        duplicates += 1;
        point += 12;
    }
    // The original writes each output as it goes; deferring is equivalent
    // only when no output overlaps anything the routine reads.
    let reads = [(first_point, end), (first_duplicate, duplicates), (first_influence, influence_end),
                 (matrices, matrices + 4 * matrix_words), (deformer + 0x24, deformer + 0x50),
                 (object + 0x28, object + 0x30), (object + 0xb0, object + 0xb4), (object + 0xe0, object + 0xe4),
                 (object + 0x1fc, object + 0x201), (skeleton + 4, skeleton + 0x11)];
    if out > first_out && reads.iter().any(|&r| overlaps((first_out, out), r)) {
        return None;
    }
    let mut serial = m.u8(object + 0x28)?.wrapping_add(1);
    if serial == 0 { serial = 1; }
    effects.bytes.extend([(object + 0x28, serial), (object + 0x29, serial), (object + 0x200, 1), (object + 0x1fc, stamp)]);
    Some(effects)
}

// ---- _mceTransform_multiply2(out, a, b) ---------------------------------

/// _mceTransform_isIdentity: compares lazily and caches the answer at +0x40.
fn is_identity(m: &Memory, transform: u32, effects: &mut Effects) -> Option<bool> {
    let cached = effects.byte(m, transform + 0x40)?;
    if cached != 0 {
        return Some(cached == 1);
    }
    for i in 0..16 {
        if !fcmpeq(m.u32(transform + 4 * i)?, if i % 5 == 0 { ONE } else { 0 }) {
            effects.bytes.push((transform + 0x40, 2));
            return Some(false);
        }
    }
    effects.bytes.extend([(transform + 0x40, 1), (transform + 0x41, 1), (transform + 0x42, 1)]);
    Some(true)
}

fn multiply2(m: &Memory, out: u32, a: u32, b: u32) -> Option<Effects> {
    if ![out, a, b].iter().all(|&p| m.valid(p, 0x43)) { return None; }
    let span = |p: u32| (p, p + 0x43);
    // Partial overlaps would interleave reads and writes differently.
    if (out != a && overlaps(span(out), span(a))) || (out != b && overlaps(span(out), span(b))) {
        return None;
    }
    // Cache writes made by isIdentity are idempotent, so a later fallback
    // that repeats them observes the same answers.
    let mut effects = Effects::default();
    let source = if is_identity(m, a, &mut effects)? { Some(b) }
                 else if is_identity(m, b, &mut effects)? { Some(a) } else { None };
    if let Some(source) = source {
        // _mceTransform_copy
        for i in 0..16 { effects.words.push((out + 4 * i, m.u32(source + 4 * i)?)); }
        for offset in [0x40, 0x41, 0x42] {
            let value = effects.byte(m, source + offset)?;
            effects.bytes.push((out + offset, value));
        }
        return Some(effects);
    }
    let x = |i: u32| m.u32(a + 4 * i);
    let y = |i: u32| m.u32(b + 4 * i);
    let row = |p: (u32, u32, u32), c: u32| -> Option<u32> {
        add(add(mul(p.0, x(c)?)?, mul(p.1, x(c + 4)?)?)?, mul(p.2, x(c + 8)?)?)
    };
    let mut r = [0u32; 16];
    for column in [0, 4, 8, 12] {
        let p = (y(column)?, y(column + 1)?, y(column + 2)?);
        for c in 0..3 {
            let value = row(p, c)?;
            r[(column + c) as usize] = if column == 12 { add(value, x(12 + c)?)? } else { value };
        }
    }
    r[15] = ONE;
    for (i, value) in r.iter().enumerate() { effects.words.push((out + 4 * i as u32, *value)); }
    effects.bytes.push((out + 0x40, 0));
    // The flags are read after the matrix and +0x40 writes, which never touch
    // +0x41/+0x42 of an aliased input.
    for offset in [0x41, 0x42] {
        let both = effects.byte(m, a + offset)? == 1 && effects.byte(m, b + offset)? == 1;
        effects.bytes.push((out + offset, both as u8));
    }
    Some(effects)
}

// ---- Unicorn hooks ------------------------------------------------------

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct Counters { handled: u64, fallbacks: u64, verified: u64, mismatches: u64 }

/// Trampoline addresses for one function, all Thumb instruction addresses.
#[derive(Clone, Copy)]
struct Site { hook: u32, shadow_call: u32, shadow_return: u32, original: u32 }

pub struct Bridge {
    uc: *mut c_void, delete: HookDel, read: RegAccess, write: RegAccess,
    memory: Memory, sqrt_entry: u32, shadow: bool, hooks: Vec<usize>, sites: [Site; FUNCTIONS],
    pending: Vec<(usize, [u32; 4], Option<Effects>)>, counters: [Counters; FUNCTIONS],
    mismatch_arguments: [[u32; 4]; FUNCTIONS],
}

impl Bridge {
    unsafe fn register(&self, id: c_int) -> u32 {
        let mut value = 0u32;
        (self.read)(self.uc, id, &mut value as *mut u32 as *mut c_void);
        value
    }
    unsafe fn set_register(&self, id: c_int, value: u32) {
        let mut value = value;
        (self.write)(self.uc, id, &mut value as *mut u32 as *mut c_void);
    }
    fn compute(&self, function: usize, a: [u32; 4]) -> Option<Effects> {
        let m = &self.memory;
        match function {
            0 => trans_points(m, a[0], a[1]),
            1 => dot(m, a[0], a[1]),
            2 => multiply2(m, a[0], a[1], a[2]),
            3 => cross_plane(m, a[0], a[1], a[2]),
            4 => distance(m, self.sqrt_entry, a[0], a[1]),
            5 => inside_triangle(m, a[0], a[1]),
            6 => cross_sphere(m, self.sqrt_entry, a[0], a[1], a[2]),
            7 => plane_cross_point(m, a[0], a[1], a[2], a[3]),
            _ => line_nearest_point(m, self.sqrt_entry, a[0], a[1], a[2], a[3]),
        }
    }
}

extern "C" fn enter(_uc: *mut c_void, address: u64, _size: u32, user: *mut c_void) {
    // SAFETY: Unicorn passes back the Bridge registered with this hook.
    let bridge = unsafe { &mut *(user as *mut Bridge) };
    let Some(function) = bridge.sites.iter().position(|s| s.hook as u64 == address) else { return };
    unsafe {
        let arguments = [bridge.register(UC_ARM_REG_R0), bridge.register(UC_ARM_REG_R1),
                         bridge.register(UC_ARM_REG_R2), bridge.register(UC_ARM_REG_R3)];
        let effects = bridge.compute(function, arguments);
        if bridge.shadow {
            if effects.is_none() { bridge.counters[function].fallbacks += 1; }
            bridge.pending.push((function, arguments, effects));
            bridge.set_register(UC_ARM_REG_PC, bridge.sites[function].shadow_call | 1);
            return;
        }
        match effects {
            Some(effects) => {
                for &(address, value) in &effects.words { (address as usize as *mut u32).write_unaligned(value); }
                for &(address, value) in &effects.bytes { *(address as usize as *mut u8) = value; }
                if let Some(value) = effects.result { bridge.set_register(UC_ARM_REG_R0, value); }
                bridge.counters[function].handled += 1;
            }
            None => {
                bridge.counters[function].fallbacks += 1;
                bridge.set_register(UC_ARM_REG_PC, bridge.sites[function].original | 1);
            }
        }
    }
}

extern "C" fn shadow_return(_uc: *mut c_void, _address: u64, _size: u32, user: *mut c_void) {
    // SAFETY: as in `enter`.
    let bridge = unsafe { &mut *(user as *mut Bridge) };
    let Some((function, arguments, Some(effects))) = bridge.pending.pop() else { return };
    // Final contents per address: later writes win, bytes override words.
    let mut expected = HashMap::new();
    for &(address, value) in &effects.words {
        for k in 0..4 { expected.insert(address + k, (value >> (8 * k)) as u8); }
    }
    for &(address, value) in &effects.bytes { expected.insert(address, value); }
    let mut equal = expected.iter().all(|(&address, &value)| bridge.memory.u8(address) == Some(value));
    if let Some(value) = effects.result {
        equal &= unsafe { bridge.register(UC_ARM_REG_R0) } == value;
    }
    let counters = &mut bridge.counters[function];
    if equal {
        counters.verified += 1;
    } else {
        counters.mismatches += 1;
        if counters.mismatches == 1 { bridge.mismatch_arguments[function] = arguments; }
    }
}

/// Number of replaced functions, in the order of `sites` and the counters.
#[no_mangle]
pub extern "C" fn re4_math_functions() -> usize { FUNCTIONS }

/// `sites` holds four Thumb addresses per function: the hooked `bx lr`, the
/// shadow call sequence, its hooked return point and the relocated original.
/// `sqrt_entry` is the engine's mceUtil3D_sqrt, which distances call.
///
/// # Safety
/// `uc` must be a live engine and the hook functions Unicorn's own exports.
#[no_mangle]
pub unsafe extern "C" fn re4_math_open(uc: *mut c_void, hook_add: HookAdd, hook_del: HookDel, read: RegAccess,
                                       write: RegAccess, start: u64, bytes: u64, shadow: c_int,
                                       sites: *const u32, sqrt_entry: u32) -> *mut Bridge {
    let s = std::slice::from_raw_parts(sites, 4 * FUNCTIONS);
    let site = |i: usize| Site { hook: s[4 * i], shadow_call: s[4 * i + 1], shadow_return: s[4 * i + 2], original: s[4 * i + 3] };
    let bridge = Box::into_raw(Box::new(Bridge {
        uc, delete: hook_del, read, write, memory: Memory { start, end: start + bytes }, sqrt_entry, shadow: shadow != 0,
        hooks: Vec::new(), sites: std::array::from_fn(site), pending: Vec::new(),
        counters: [Counters::default(); FUNCTIONS], mismatch_arguments: [[0; 4]; FUNCTIONS],
    }));
    let b = &mut *bridge;
    for site in b.sites {
        let mut targets = vec![(site.hook, enter as *mut c_void)];
        if b.shadow { targets.push((site.shadow_return, shadow_return as *mut c_void)); }
        for (address, callback) in targets {
            let mut hook = 0usize;
            if hook_add(uc, &mut hook, UC_HOOK_CODE, callback, bridge as *mut c_void, address as u64, address as u64) != 0 {
                re4_math_close(bridge);
                return std::ptr::null_mut();
            }
            b.hooks.push(hook);
        }
    }
    bridge
}

/// # Safety
/// `bridge` must come from `re4_math_open`.
#[no_mangle]
pub unsafe extern "C" fn re4_math_counters(bridge: *const Bridge, function: usize) -> Counters {
    let b = &*bridge;
    b.counters.get(function).copied().unwrap_or_default()
}

/// Arguments of the first shadow mismatch (zero when none occurred).
///
/// # Safety
/// `bridge` must come from `re4_math_open`; `out` must hold four words.
#[no_mangle]
pub unsafe extern "C" fn re4_math_mismatch(bridge: *const Bridge, function: usize, out: *mut u32) {
    let b = &*bridge;
    let arguments = b.mismatch_arguments.get(function).copied().unwrap_or_default();
    std::ptr::copy_nonoverlapping(arguments.as_ptr(), out, 4);
}

/// mceUtil3D_sqrt on the live engine's table, for tools/verify_native_math.py.
///
/// # Safety
/// The range must be the live guest mapping, holding the checked routine.
#[no_mangle]
pub unsafe extern "C" fn re4_math_sqrt(start: u64, bytes: u64, sqrt_entry: u32, x: u32, out: *mut u32) -> c_int {
    match sqrt(&Memory { start, end: start + bytes }, sqrt_entry, x) {
        Some(value) => { *out = value; 1 }
        None => 0,
    }
}

/// # Safety
/// `bridge` must come from `re4_math_open` and the engine must still be live.
#[no_mangle]
pub unsafe extern "C" fn re4_math_close(bridge: *mut Bridge) {
    if bridge.is_null() { return; }
    let b = Box::from_raw(bridge);
    for &hook in &b.hooks { (b.delete)(b.uc, hook); }
}
