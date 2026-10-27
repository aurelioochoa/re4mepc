# Supported-engine rendering audit

## Current host presentation — 2026-10-23

Independent host geometry interpolation is now available at 30, 60, 90, 120,
144, 165 and 240 FPS, or uncapped (`--fps 0`). Native simulation still runs at
20 Hz. The default and existing saved 20 FPS preferences retain native
presentation. Select a higher rate in Settings or run `make run ARGS="--fps 60"`.

This implementation does not call extra native Draw/Render functions. A native
C renderer copies the fixed-function state, matrices, indices and enabled client
arrays at actual native submissions. A separate shared OpenGL context presents
those snapshots while ARM execution continues. Matching draw identities blend
model/view matrices and floating-point vertex/normal data. Texture identity,
indices, projection, array layouts and UVs must agree; incompatible draws snap
to current geometry. Large transform steps, player lifecycle changes, resource
updates, loading, story overlays and menu transitions invalidate history.

The two contexts own separate framebuffers and client state. A hidden SDL
surface hosts native rendering; the visible surface belongs to presentation.
GPU fences publish textures and protect reuse. Menu and authored movie frames
use a bounded three-texture handoff; a higher display rate does not invent
additional movie frames. Host snapshot arrays are bounded to 32 MiB per frame
and never retain guest pointers as replayable data.

Interpolation has up to one native tick (50 ms) of visual latency. Simulation,
input sampling, movement, collision, combat, audio requests, mission seconds,
saves and replay frame numbers retain native tick semantics. Requested FPS is
a target; actual throughput depends on the host and driver. Detailed import or
JSONL tracing uses the Python GL path so per-import attribution stays complete.

Reproduce the game-free driver checks with `make check`, and the isolated
supported-engine checks with:

```bash
.venv/bin/python tools/test_presentation.py --output /tmp/re4-presentation
```

The engine check compares native/replayed endpoint pixels, demonstrates distinct
intermediate images, hashes all 256 MiB of guest memory before/after extra
presentations, checks native service counts, runs paired GL-bridge measurements,
measures independent display FPS and mission time, and exercises a native stage
transition. Its mission setup is synthetic; it does not establish campaign or
physical-controller coverage. See [FPS implementation and measurements](fps-performance.md).

## Earlier native-render feasibility audit — 2026-10-12

The extra-native-draw gate was **closed**. Simulation and presentation remained 20 Hz.
30 and 60 are rejected by settings and CLI validation. Re-presenting the same
frame is not offered as smoother motion. Frame limits and replay frame numbers
continue to count authoritative simulation ticks.

This finding applies only to the two SHA-256 layouts in
`re4pc.assets.COMPATIBLE_LIBRARIES`:

| Library | SHA-256 |
|---|---|
| libbio4af.so | 6f6e52ef26b096cda44fc08c3f541cdc3bf1056a88f13fc1c3e17201589a0423 |
| libmc_eruption_for_android_jni.so | 25109c3b799045312073243b644f6053726689d7baf05bcf09b7acd786cff4f6 |

The local audit tool validates both hashes before inspecting symbols. Run
`.venv/bin/python tools/audit_render.py --output /tmp/render-audit.json` to
reproduce the symbol-level evidence. It publishes names and call relationships,
not engine bytes or instruction dumps. Counts are conservative static lower
bounds because jump tables, literal pools and virtual calls require additional
control-flow recovery.

`Bio4_Main::onDrawFrame` sets up Java state, initializes/resumes the application,
and calls `PLT_Application::Main`. `Bio4_FrameWork::doMain` synchronizes the
message queue and input, handles framework state changes, then calls
`_execState` and `_drawState` consecutively. Exec dispatch includes resource
loading, game tasks, sound resume and resume-state transitions. Draw dispatch
includes task rendering, resource/loading screens and renderer swap.

Both `CMN_GameTaskManager` and `GM_TaskManager` dispatch Frame/Render through
virtual calls. `GM_CtrlMain::Main` calls the gameplay task manager's Frame;
`GM_CtrlMain::Draw` calls Render. A Draw symbol name does not prove purity:
`GM_MisConduct::Draw` calls `GM_CtrlLayout::Set_WinActMess` and
`GM_CtrlLyt_Input::Set_EveBtn`. Those mutate interaction state used by input.
The PC HUD drawing hook also temporarily changes visibility flags and restores
them after the native draw pass.

