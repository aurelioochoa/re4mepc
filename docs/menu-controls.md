# Desktop menu input

PC mode browses menus the way a console port does: a focus moves between the
game's own buttons and the keyboard or controller presses the focused one.
There is no desktop pointer and no hint bar.

| Keyboard | Controller | Action |
| --- | --- | --- |
| WASD / arrows | D-pad / left stick | Move the focus (hold to repeat) |
| Left / Right on a counter | Left / Right on a counter | Adjust it (difficulty) |
| Enter or Space | B or A | Press the focused control |
| Escape | Start | Cancel / back |

Every frame the host observes which original layout components the engine
draws (`LYT_Cmp_*::doDraw`). Enabled, visible buttons, push buttons, toggles,
switches, list rows, counters and confirmation sliders become focus targets.
A disabled table or layout disables everything inside it, so an open item
submenu takes the focus from the inventory list behind it. Empty list rows
and controls mostly off screen are skipped.

Directions pick the nearest target in that direction, preferring targets in
line with the current one. The initial focus is the screen's main choice (the
largest control; ties go to the top, then the right). Difficulty OK, notice
Next and mission Select are read from their tasks, so Enter still continues on
those screens. Moving past the first or last visible list row scrolls the
original table with `LYT_Cmp_TableView::Select_ViewTopItem`. Arrow buttons
inside a counter are not separate targets; Left/Right press them.

Pressing a button sends an ordinary touch at the centre of its touch area,
exactly like a mouse click, so every result comes from the engine's own
handlers. A confirmation slider receives one bounded eight-tick drag along its
track. Holding Confirm never repeats it. Focus loss, controller disconnect,
window close, rebinding and menu-state changes cancel pending gestures and
release a touch already begun. A title "touch the screen" panel with no
buttons is tapped at its centre.

The focused control has a blood-red outline (round for icon buttons). Mouse
clicks and motion work as before; the mouse hides the focus until the next key
or button press, and that first direction press only shows it again.

Escape/Start clicks the verified Back button in inventory or Cancel button in
its item submenu, once per press, and calls the native No handler on the data
reset prompt. Other screens retain the engine's original cancel path. During
gameplay, including its HUD buttons, keys keep their gameplay meaning.

Run the visible replay on isolated game data:

```bash
.venv/bin/python tools/test_menu_controls.py --device keyboard --output /external/menu-keyboard
.venv/bin/python tools/test_menu_controls.py --device controller --output /external/menu-controller
```

It traverses SDL event polling and original engine actions, reaches gameplay,
checks the default focus and focus movement on each screen, changes/restores
difficulty from the focused counter, scrolls the mission list past its visible
rows and back, cancels partial confirmation on focus loss and actual SDL
virtual-controller detach, tests held confirmation and opens an inventory item
submenu, then returns through inventory to gameplay with the current cancel
binding. It also checks native serialization. Its tutorial-clear
and mission-selection setup is synthetic and does not certify campaign progress
or a physical controller. Game-free tests cover release routing across state
changes, gameplay screens, disabled containers, counters, list scrolling and
focus movement.

A fresh-install, input-only first-mission run exposed that the original native
Back path did not close inventory's item submenu. The bounded cancel clicks
above correct that behavior while preserving the existing gesture-cancellation
rules. The failure is recorded in `natural-pilot`; the
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
