# Desktop menu input

PC mode observes recognized native task states for the title, difficulty,
confirmation slider, notices, mission list/description/preparation, inventory
and its item submenu. Unknown states keep the original input path and receive
no synthesized click or drag. Touch mode retains its original controls.

The current **Confirm** binding continues through verified native actions on the
title Start menu, difficulty, notices and mission description. On the recognized
difficulty-confirmation slider it produces one bounded eight-tick touch gesture.
Holding Confirm never repeats the gesture. Focus loss, controller disconnect,
window close, rebinding and menu-state changes cancel pending gestures and
release a touch already begun.

Direction bindings move a visible desktop cursor. **Action** clicks it; **Confirm**
also clicks it in inventory and list states. This permits ordinary item selection
and context menus using keyboard/controller input. Left/Right changes the native
difficulty counter on the difficulty screen. The right controller stick moves
the same cursor. Hints show current remapped keyboard/controller bindings.
The default Enter/B continue, Space/A click, WASD/D-pad move the cursor, and
Escape/Start clicks the verified Back button in inventory or Cancel button in
its item submenu, once per press. Other states retain the engine's original
cancel path; the Back hint appears only where the adapter verifies it.
Mouse clicks/motion continue to work
and cancel an in-progress synthetic gesture before taking control.

Run the visible replay on isolated game data:

```bash
.venv/bin/python tools/test_menu_controls.py --device keyboard --output /external/menu-keyboard
.venv/bin/python tools/test_menu_controls.py --device controller --output /external/menu-controller
```

It traverses SDL event polling and original engine actions, reaches gameplay,
changes/restores difficulty, cancels partial confirmation on focus loss and
actual SDL virtual-controller detach, tests held confirmation and opens an
inventory item submenu, then returns through inventory to gameplay with the
current cancel binding. It also checks native serialization. Its tutorial-clear
and mission-selection setup is synthetic and does not certify campaign progress
or a physical controller. Game-free tests cover release routing across state
changes, unknown states, disabled components and remapped hints.

A fresh-install, input-only first-mission run exposed that the original native
Back path did not close inventory's item submenu. The bounded cancel clicks
above correct that behavior while preserving cursor position and the existing
gesture-cancellation rules. The failure is recorded in `natural-pilot`; the
regression replays are `menu-back-keyboard` and `menu-back-controller`.

One intermittent title-to-difficulty initialization exception occurs both before
and after the JNI class-reference fix. Successful keyboard/controller retries
and ten additional fast PC plus ten touch-only entry trials pass; those trials
do not prove the exception is fixed. REA's difficulty initialization dossier
identifies a virtual Unicode text-setting call after component lookup. The
failure's return address maps to that call site, while its target maps into ELF
data rather than the successful text setter. The cause remains unresolved.
Failure captures, provider output and addresses stay external. The replay now
records guest base, tick, source identity and relevant registers on failure.
