# FPS and graphics performance

After updating source, run `make build` once. Run interpolated gameplay at a
higher presentation rate:

```bash
make run ARGS="--fps 60"
make run ARGS="--fps 120"
make run ARGS="--fps 0"
```

The launcher offers the same options in Settings → Display & sensitivity →
Presentation rate. Supported targets are 20, 30, 60, 90, 120, 144, 165 and
240 FPS, plus Uncapped (`0`). Native 20 FPS remains the default and preserves
existing preferences. `--presentation-rate` is an alias for `--fps`.

## Save a preference or return to native presentation

`--fps` overrides the saved setting for that run only. To save 60 FPS from the
checkout, then launch using the saved preference:

```bash
make cli ARGS="settings --set presentation_rate 60"
make run
```

To save the original mode again, use
`make cli ARGS="settings --set presentation_rate 20"`. The launcher saves the
same `presentation_rate` setting, and changes apply on the next launch. Settings
live at `$XDG_CONFIG_HOME/re4mepc/settings.json`, or
`~/.config/re4mepc/settings.json` when that variable is unset.

The native graphics bridge is enabled in both native and interpolated modes.
For a comparison through the Python GL state-import path, run
`make run ARGS="--fps 60 --no-fast-graphics"`. To compare the original
presentation and Python state-import paths together, use
`make run ARGS="--fps 20 --no-fast-graphics"`.

These options describe the current source. The frozen
`v0.1.0-experimental.20261014` AppImage/archive predate this implementation;
their existing qualification does not cover the FPS feature. New distribution
builds require their own package checks.

## What higher FPS changes

The game still simulates at 20 Hz. Higher modes interpolate matching model/view
transforms and floating-point vertex/normal arrays, including animated geometry,
in a separate GL context on a presentation thread. They add up to 50 ms of visual
latency. Input, collision, damage, mission time and saves keep their native
cadence. Menus and movies use complete native frames; 30 FPS movies retain their
authored motion cadence. Uncapped presentation yields briefly between frames;
throughput still depends on CPU/GPU/driver limits.

## Inspect the running rate

F3 shows simulation Hz and presentation FPS separately. Periodic runtime logs
also report both. To retain a JSON report:

```bash
make run ARGS="--fps 60 --stats /tmp/re4-fps-stats.json"
```

The report is written when the game exits. `presentation_hz` is the requested
target (`0` means uncapped); `presentation.worker.recent_fps` and
`diagnostics.presentation_fps` are measured rates. `frames` still counts native
simulation ticks. Repeated menu/movie frames count as presentations, so that
counter alone does not prove interpolated gameplay motion. See the
[diagnostics field reference](diagnostics.md) for bridge and snapshot counters.

## Implementation

- `native/gl.c` forwards 40 frequent GL state imports directly from Unicorn to
  desktop GL, including matrix loads, pointers, material/lighting and texture
  parameters. It validates guest pointers and reports calls and CPU submission
  time in batches. It caches no GL state. Draws, resource uploads, queries and
  custom sights retain the Python bridge. `--no-fast-graphics` selects the old
  state-import path for comparisons. Import profiling and JSONL traces also use
  that path to retain complete per-call records.
- `native/render.c` owns copied draw data and fixed-function snapshots. Indices,
  textures, UVs, array layout and projection identify compatible submissions.
  Matching draws blend transforms and float geometry; incompatible draws snap.
  Large matrix changes, loading, resource updates and player lifecycle changes
  discard history. Buffers are bounded; invalid or oversized draws reject that
  snapshot. Original engine libraries and resources are unchanged.
- `re4pc/presentation.py` owns a shared GL context, its own framebuffer and a
  hidden native-render surface. A mutex protects snapshot publication. GPU
  fences synchronize resource publication and reuse. Three bounded textures
  transfer complete menu/movie frames without CPU pixel readback. Native GL
  state, input and guest memory remain on the engine thread.

