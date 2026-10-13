# Desktop launcher and release builds

Run `./re4pc.sh launcher` to open the Python/Tk desktop launcher. APK import and
Play use child processes; logs are captured with bounded buffers while the GUI
remains responsive. The main window has no console panel. **View logs** opens
optional session output in a separate window; desktop entries use `Terminal=false`.
Progress, completion and failures appear in the main status area. Play, Backups
and Diagnostics are enabled when the selected folder contains the expected game
files; the engine still performs full validation at launch. APK import suggests
an unused destination and selects it only after a successful import.

The launcher uses a parchment case-file layout, a pinned village photograph,
generated distressed numeral, application icon, cogwheel and typewriter artwork.
It opens at 1280 × 720 and scales its composition uniformly when resized, with a
1000 × 600 minimum. Text, navigation, installation fields and actions remain live
native widgets. [Artwork prompts and provenance](launcher-assets.md)
are recorded with the project. Release builds copy these assets from an explicit
allowlist. Source desktop installation can use the generated icon when neither
an APK nor a custom icon is specified; an existing installed icon is preserved.

Settings expose keyboard/controller/mouse bindings, mouse
and controller sensitivity, invert Y, stick dead zone, window mode and the
currently qualified presentation rate. Settings tabs scroll on smaller windows.
Import requires an unused destination.
The user supplies the APK; packages contain no game libraries or assets.

Game rendering uses an 800 × 480 logical framebuffer. Resizable/HiDPI drawable
sizes use an aspect-preserving blit with black letterboxes. SDL mouse coordinates
map through that same transform; presses in bars are ignored and releases during
a drag are clamped to the logical edge. Movies, diagnostics and controller
cursor draw into that logical surface. Screenshots capture its 800 × 480 pixels.
Alt+Enter toggles borderless desktop fullscreen, F3 diagnostics, Tab cursor,
F12 quit. Held input is released on focus loss, device removal and remapping.

Default controllers use left-stick tank movement, right-stick look, triggers
for aim/fire, A action, X reload, Y knife, Start status, and D-pad navigation.
In PC menus the right stick moves the cursor, A clicks the current selection,
and B confirms through a verified native action or a bounded slider gesture.
In touch mode A holds the virtual cursor for dragging. All devices share named
actions, with independent physical sources and press-selected release routes.
Bindings use SDL keycodes, button numbers, and controller names in settings.
Tab, F3 and F12 are reserved. Explicit run options override saved settings.

User locations remain independent of the checkout and package version:

| Content | Default |
|---|---|
| Imported data and saves | XDG_DATA_HOME/re4mepc/game |
| Desktop settings | XDG_CONFIG_HOME/re4mepc/settings.json |
| Backups | XDG_STATE_HOME/re4mepc/backups/installation-path-hash |
| Logs | XDG_STATE_HOME/re4mepc/logs |
| Converted textures | XDG_CACHE_HOME/re4mepc/textures |

Each installation has a process lock covering the entire Game lifecycle.
Save tools use the same lock; export/import/restore require the game stopped.
A full save snapshot precedes native startup (including possible legacy save
migration), and the supported `Bio4_UserData::Save` entry takes another complete
snapshot before its storage file opens. Its sole return follows close/destruction;
a successful native result publishes a coherent checksummed set. Failed or
interrupted calls retain their prewrite snapshot and never publish success.
Latest ten distinct content sets are retained; equal contents update recency.
Caches and imported resources are excluded. No cloud sync is provided.

Stopped-game CLI equivalents to launcher backup controls:

```sh
./re4pc.sh backup
./re4pc.sh backups
./re4pc.sh export-backup SNAPSHOT_ID '/path/with spaces/save-backup.zip'
./re4pc.sh import-backup '/path/with spaces/save-backup.zip'
./re4pc.sh restore-backup SNAPSHOT_ID
```

All accept `--game PATH`. Restoring first checks the manifest, all file sizes
and hashes and path safety, preserves a recovery snapshot, stages and fsyncs the
replacement, then exchanges save directories atomically on Linux. The returned
`recovery_directory` holds the independent original set, in addition to the
retained snapshot. A failed rollback reports that path explicitly. Restore never
merges partial sets. Export refuses an existing destination.

`make package` uses a Docker Ubuntu 22.04 x86_64 builder for the runtime ABI
baseline. It stages Python 3.10/Tk, pinned Python dependencies, SDL2, FFmpeg and
native helpers with relative Unicorn lookup. Host graphics drivers, glibc,
GL loaders, DRM/GBM, libstdc++ and libgcc remain external. The build compiler and checkout are not
needed to run the resulting artifacts. Both outputs come from the same audited
AppDir:

