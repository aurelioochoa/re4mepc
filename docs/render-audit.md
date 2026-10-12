# Supported-engine rendering audit

The presentation gate is **closed**. Simulation and presentation remain 20 Hz.
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
