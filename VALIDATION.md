# Validation

The host targets Linux x86_64 with SDL2, desktop OpenGL, FFmpeg and Unicorn.
No original game libraries, extracted assets, dumps or save files are
part of the repository or required by the component suite. The README's reviewed
gameplay mosaic is a documentation image; component tests need no gameplay captures.

## Native engine math verification — 2026-10-27

Bone skinning, vector dot products and transform multiplication now run as
Rust code (`native/math.rs`), with the original ARM routine taking over for any
value outside the verified soft-float domain or any aliasing output. `make
check` builds the crate and runs 14 synthetic Unicorn regressions covering
replacement, fallback, aliasing, identity caches, skinning duplicates and
shadow mismatch reporting.

`make math-test` ran the title-to-village fixture and 200 gameplay ticks in
shadow mode: 2,345,740 calls matched the original routines with zero
mismatches, and 7 multiply2 calls during loading used the original routine.
Two alternating timing pairs measured median gameplay tick work of
43.6 → 27.3 ms and 41.5 → 26.6 ms. Details are in the
[FPS/performance guide](docs/fps-performance.md#native-engine-math--2026-10-27).
This does not qualify a full campaign.

## FPS and graphics verification — 2026-10-23

Current source adds independent geometry presentation at 30/60/90/120/144/165/240
FPS or uncapped, while native simulation remains 20 Hz. The existing 20 FPS
preference remains the default. This supersedes the older source-only
presentation restrictions below; the dated package qualifications still apply
only to their frozen artifact bytes. No portable release was rebuilt for this
change.

`make check` passed **408 component tests**, including real offscreen GL
interpolation, copied array ownership, state restoration, shared-context
presentation, menu/movie transfer, all 40 accelerated GL imports, CLI/settings
and staged renderer imports. `make audit-source` passed the complete source and
history audit. All six implementation acceptance gates passed.

REA 6.4.0/Ghidra 12.1.4/JDK 21 verified the native timing and exec/draw boundaries
against the supported engine hash and ELF/Capstone mappings. The isolated
mission fixture produced exact native/replayed endpoint pixels in seven cases,
distinct intermediate images in five, unchanged hashes of all 256 MiB of guest
memory across extra presentations, and no extra native service calls. A native
stage transition passed with presentation active.

On Ryzen 9 6900HS/Radeon 680M with Mesa 26.2.5, the gameplay test measured
60.03/120.00 presentation FPS at the corresponding targets. An explicitly
enabled native countdown and elapsed timer each advanced three seconds over
60 native ticks. Three paired blocks measured median tick work of
39.707 → 35.556 ms, about 10.5% less work with native GL state imports.
Uncapped rendering caused contention and slower wall-clock simulation in that
offscreen run. A separate X11 startup check completed at 120.01 recent FPS,
without GL messages, and shut down cleanly.

Reproduction commands, hardware scope, visual latency, measured tables and
external evidence locations are in the [FPS/performance guide](docs/fps-performance.md).
The fixture does not qualify a full campaign, physical controllers or other
GPU vendors. The existing intermittent native difficulty-initialization
exception remains unresolved.

## Repeatable source-only verification

The aiming/shooting investigation on 2026-10-14 adds nine combat component
regressions (322 component tests total). REA 6.4.0/Ghidra 12.1.4 identifies
Extreme's deliberate laser suppression and the native fire scan/cooldown
checks. A private copy of the reported save selects Extreme. PC mode now
shows the laser at that difficulty and buffers quick fire taps through startup
and recoil. See [the investigation and isolated engine command](docs/rea-workflow.md#aiming-and-firing-investigation).

The isolated Extreme replay renders 262 changed pixels in the native laser
draw versus zero with the original suppression; six aim-angle checks render
142–328 pixels. The startup tap consumes one round (10 → 9), two clicks
separated by recoil consume two (9 → 7), and keyboard fire/reload returns the
magazine to 10. Aim release and focus loss cancel a buffered shot without
consuming ammunition. These are synthetic mission-2 regression results, not
full campaign or physical-controller qualification. Raw captures and results
remain external at `/tmp/re4-combat/verified/`.

From a clean Git clone:

```bash
make setup
make check
make audit-source
make verify
```

On 2026-10-11 the original baseline passed 49 component tests and the expanded
suite passed 80 tests. The expanded suite
also exercises supported/incompatible engine hashes, repackaged APKs, missing
libraries/assets, malformed archives, unsafe manifest paths, duplicate assets,
existing and concurrently created destinations, XDG defaults/overrides,
independent test copies and migration preservation.

The auditor's negative controls create temporary repositories with forced
ignored packages, extracted assets, saves, captures, binary data disguised as
source, symlinks, encoded dumps and forbidden contents present only in earlier
commits. It also detects dangling binary blobs. All fixtures are synthetic.

The original component coverage remains: ARM/Thumb interworking, EABI math,
NaN comparisons, JNI argument alignment, save I/O confinement, memory bridge
pointer validation, palette textures, SDL input sampling, key aliases,
movie queue timing/cancellation, OpenGL overlay state and runtime logging.
The synthetic OpenGL test uses an offscreen SDL context with generated color
rows. It does not load the game.

## Local real-engine verification

Supply and import a compatible APK before these checks:

```bash
make check-game
make visible-test
make controls-test
```

Each run creates an external game copy containing only libraries and resources,
with fresh saves and caches. Normal user saves are never copied or modified.
The runners print the artifact location. These files are local evidence and
are excluded from publication.

The visible smoke replay checks intro/title/menu rendering, nonblank captures,
nonzero samples from the SDL audio callback, mouse delivery, absence of OpenGL
messages and the engine's own save/load roundtrip. Nonzero audio samples verify
delivery to the audio callback, not speaker loudness.

The gameplay replay checks full camera turns and vertical sweeps, translation
preservation, native collision vectors, repeated aim transitions, idle drift,
movement, fire/reload, knife controls, focus release and cursor recapture.
Screenshots require visual review to confirm scene correctness.

## Compatibility implementation

Both engine SHA-256 values are checked before runtime allocation and engine
initialization. Hook positions derive from symbols and offsets in that
supported layout; no copied engine instruction signature is embedded in the
host. Generic ABI trampolines and arithmetic helpers are authored host code.

The mouse bridge converts degrees to the engine's binary angle units and
weapon pitch blend. It preserves translation across model rotation and applies
free-look pitch before the engine constructs its orbit and collision ray.
The movie overlay preserves OpenGL state while enabling color writes and
setting packed pixel-store state. Movie decoding uses a bounded worker queue
and presentation clock, including buffered frames after decoder exit.

This is an experimental compatibility host. A complete campaign, all menus,
long-session behavior and platforms beyond Linux x86_64 remain unverified.

## Frame timing and media performance — 2026-10-11

The expanded component suite passes 122 tests, including deadline pacing,
sleep overshoot, long-stall recovery, batched ARM arguments, pending audio
cancellation/pause/volume/reload, asynchronous movie startup and decoder cleanup.
The publication allowlist includes the new timing module and its tests.

The supported engine updates its mission seconds every 20 frames, and its
application FPS check always permits an update. The host now caps this combined
update/draw callback at 20 Hz; raising its FPS also raises gameplay speed.
The gameplay replay directly checked the original mission countdown and elapsed
time counters: 20 updates advanced both by one second in 0.999 seconds of wall
time, paced with the same clock as interactive play. Movement, camera sweeps,
aim transitions, fire/reload, knife, focus and menu checks also passed.

A cold-cache visible replay exercised 560 frames, the intro, title/menu clicks,
audio output and native save/load with no OpenGL messages. Maximum measured
main-thread video service time was 0.766 ms and video cleanup time was 1.584 ms;
the maximum audio service call was 26.433 ms. Measurements are local to this
machine and are not portable performance guarantees. Video cleanup returns
before its worker finishes reaping FFmpeg. The replay asserts that media calls
stay under 100 ms and total run time cannot imply accelerated game updates.
Menu occupancy checks reject a black screen with only the corner logo; positive
and synthetic negative controls were exercised before reviewing the captures.

Register reads reuse one batch buffer per runtime and graphics forwarding reuses
the import argument snapshot. OES palette expansion uses Pillow's native path,
with nibble order, alpha and mip levels covered by regression tests. A synthetic
1024 × 1024 RGBA palette comparison produced identical pixels and measured
237.24 ms for the Python reference versus 9.74 ms for the new conversion in one
run; this measures texture conversion, not overall game FPS.

The visible replay still recorded a maximum engine frame of 4.57 seconds during
resource loading. These ARM engine stalls remain distinct from media bridge
latency. A cap prevents accelerated gameplay and post-load catch-up bursts; it
cannot preserve real-time simulation on hardware that consistently takes more
than 50 ms to execute an engine frame. Uncapped rendering requires an audited
separation of native logic and drawing. Frame-time history is bounded to the
latest 200 samples while mean/maximum measurements cover the entire run.

## Source separation verification — 2026-10-11

The existing installation and test artifacts were moved outside the checkout.
Pre/post inventories matched for 71 game files and 280 historical log/artifact
files, including normal saves and audio caches. Migration evidence remains in
the local state directory.

After migration the normal desktop smoke replay passed 710 frames with 4,741
draw calls, 55 texture uploads, one video, 1,352,354 nonzero mixed samples,
no OpenGL messages and a successful engine save/load roundtrip. The title
capture was visually inspected. These measurements came from a fresh external
test game with independent saves, on the supported Linux x86_64 desktop.

## Desktop release integration — 2026-10-11

The expanded component suite passes 210 checks. Coverage includes exclusive
timing and active operations, native-hook returns, corrupt/concurrent caches,
allocator accounting, logical/drawable coordinate mapping, release routing,
controller disconnect/remapping, settings precedence, interrupted snapshots,
restore rollback/recovery, launcher children and package-content negative
controls. The diagnostics/cache, desktop/input and save/media/launcher leaves
also passed separately (39, 60 and 53 tests). Direct commands were used when the
skill's Node subprocess supervisor could not capture output in the restricted
execution environment; empty supervisor output was recorded as failed evidence.

The current SDL-injected gameplay replay passed camera sweeps, movement, repeated
aim, fire/reload, knife, keyboard aliases, focus release, cursor recapture and
status-menu entry. Twenty updates advanced the original mission countdown and
elapsed-time counters by one second in 0.999 seconds. This run used a hidden
window on software OpenGL. An earlier visible-window run failed its keyboard-aim
assertion; the hidden replay did not reproduce that failure. Physical cursor
capture and that intermittent visible failure still need a desktop retry.

The separate virtual-controller replay used SDL_JoystickAttachVirtual and SDL's
axis/button APIs, reached gameplay and completed look checks in 1,529 ticks and dragged the native
confirmation slider. It visited title, difficulty, confirmation, notice,
mission-selection and gameplay tasks. These checks exercise real SDL event
translation, not a physical controller's hardware or platform mapping database.
Three right-stick ticks turned native yaw by −26.999998° with controller
sensitivity 2 and mouse sensitivity 4. The camera bridge now applies controller
scaling independently of mouse scaling, while retaining shared inversion.

A 560-tick visible replay exercised the intro, title/menu, resize to 1000×700,
fullscreen during the movie, F3, audio and native save/load. It recorded 2,589
native draws, 55 uploads, 2,093,730 nonzero mixed samples, five successful save
transactions, zero failed saves and no OpenGL messages. Captures and versioned
reports are preserved locally under build/release-validation; imported engine
fixtures, captures and logs are excluded from publication.

At this 2026-10-11 checkpoint, the supported-hash rendering audit left the
independent-presentation gate closed. Native drawing changes event-button and
interaction-message state;
virtual task/camera/animation dispatch has no proven interpolation contract.
Only 20 Hz was selectable at that checkpoint. No 30/60 FPS equivalence or
interpolated motion was claimed then. The 2026-10-23 host-snapshot implementation
above does not repeat those coupled native draw routines. See
[the rendering audit](docs/render-audit.md) for both investigations.

## Benchmark qualification and limitations

The reference CPU is an AMD Ryzen 9 6900HS with 15,943,704,576 bytes of RAM,
Linux 7.1.4 and Mesa 26.1.5. Engine hashes are those listed in the render audit;
settings are default 800×480, 20 Hz, mouse sensitivity 1, dead zone 0.18 and
invert Y disabled. Every scenario uses isolated inputs and fresh saves. Cold
means application caches; OS page cache is uncontrolled. Title-to-village time
includes reproducible menu-input waits. Sustained gameplay runs 200 ticks, then
the audited native lifecycle requests stage 2→3 and runs 40 further ticks.
This verifies stage loading/object lifecycle, not a natural door route.
Constructor/linking readiness defines startup; initial engine loading in the
first 200 replay ticks remains in accumulated phases and maximum loading work.

GPU reference measurements on the Radeon 680M include two complete repetitions
per cache mode. Five interleaved stationary windows per diagnostics mode measured
52.915 ms baseline versus 53.743 ms instrumented median work: 1.56% overhead.
The restricted environment subsequently lacked GPU/display access. A resumed
software-renderer case was identified and excluded from the GPU reference.
Benchmark resume now rejects mixed renderer/version, engine, hardware, settings,
configuration and duplicate-case evidence. A separate llvmpipe series uses the
software renderer consistently. Its five paired instrumentation windows measured
51.933 ms baseline versus 53.006 ms instrumented: 2.07% overhead. Both observed
overhead gates pass; detailed profiles and F3 drawing are separate opt-in work.

All fifteen unprofiled software-renderer cases completed: five cold, five warm
and five cache-disabled runs. Each native stage 2→3 transition passed. Medians
are across the five runs; gameplay p95 is the median of per-run p95 values.

| Cache mode | Startup/linking (s) | Title→village (s) | Loading range (s) | Largest loading frame (ms) | Gameplay p50 / p95 (ms) | Native transition block (s) |
|---|---:|---:|---:|---:|---:|---:|
| Disabled | 0.718 | 78.341 | 77.076–80.245 | 5411.5 | 53.50 / 60.38 | 3.567 |
| Cold | 0.726 | 78.083 | 77.438–78.976 | 5160.2 | 53.72 / 57.87 | 3.637 |
| Warm | 0.698 | 78.552 | 77.730–79.019 | 5695.5 | 54.23 / 58.42 | 3.625 |

Median guest reservation peaks were approximately 28,733,376 bytes in every
mode. Enabled texture caching added 27,343,872 bytes of host cache accounting;
disabled added zero. Process RSS reports are high-water marks since the shared
benchmark process started, not independent per-case memory peaks. The overhead
probe's first case has partial diagnostic counters while disabled windows run;
it is excluded from phase/memory comparisons. CPU frequency, scheduling and OS
page cache were not controlled; workload drift is visible in the results.
The software series exercised default keyboard controls before the subsequent
independent controller-sensitivity routing fix; that unused controller path
does not supply these loading measurements. Raw reports retain settings and
engine hashes. No cache gain exceeds this baseline variability.

Loading stalls remain in native execution. For one unprofiled GPU warm case,
exclusive native_unknown time was 68.840 s, CPU graphics submission 1.823 s,
texture conversion/cache access 0.038 s, graphics upload 0.018 s and allocator
search 0.066 s. Allocator search is nested and is not added to phase totals.
GPU execution is unmeasured. These figures do not justify a new allocator or an
unverified parser replacement. The converted-pixel cache remains experimental
and disabled by default; no loading improvement beyond variability is claimed.

A separate cProfile plus selective-native-hook run completed the loading,
gameplay and transition fixture, explicitly marked profiled and excluded from
qualification. Of 122.892 s recorded, emulator self time was 61.700 s and pacing
sleep 34.131 s. Import dispatch had 820,653 calls and 18.965 s cumulative time,
including service bodies; those overlapping totals must not be added. Native
ReadData timing recorded 20 calls / 0.012 s exclusive, CSV ReadLine 390 calls /
0.207 s, and the alternate ReadData entry had no hits. Native_unknown remained
75.239 s, including unclassified host dispatch/helper/emulator work. These hooks
do not resolve the large remaining bottleneck or justify parser acceleration.

## Package evidence and remaining release gate

Both artifacts are produced from the same audited 2,293-member Ubuntu 22.04
runtime stage, including Python/Tk, dependencies, SDL2, FFmpeg, native helpers,
fonts and notices. The stage matches current application modules; its manifest,
build-tool pins and artifact SHA256SUMS pass verification. Offline repacking
refreshed presentation-count metadata and independent controller look routing,
and removed bundled DRM/GBM support libraries in favor of the host graphics
stack. It did not rebuild the Ubuntu runtime. Both refreshed formats pass CLI, engine-input hash
validation, XDG settings and backup operations from paths containing spaces.
Settings from the preceding package remain available in both final formats.
The staged Python imports Tk/Pillow/Unicorn/Capstone/ELF tooling and loads SDL
with host DRM/GBM; this check initializes Tcl, not a graphical Tk window.

The preceding artifact pair passed clean Ubuntu 22.04, Ubuntu 24.04 and Arch
containers with Mesa/Xvfb, no Python/compiler, both Tk launchers, 160 engine
ticks per format and settings/backups retained while switching formats. Those
reports identify immutable artifact hashes and apply to that preceding pair,
not the refreshed bytes. Docker access is denied in the current environment,
and the bundled SDL's graphical backend cannot open a display here. Fresh
clean-OS GUI/engine qualification of the refreshed artifacts remains required;
run tools/validate_package.py in a Docker-enabled environment. Physical displays,
vendor graphics drivers, physical controllers and a complete campaign remain
outside the automated smoke coverage. Existing user imports/saves were preserved.

## Roadmap implementation and qualification — 2026-10-12

The current work supersedes the earlier environment limitations above: Docker,
the AMD desktop and REA/Ghidra are available for the dated checks. Exact source,
toolchain and measurement identities are in [roadmap results](docs/roadmap-results.md).
The five-repetition AMD baseline remains separate from the earlier software
renderer series. No measured loading optimization qualified for shipment.

Keyboard and SDL virtual-controller menu replays reach gameplay and inventory,
exercise a held confirm, and cancel gestures on focus loss/disconnect and native
task/phase changes. Visible gameplay retries do not reproduce the intermittent
keyboard-aim failure; no fix for that failure is claimed. The component suite
adds archive corruption, limits, missing/conflicting media, stopped-installation
locking, interrupted publication and gallery/bundle UI checks.

Both frozen candidate package formats pass clean Ubuntu 22.04, Ubuntu 24.04 and
Arch software-renderer smoke runs. Their [immutable package report](docs/desktop-release.md)
identifies hashes, image IDs, gallery/bundle/legacy roundtrips and preceding-build
settings/backup persistence. Every repack requires new qualification.

[Campaign coverage](docs/campaign-coverage.md) distinguishes input-only first-mission
entry, synthetic stage stress and the isolated session from natural mission
completion. All 22 story completions, additional difficulty/mode gameplay and
natural restart coverage remain unverified. Physical display/HiDPI, controllers,
audible output and extended package hardware-driver checks remain incomplete. The
[rendering research](docs/render-audit.md) records extra-draw memory/host effects
and leaves the presentation gate closed at 20 Hz.

## Experimental publication — 2026-10-13

The [authored qualification summary](docs/qualification-summary.md) identifies
final package hashes and their matching clean-OS/AMD reports. All packaged
application modules and artwork match the source, and the staged content
manifest passes its proprietary-content audit. Final source verification covers
294 component tests, native builds and the source/history audit.

Natural mission completion is deferred to the user's later playtest. The final
two-hour soak was stopped at the user's request; its preserved checkpoint is
2,880.043 seconds, with `completed: false`. The two-hour gate remains incomplete.
The unresolved intermittent difficulty-initialization exception and remaining
physical-device checks are recorded in the summary. No campaign-qualified or
30/60 FPS release claim is made.


## Refreshed public-test packages — 2026-10-14

The [current qualification summary](docs/qualification-summary.md) identifies
`v0.1.0-experimental.20261014` and its new immutable artifact hashes. Both formats were freshly built
with six-language selectors, Japanese fonts/licenses and merged dependency notices.
A regression covers the font-license/dependency-notice directory conflict exposed
by this fresh build. Final source checks cover 313 component tests, native helper
builds and the complete source/history publication audit.

Both formats pass clean Ubuntu 22.04, Ubuntu 24.04 and Arch smoke/upgrade checks,
including six-language Tk launchers, restored preferences and bundled Japanese
glyph coverage. On Ubuntu 22.04 both bundled runtimes additionally check all six
native language IDs and execute 160 ticks per language. Input-only first-mission
replays on AMD RX 6700S observe inventory, its handgun submenu, cancellation and
return to active gameplay, with native save/load and reviewed captures. The first
fixed-timestamp replay's transition/incomplete-roundtrip captures were rejected;
the qualifying retry waits for observed states without changing application code.

Earlier GPU/session/performance evidence remains tied to its historical hashes.
Campaign completion, two-hour endurance, physical-device coverage and the known
intermittent initialization exception remain deferred. User imports and saves,
the preceding release artifacts and raw private evidence remain external/preserved.

## Laser sight customization — 2026-10-14

The source launcher adds color, Original/Circle/Predator/Black Matter shapes,
size, live preview and reset under Settings & controls → Laser sight. Existing
preferences retain the native red sight. Ten synthetic tests cover preference
validation/roundtrips, the real Tk picker and save/reset lifecycle, minimum-size
layout, procedural shapes/animation, projection, and offscreen GL state/depth.

`tools/test_laser.py` exercises an isolated mission-2 fixture: native red and
selected green beam pixels, all custom markers, each Predator dot's selected
color, size changes, native aim tracking, and explicit visibility-off/on controls.
It also exercises the native endpoint-model branch with a fixture-only endpoint
injection; this does not qualify enemy-hit detection or a full campaign. Host
textures follow the native 16.16 beam endpoint and restore graphics state. Raw
captures/results remain external under `/tmp/re4-laser/`. Existing published
AppImage/archive artifacts have not been rebuilt for this source feature.

### Native sight behavior — 2026-10-15

Custom artwork now reskins the actual native endpoint submission. Its vertices,
indices, positioning, projection, visibility checks, depth/blend state and
current intensity/alpha remain native. The previous host overlay and its
constant pixel size have been removed. The optional user size multiplier scales
the original endpoint model, and custom colors preserve its native fade.

Offscreen GL checks compare custom artwork with the native quad at three camera
depths, verify the size multiplier, inherited depth/fading/alpha, animation and
OpenGL state restoration, and check that scope exit never adds an extra draw.
The isolated native regression compares submitted geometry and render state
before/during/after customization, native visibility-off cases, alpha-zero
controls and native marker sizes at different aim distances. Endpoint visibility
is injected only as a positive fixture control, without modifying game files or
user saves. Current display restrictions may skip native Tk widget tests.

### Gameplay mouse capture — 2026-10-17

PC gameplay now routes captured SDL buttons directly to desktop actions and
blocks native touchscreen presses and dragging. Capture centers the pointer in
window coordinates, enables relative movement and the window grab, and hides
the cursor. Tab and focus loss update capture immediately. A recapture click
is consumed through release, including a menu transition during that click;
controller activity no longer overrides a deliberate cursor release.

The 19 mouse-capture and graphics tests passed, including a real offscreen SDL
check of relative mode, cursor visibility, centering and injected button/motion
events outside the viewport. Additional input, key, controller and menu tests
passed. `make check` ran 349 tests with one failure in the existing launcher
achievement wheel timing test; that test passed when rerun alone. The isolated
native combat replay passed all seven cases, including buffered clicks, aim
angles, keyboard/reload, aim release and focus loss. Its report is external at
`/tmp/re4-mouse-capture/combat/results.json`. Offscreen SDL does not verify a
physical desktop pointer grab. Existing distribution packages were not rebuilt.
