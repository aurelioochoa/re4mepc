# Validation

The host targets Linux x86_64 with SDL2, desktop OpenGL, FFmpeg and Unicorn.
No original game libraries, assets, dumps, save files or screenshots are
part of the repository or required by the component suite.

## Repeatable source-only verification

From a clean Git clone:

```bash
./setup.sh
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
