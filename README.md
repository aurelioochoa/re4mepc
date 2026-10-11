# Resident Evil 4 Mobile — Linux PC host

Runs the original ARM32 Android game engine in a visible Linux desktop window. This is an experimental compatibility port: Unicorn executes the original native libraries, SDL provides the window and audio, and a GLES 1 bridge sends the game's rendering to desktop OpenGL. It does not require an Android emulator or an Android installation.

This repository contains the compatibility host, importer, synthetic tests and documentation. Supply your own APK; the host never downloads the game. Original executable libraries and resources are extracted locally and stay outside the checkout.

## Setup and play

Requires Linux **x86_64**, Python 3.10 or later with `venv`, a C compiler, `pkg-config`, SDL2 development headers, desktop OpenGL with a compatibility profile, and FFmpeg. Run it from your desktop session, with your normal display and audio device available.

On Arch Linux, install `python gcc pkgconf sdl2-compat ffmpeg mesa`. On Debian/Ubuntu, install `python3-venv build-essential pkg-config libsdl2-dev libgl1-mesa-dev ffmpeg`.

```bash
git clone https://github.com/aurelioochoa/re4mepc.git
cd re4mepc
./setup.sh
./re4pc.sh import '/path/to/Resident Evil 4.apk'
./re4pc.sh check
./re4pc.sh run
```

F12 closes the window. PC gameplay controls are enabled by default; the cursor is captured during gameplay and released in menus and story overlays. English is selected at startup; use `--language saved` to retain the game's saved language. Enter, Space, Escape, or a mouse click skips a playing video.

| Desktop input | Game input |
| --- | --- |
| W / S | Forward / backward |
| A / D | Turn left / right (classic tank movement) |
| Arrow keys | Same directions; navigate menus |
| Mouse movement | Look and aim with relative mouse movement |
| Hold right mouse / X | Aim |
| Left mouse / Z | Fire |
| R | Reload |
| Hold F, then left mouse / Z | Ready knife, then slash |
| E / Enter / Space | Context action; Enter / Space advance story text |
| Escape | Status menu |
| Tab | Release / capture cursor; click to recapture |
| F12 | Close the host |

Menus use normal mouse clicks. Mobile confirmation sliders require dragging the arrow across the button. For the original mouse-as-touch controls, launch `./re4pc.sh run --controls touch`.

Mouse look uses 0.15 degrees per pixel, with vertical movement limited to
45 degrees up or down. Holding and releasing aim preserves the vertical look
angle. Losing window focus releases held controls and the cursor; click the
game window to recapture it.

Un-aimed mouse look rotates the third-person camera around its native target.
The engine checks walls against that same camera orbit before rendering.

The importer restores the bundled files' original names and checks both ARM
libraries and every required stage resource. Extraction is temporary until
validation succeeds. Existing destinations, including empty directories and
symlinks, are never overwritten.

## Data locations and supported engine

| Content | Default location |
| --- | --- |
| Imported libraries and resources | `~/.local/share/re4mepc/game` |
| User saves | `~/.local/share/re4mepc/game/saves` |
| Decoded audio cache | `~/.local/share/re4mepc/game/cache/audio` |
| Test game copies, captures and measurements | `~/.local/state/re4mepc/logs` |

Absolute `XDG_DATA_HOME` and `XDG_STATE_HOME` values replace
`~/.local/share` and `~/.local/state`. Empty or relative values use the defaults.
Explicit paths remain available:

```bash
./re4pc.sh import /path/to/game.apk --output /external/re4/game
./re4pc.sh check --game /external/re4/game
./re4pc.sh run --game /external/re4/game
```

Only the following engine libraries are supported. Import, check and run verify
these SHA-256 values. The APK's overall hash can differ, so repackaged APKs with
the same libraries and complete resources are accepted. There is no runtime
option to bypass engine compatibility validation.

| Library | SHA-256 |
| --- | --- |
| `libbio4af.so` | `6f6e52ef26b096cda44fc08c3f541cdc3bf1056a88f13fc1c3e17201589a0423` |
| `libmc_eruption_for_android_jni.so` | `25109c3b799045312073243b644f6053726689d7baf05bcf09b7acd786cff4f6` |

For an older checkout with local `game/` and `logs/`, run
`.venv/bin/python tools/migrate_local.py` once. It checks both destinations
before moving anything and records file inventories and SHA-256 values in
`~/.local/state/re4mepc/migration.json` (respecting `XDG_STATE_HOME`). It refuses
existing destinations and verifies every moved file. Stop running game
processes before migration. `--verify` later checks all original entries;
new test artifacts are allowed.

## Visible testing

`make` lists the standard project commands. `make run` (or `make dev`) starts
the game with live terminal status every five seconds: FPS, frame and draw
counts, input count, cursor state, and whether the engine is still loading.
Startup, cursor changes, errors and final statistics are logged immediately.
Verbose original engine messages are available at the debug level.

```bash
make run ARGS="--log-file ~/.local/state/re4mepc/logs/game.log"
make run ARGS="--log-level debug --log-interval 2"
make verify
```