The [REA investigation](rea-workflow.md#fps-and-graphics-investigation--2026-10-23)
used REA 6.4.0/Ghidra 12.1.4/JDK 21 against the supported library hash. Dossiers
and load-image observations were checked against ELF/Capstone entries. They
confirm the unconditional FPS check, consecutive framework exec/draw dispatch
and mission seconds per 20 active ticks. The host never repeats a native render
function to obtain extra FPS.

## Verification

`make check` covers real offscreen GL interpolation, immutable array ownership,
driver-state restoration, shared-context rendering, menu/movie handoff, bounded
inputs, all 40 accelerated GL imports, settings, CLI rates and existing behavior.

With the supported imported game available:

```bash
.venv/bin/python tools/test_presentation.py --output /tmp/re4-presentation
```

The test copies game inputs into a new external fixture with fresh saves. It
enters the existing synthetic mission-2 setup, checks walking/turning/aiming/
firing/holstering snapshots, compares native endpoint pixels and demonstrates
distinct intermediate motion. Hashes of all 256 MiB of guest memory and native
service counters must remain equal across extra presentations.

The FPS check enables a ten-minute countdown through the native
`GM_MisConduct::Set_LimitTime` API because this story mission normally leaves
its timer disabled. Each tested presentation rate must advance elapsed time and
countdown by exactly three seconds over 60 native ticks. A native stage
transition runs with presentation active. This synthetic fixture does not
qualify a full campaign or physical input devices.

## Native engine math — 2026-10-27

The supported engine has no hardware float ABI; every float multiply, add and
comparison is a libgcc call. A guest basic-block profile of the gameplay replay
attributed 55–60% of executed ARM instructions to those calls, about 205,000 per
tick, while GL submission and host services took under 1% of tick time. Three
routines in `libmc_eruption` issue about 60% of the calls:

| Routine | Share of soft-float calls | Work |
|---|---:|---|
| `_mceBoneDeformer_transPoints` | 34% | Skins points by up to N weighted bone matrices |
| `mceVector3D_dot` | 14% | Three-component dot product |
| `_mceTransform_multiply2` | 12% | Affine 4×4 product with identity shortcuts and cached flags |

REA/Ghidra decompilation showed pure arithmetic with ordered writes, so
`native/math.rs` reproduces each one with the same operation order. Its float
operations accept only the domain in which the existing VFP helpers equal
libgcc bit for bit; anything else, and any output that would alias an input,
runs the original routine. The replacement is on by default; use
`--no-native-math` to compare.

`make math-test` (or `tools/verify_native_math.py`) first runs the replay in
shadow mode, where every call executes the original routine and is compared
with the Rust result, then alternates timed runs with the replacements off and
on. On the reference host:

| Check | Result |
|---|---|
| Shadow-verified calls (transPoints / dot / multiply2) | 4,560 / 1,963,210 / 377,970 |
| Mismatches | 0 |
| Calls returned to the original routine | 7 multiply2 calls during loading |
| Gameplay tick work p50, off → on (two pairs) | 43.6 → 27.3 ms, 41.5 → 26.6 ms |
| Gameplay tick work p95, off → on | 49.2 → 31.4 ms, 46.7 → 29.8 ms |
| Busy loading time, title to village | 26.1 → 22.3 s, 25.1 → 21.4 s |

These figures come from the synthetic mission-2 fixture with SDL's offscreen
driver; desktop activity was uncontrolled. The longest loading frame (about
1 s) involves other routines and is unchanged.

### Collision math and comparisons

A later instruction-count sample of 300 village gameplay ticks, with helper
work charged to its caller, found the next costs in collision code and in the
libgcc comparison wrappers:

| Routine | Share of sampled ARM instructions |
|---|---:|
| `__aeabi_cfcmple` and the `fcmp*` wrappers around it | ~11% |
| `ERP_CalcMath::Mul` (a call to `__aeabi_fmul`) | 10.9% |
| `GM_Util_Collision` / `GM_Util_CollCheck` routines | ~30% |
| `ERP_CalcVec::Get_Dis_Pos` | 4.9% |

The `fcmp*` entries in `libmc_eruption` reached `__cmpsf2` through `cfcmple`
or `cfrcmple`, about 20 instructions per comparison. `re4pc/eabi.py` now
redirects all seven to VFP comparisons. For ordered operands VFP's NZCV equals
libgcc's; unordered operands set V, so those resume the original routine.
`cfrcmple` also returns with r0/r1 swapped, as the original does.
`tools/verify_softfloat.py` compares the flag-returning entries' NZCV and
r0–r3, not only R0: 252,116 cases each, 0 mismatches.

`native/math.rs` adds six `libbio4af` routines, each decompiled with Ghidra
12.1.4 and read instruction by instruction for operand order:
`Check_ReiCrossPlane`, `Check_InsideTriangle`, `Check_ReiCrossSphere`,
`Set_ReiPlane_CrossPoint`, `Get_PointCrossLinePt` and `Get_Dis_Pos`. Distances
use the engine's table-driven `mceUtil3D_sqrt`, reproduced in integer
arithmetic. Python checks that routine's SHA-256 before Rust reads its table,
and `make math-test` compares the copy with the engine on 212,999 inputs
covering every exponent, sign and table row.

| Check | Result |
|---|---|
| Shadow-verified calls, 400 gameplay ticks (plane / inside / sphere / plane point / line point / distance) | 656,685 / 123,872 / 86,879 / 124,281 / 260,637 / 352,786 |
| Mismatches, all nine functions | 0 |
| Gameplay tick work p50, before → after (two clean pairs) | 26.1 → 13.7 ms, 25.8 → 13.6 ms |
| Gameplay tick work p95, before → after | 30.5 → 15.6 ms, 30.0 → 15.4 ms |
| Gameplay CPU, one sampled run per build | ~60–80% → ~35–50% of one core |
| Title to village, longest loading frame | unchanged (~63 s, ~1 s) |

"Before" disables only these changes; the three earlier routines stay native
in both arms. A third pair ran under heavy desktop contention (41.1 → 18.3 ms
p50) and is excluded. Title-to-village time is dominated by paced menu input
waits.

### Next targets

Shares are from the profile above, taken before these changes, so the
remaining work is now a larger share of a smaller tick. Re-profile before
starting each target.

1. **`GM_Util_CollCheck::Hit_Tri_Sph` and `Hit_Tri_SphFall`** (about 1 KB of
   Thumb code each). Ghidra's call graph makes these the hub: reached from
   `Hit_Sph_Tris`, `Check_HitAll`, `Check_AimSph` and `Check_Fall`, they call
   all six new leaves plus `Get_Tri_NearPos`, `Set_MoveVec`,
   `mceVector3D_normalize`, `ERP_CalcVec::Set`/`Sub` and `Mul`. As whole
   functions they would cost one hook per triangle instead of one per leaf
   test, and they cover the remaining instructions in their own bodies
   (3.5% and 3.2%). The fifth argument is a float on the stack, but the
   shadow trampoline pushes two words before calling the original, so shadow
   mode first needs a variant that copies stack arguments.
2. **`ERP_CalcMath::Mul`** (10.9% including its `__aeabi_fmul`). The wrapper
   only stores both arguments, calls through the PLT and returns, so a Rust
   hook would cost more than the work. Better: an in-guest Thumb-2 VFP body
   with the same domain checks as `eabi.py`'s arithmetic helpers, falling back
   to the original routine.
3. **`mceUtil3D_sin`** (5.0%). Table interpolation like `mceUtil3D_sqrt`, plus
   soft-float corrections; `mceUtil3D_sqrt` itself is another 1.1% when called
   outside distances.
4. **Smaller routines** (each under 2%): `_mceTransform_setRotateEulerXYZ`,
   `_mceStructArray_setCopy`, `Check_ReiCrossColumn`,
   `GM_Util_BoundStage::Check_HitAll`/`Check_Fall`, `mceVector3D_normalize`
   and `_mceTransform_copy`.
5. **Loading** (unchanged by all of the above). The longest loading frame is
   about 1 s, involving `CMN_HizArchive::_calcChecksum` and `rcx::font` glyph
   code; it needs its own profile of slow loading frames.

Moving GL submission to another thread was considered and not pursued: CPU
graphics submission is about 1.8 s against about 69 s of native execution in
a loading profile, and under 1% of gameplay tick time.

The profile sampled program counters every 50,000 guest instructions
(`emu_start` count slices) while the benchmark replay drove village
gameplay, charging soft-float helper samples to the link register's
function. It counts instructions, not time, and slows emulation about tenfold.
Static analysis used Ghidra 12.1.4 headless (`analyzeHeadless` with short Java
post-scripts for decompilation and call graphs) on copies of the libraries;
Ghidra rejects project paths containing dot-prefixed directories.

## Camera-turn interpolation — 2026-10-27

Camera turns change which native objects are visible. The earlier renderer
required consecutive snapshots to have the same command count and draw order;
one appearing or disappearing object could stop interpolation for the scene.
The renderer now matches surviving geometry using its array identities, layout,
topology, projection and textures within the same clear pass. New or ambiguous
instances snap individually. Camera cuts, resource invalidation and the existing
motion bounds still discard incompatible history. Compatibility and vertex
checks run once per native tick rather than at every display refresh.

To exercise visibility changes, rapid mouse sweeps and aim transitions against
the supported imported game:

```bash
SDL_VIDEODRIVER=offscreen SDL_AUDIODRIVER=dummy \
  .venv/bin/python tools/verify_camera_turns.py --output /tmp/re4-camera-turns
```

The verifier uses isolated fresh saves, compares every native endpoint pixel,
hashes all guest memory around extra presentations, and checks service/tick
counters. It requires visibility changes with distinct intermediate motion,
then runs the normal 60 FPS worker without readbacks. An optional
`--baseline-library /external/before/libre4fast.so` captures the identical native
submissions through an older compiled renderer for paired comparisons. These
are synthetic village checks and host submission timings, not GPU or physical
display timings; native 20 FPS mode does not interpolate.

See the [REA culling investigation](rea-workflow.md#camera-turn-investigation--2026-10-27).

One 120-tick paired sweep on the reference host preserved distinct intermediate
motion through **56 of 56** draw-count changes; the previous renderer preserved
none of those 56. All 120 endpoint images matched exactly and all guest-memory
and service-counter checks passed. Median replay submission time changed from
**0.218 to 0.186 ms**, with p95 changing from **0.291 to 0.259 ms**. These are
CPU submission timings from alternating renderers receiving identical draws;
they do not measure native tick speedup or GPU execution.

The subsequent paced 120-tick sweep presented at **60.00 FPS** over about six
seconds, with p99 refresh intervals of **17.31 ms** and a maximum of **17.39 ms**
in the worker's last 239 intervals (about four seconds).
This run used the original 800×480 render surface with SDL's offscreen driver
and dummy audio. Evidence is in `/tmp/re4-stutter/camera-final/results.json`.
The source regression tests also fail against the saved older library for
inserted, removed and reordered geometry, and pass with the rebuilt library.

A separate paced sweep using the locally saved **2× rendering, 16:9, no MSAA**
preferences also held **60.00 FPS** over 120 ticks. Its p99 refresh interval was
**16.97 ms**, with a maximum of **17.06 ms** over the same bounded interval window.
These six-second offscreen samples
do not establish campaign-wide or physical-display frame pacing. That report
and screenshot are under `/tmp/re4-stutter/saved-settings`.

## Local measurements — 2026-10-23

Reference host: AMD Ryzen 9 6900HS, Radeon 680M, Mesa 26.2.5, Arch Linux
x86_64, Python 3.14.8 and Unicorn 2.1.4. Gameplay used SDL's offscreen driver;
these are submission/presentation measurements, not physical monitor refresh
or GPU execution timings. Raw evidence, fixtures and captures are external at
`/tmp/re4-fps/verification/results.json` and its neighboring files.

| Check | Recorded result |
|---|---|
| Native versus replayed endpoint pixels | Exact match in all seven cases |
| Distinct intermediate motion | Demonstrated in five cases |
| Guest memory across extra presentations | All 256 MiB unchanged |
| Extra native service calls during replay | None |
| Native stage transition with presentation active | Passed |
| Snapshot array storage at final sample | 1,988,000 bytes |

Three alternating paired blocks in the same scene measured median tick work of
39.707 ms through Python GL imports and 35.556 ms through the native bridge:
about **10.5% less tick work**. Each block measured 30 ticks after five warm-up
ticks, with snapshots enabled and the presentation thread stopped. These figures
describe this scene and host; they do not establish a loading or campaign-wide
speedup. Desktop background activity was uncontrolled.

| Presentation target | Recent measured FPS | Native ticks | Native mission seconds | Wall seconds |
|---|---:|---:|---:|---:|
| 60 | 60.03 | 60 | 3 | 2.996 |
| 120 | 120.00 | 60 | 3 | 2.996 |
| Uncapped | 994.80 | 60 | 3 | 4.567 |

Uncapped presentation saturated the host enough to slow simulation in this
offscreen run. A 60 or 120 FPS target preserved real-time simulation and avoids
that unnecessary work. The engine clock still counted exactly 20 native ticks
per mission second in every mode. Higher numbered targets remain options, with
timing and driver tests covering scheduling; they are not all gameplay-qualified.

An additional X11 startup/CLI check completed 80 native ticks at a 120 FPS target
(120.01 recent presentation FPS), with no GL messages and clean shutdown. Its
scope was menus/loading, separate from the offscreen gameplay fixture.

The previously documented intermittent native difficulty-initialization
exception remains outside this change. Neither these checks nor interpolation
establish full-campaign, physical-controller, Intel or NVIDIA qualification.
