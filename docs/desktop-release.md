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
In menus A holds the virtual touch cursor and the right stick moves it, including
confirmation sliders; B delivers native confirm. All devices share named
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