Use `--log-interval 0` to disable periodic status. The log file appends across
runs. Terminal log levels are colored (debug cyan, info green, warnings yellow,
errors red); redirected output and log files stay plain. Set `NO_COLOR=1` to
disable colors or `FORCE_COLOR=1` to enable them even when redirecting output.
`make check` builds helpers and runs synthetic component tests without a game.
`make verify` also audits the Git index and history. Use `make check-game`
(or `./re4pc.sh check`) to validate your imported game. `make clean` removes compiled helpers and Python
caches, and `make distclean` also removes `.venv`; both preserve imported game
data, saves and logs. Run `make build` after cleaning, or `make setup` after
distclean. No automatic formatter is configured, so `make fmt` explains this.

```bash
make test
make visible-test
make controls-test
```

`make test` checks APK restoration and rejection of unsafe paths, texture palette decoding, ARM/Thumb execution, floating point helpers, JNI argument alignment, save file I/O, and the native memory bridge, including invalid-pointer rejection and quick press/release sampling. These are component tests; they do not launch a hidden game.

`make visible-test` opens a normal SDL window, plays the original intro, displays the title, clicks through to the menu, and plays audio through the desktop audio device. It creates a fresh game copy with separate saves under the external
`logs/visible-test/run-*/game-*` directory and checks the original engine's save/load routines by saving a language change, changing it in memory, loading it back and restoring the original setting. Captures, the input replay, and measured statistics are written to that run directory. The replay accepts F12 and the window's close button; other desktop input is ignored during this timed test so clicks cannot interrupt its sequence. Rendering, video playback, actual mixed audio output, input delivery and nonblank captures are checked automatically; screenshots still need visual inspection for scene correctness.

`make controls-test` opens the real game window, uses an isolated story mission fixture and checks gameplay controls through SDL events one by one. It measures camera direction as well as player rotation, repeated aim transitions, idle drift, focus release and ammunition. Captures and measurements are saved under the external `logs/pc-controls/run-*` directory. F12 or closing the window interrupts the test.

For an interactive visible test with JSON commands on stdin:

```bash
.venv/bin/python -u tools/live_test.py
```

For example, enter `{"action":"screenshot","path":"/tmp/game.png"}` to capture the window, `{"action":"stats"}` for live measurements, or `{"action":"quit"}` to close it. It creates an isolated game copy with fresh saves; normal mouse and keyboard
events also reach this window. Once a mission is running, `{"action":"test_pc"}` runs visible SDL gameplay checks and writes captures and measurements to its external run directory. During this short test only F12 and close-window input are accepted.

## Current scope

Linux x86_64 is the first target. Shared guest memory requires a mapping below 4 GiB, and the renderer requires desktop OpenGL compatibility functions. Windows, macOS, ARM64 Linux, controllers, resizing and fullscreen are not implemented.

The title, English menus, original video and audio, and village gameplay have been exercised in visible desktop tests. ARM translation and Python import calls impose substantial overhead, especially during level loading; this is not yet a performance-equivalent native x86 port. A full campaign playthrough has not been validated. See [VALIDATION.md](VALIDATION.md) for the recorded checks and limitations.

## Implementation

`re4pc/arm.py` loads and relocates both ARM ELF libraries. `jni.py` provides the Android services they request, `bionic.py` handles file and libc imports, and `eabi.py` installs ARM floating point helpers. `graphics.py` bridges fixed-function GLES calls, with OES paletted textures expanded according to the Khronos extension. `media.py` decodes the original audio and movies using FFmpeg. Small C helpers under `native/` accelerate memory imports and mix audio in SDL's callback.

```bash
make build
./re4pc.sh run --frames 600 --screenshot /tmp/frame.png --stats /tmp/stats.json
```

## Source checks and publication

```bash
make check
make audit-source
make verify
make check-game
make visible-test TEST_ARGS="--game /external/re4/game --output /external/re4/smoke"
```

Visible, gameplay, live and input-probe tests accept `--game` and `--output`.
Their defaults use XDG paths and a new run directory every time. They copy only
libraries and resources; user saves and caches are never used as test fixtures.
Copies use separate files rather than writable hard links. Test output must be
outside the source game directory. Captures and copies can be removed after
review to reclaim disk space.

`make audit-source` checks the Git index, every tree in all refs and reflogs,
and every stored blob, including dangling blobs. It rejects paths outside an
explicit source/documentation allowlist, symlinks, submodules, binary contents,
and large encoded payloads or disassembly dumps. It also checks past commits
whose forbidden files have been deleted from the tip. Updating the allowed
source inventory requires editing `tools/audit_source.py` and reviewing the
new source. The audit does not replace reviewing source provenance.

CI installs host dependencies, builds the C helpers, runs synthetic tests and
audits the complete fetched history. It needs no APK, game saves or game
captures. Binary distribution packages containing the game are not produced.

The source written for this host is MIT licensed. The license excludes original
game data, trademarks and third-party dependencies. Interoperability names,
symbols, offsets and hashes identify the supported engine; executable test
snippets are hand-written synthetic fixtures and host ABI trampolines.