- `dist/re4mepc-linux-x86_64.AppImage`
- `dist/re4mepc-linux-x86_64.tar.gz`
- `dist/SHA256SUMS`

The portable archive's `re4mepc/AppRun` opens the launcher with no arguments;
arguments expose the same CLI. AppImage supports `--appimage-extract-and-run`
where FUSE is unavailable. Build metadata records baseline, dependencies and
verified build-tool/runtime checksums; CONTENTS.json inventories files and
symlinks, and dependency/license notices accompany the runtime. Source/runtime
allowlists and content-hash checks reject proprietary inputs. Build needs
Docker/network initially; artifact launch needs a graphical Linux desktop.
`tools/package.py --repack` publishes both formats from an existing AppDir after
verifying its content manifest and cached build-tool checksums. This offline
operation preserves that stage's code and dependencies; it does not perform a
fresh runtime build or establish new target-OS qualification.

Validate with `tools/validate_package.py` on the target environments. A launcher
`--smoke-test` opens the real GUI briefly and exits for these checks. Package
updates replace application artifacts while preserving external XDG state.
Full campaign and long-session portability remain separate validation work.

The automated validation uses clean Ubuntu 22.04, Ubuntu 24.04 and Arch images
with Mesa and Xvfb installed as display/driver support. It asserts Python and a
compiler are absent before launching the bundled runtime. Both artifact formats
open Tk, execute 160 engine ticks from a separately mounted user fixture, and
exercise XDG settings/backups while switching formats. These checks validate a
software OpenGL compatibility driver; physical displays, hardware controllers
and vendor-specific driver combinations remain additional coverage.

## Immutable candidate qualification — 2026-10-12

The candidate pair includes desktop menu routing, achievement gallery exports
and optional portable save/media bundles. Both formats pass clean Ubuntu 22.04,
Ubuntu 24.04 and Arch containers on these exact bytes:

| Artifact | SHA-256 |
|---|---|
| AppImage | eb2df02f95cad7867e064b005dcf133696a55444c4760637238ddaa10d051bfe |
| Portable tar.gz | f74498acb580e01588e1c7c9188206ab8faf2977984a534d9ba7e37f00bf08ab |

| Target | Validation image ID |
|---|---|
| Ubuntu 22.04 | sha256:705fc84ae7baab3d57accf2c14e45d1dd8a315030205f8392e266fecdae67911 |
| Ubuntu 24.04 | sha256:9699cd9ecace73586e6dd9ceb95b997b20aaac3cf07efa9b556e4618227184d7 |
| Arch | sha256:2a24a58daccac5b7367731701581511825de12140723e6f75fda1957b74e54f4 |

The checks open both Tk launchers and run 160 engine ticks per format with
llvmpipe, Xvfb and dummy audio. They verify shared settings/backups, gallery
selection and media deduplication, PNG/MP4 bundle import followed by explicit
Restore, and legacy save-only roundtrips. Paths contain spaces. Python and a
compiler are absent from the host image. The Arch validator initially lacked
`cmp`; adding the test utility `diffutils` allowed the same artifacts to pass.

Upgrade checks retain the preceding portable build's settings and snapshot
while switching to either candidate format. The preceding AppImage hash is
`fb7200de0f1ab5afd7639f16a082120434949ab1854db4503293b81bcb8fbf43`;
the preceding tar.gz hash is
`a4aa2099d64b8600611078e2a7db17f62d4043e1c478f88a990c83ff1d9dbca2`.
Both old artifacts are frozen inputs, although only the old portable format
creates the upgrade state. Hash checks reject artifact changes during validation.

Evidence and artifacts are external under
`~/.local/state/re4mepc/roadmap-20261012/work/evidence/`, in
`candidate-packages`, `package-validation` and `package-validation-arch`.
Reproduce with:

```bash
.venv/bin/python tools/validate_package.py \
  --dist /external/candidate-packages --previous-dist /external/preceding-packages \
  --output /external/package-validation
```

These are automated smoke-qualified candidates. The full release gate remains
incomplete: natural campaign progression, physical controller hot-plug, audible
speaker output, physical display/HiDPI checks and package execution on hardware
drivers still need evidence. Source desktop checks cover resizing, fullscreen,
focus/cursor capture and SDL virtual-controller disconnect. Available hardware
is AMD RX 6700S/680M; Intel and NVIDIA hardware and a physical controller are
unavailable. Repacking invalidates all qualification attached to these hashes.