| Concern | Observed entry points and coupling | Safe independently? |
|---|---|---|
| Timers | GM_MisConduct::Frame updates mission countdown and elapsed seconds every 20 ticks | Keep authoritative at 20 Hz |
| Input | Bio4_Input::Sync, GM_CtrlLyt_Input::Frame; event buttons also changed in Draw | No independent render contract |
| Gameplay/combat | GM_CtrlMain::Main and virtual GM_TaskManager::Frame | No update-only exported lifecycle proven |
| Camera/collision | GM_CtrlMain_Camera::Main invokes behind/scope handlers; ERP_Camera::Set_LookAt_Bind builds view transforms | Snapshot/restore purity unproven |
| Animation/objects | Virtual task and model dispatch; lifecycle-sensitive native pointers | Not exhaustively audited |
| Media | Java services are called inside native execution; host workers decode independently | Native request timing remains coupled |
| Rendering | _drawState, task Render, GM_MisConduct::Draw mutate state | Unsafe for extra unqualified calls |
| Saves | Bio4_UserData::Save owns open, all serialization sections, close and destructor | Audited transaction boundary, independent of rendering experiment |

Candidate framework/task Draw entry points are useful for further research,
but none is approved for extra presentations. No interpolation is implemented
or claimed: there are no proven snapshots that preserve collision/combat/input,
no lifecycle/teleport reset contract, and no replay-equivalence evidence for
camera/animation/object transforms at equal simulation ticks. These unresolved
requirements prevent qualifying 30 FPS or experimental 60 FPS. The other
milestones continue under the original cadence.

## REA and isolated draw observation — 2026-10-12

REA 6.4.0 with Ghidra 12.1.4/JDK 21 produced dossiers for
`GM_MisConduct::Draw`, `GM_CtrlMain::Draw`, `GM_TaskManager::Render` and
`ERP_Camera::Set_LookAt_Bind`. The verified mapping translates ELF addresses
through the measured Ghidra image base; see [REA workflow](rea-workflow.md).
The task manager's Render traverses tasks through their virtual render slot.
The mission draw's interaction-message and event-button writes are retained
as coupling evidence. The camera routine constructs its bound look-at view;
that static relationship alone proves no animation or collision snapshot contract.

`tools/probe_render.py` observes real entry arguments through Unicorn hooks,
then invokes one extra draw in a discarded fixture after settling gameplay.
It never guesses task pointers. Each candidate gets a fresh installation.
Before/after full guest-memory comparisons cover writes by native helpers as
well as Unicorn instructions; instruction write events are capped at 4,096.
Host import counts and graphics submission effects are recorded separately.

| Extra native call | Changed guest pages (4 KiB) | Additional host draw calls | Changes in selected gameplay fields |
|---|---:|---:|---|
| GM_MisConduct::Draw | 4–5 | 7 | None observed |
| GM_CtrlMain::Draw | 38–40 | 19 | None observed |
| GM_TaskManager::Render | 40 | 19 | None observed |

At equal simulation ticks, the selected fields are stage, position, player state,
mission ticks/seconds, ammunition, input-controller bytes and save/achievement
file hashes. No candidate changes those fields in this stationary scenario.
Changed memory pages include stack/scratch data and do not by themselves prove
simulation corruption. Conversely, equality of selected fields does not prove
collision, damage, interaction, object lifecycle or host-resource equivalence.
The fixture unlocks/selects missions synthetically and is not campaign evidence.

```bash
.venv/bin/python tools/probe_render.py --output /external/render-probe
```

Raw dossiers, memory-effect addresses and captures stay outside the checkout,
under the roadmap evidence directory in `dossiers`, `render-probe` and the
independent `render-probe-final` repeat. The table reports ranges across those
two runs; addresses/stack layout affect the changed-page count.
The feasibility result is **blocked by demonstrated draw-side interaction
coupling and an unproven state boundary**. A development rendering prototype
was not built because its prerequisite boundary has not been established.
Interpolation requires separate camera/animation snapshots and reset behavior
for stage changes, destroyed objects and teleports; those remain unresolved.
This audit closes the research milestone with limitations and leaves the
shipping presentation rate at 20 Hz.
