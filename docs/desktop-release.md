# Desktop launcher and release builds

Run `make install` from the checkout to prepare the app and install the per-user
`re4mepc` CLI and applications-menu entry. Use `make play` from the checkout or
`re4mepc` from any directory to open the Python/Tk desktop launcher. The CLI
requires `~/.local/bin` on `PATH`; the installer prints how to add it when needed.
Use `make setup` for preparation without desktop installation. `make uninstall`
removes the installed CLI and menu entry while preserving game data and saves.

`re4mepc --help` lists commands; `re4mepc import /path/to/game.apk`,
`re4mepc check` and `re4mepc run` import, validate and start the game.
The checkout equivalents are `make import APK="/path/to/game.apk"`,
`make check-game` and `make run`. `make cli ARGS="..."` exposes every CLI
operation; ordinary targets accept extra options through `ARGS`.
`DESKTOP_ARGS` applies to `make install`, `make desktop` and `make uninstall`.
An installation with `DESKTOP_ARGS="--game /external/re4/game"` uses that
folder for game commands; an explicit CLI `--game` overrides it. Keep the
checkout and its `.venv` in place, and rerun installation after moving them.
The existing `./setup.sh` and `./re4pc.sh` entry points remain supported.

APK import and
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

The launcher supports English, Spanish, French, German, Italian and Japanese.
Its language changes immediately, including open dialogs; the separate game
language preference applies at the next game launch. Portable builds include
IPAGothic and its license for Japanese text on systems without CJK fonts.
Source installations need a Japanese font such as `fonts-ipafont-gothic` on
Debian/Ubuntu or `noto-fonts-cjk` on Arch Linux.

Settings expose keyboard/controller/mouse bindings, mouse
and controller sensitivity, invert Y, stick dead zone, window mode and
presentation rate. Current source offers native 20 FPS and interpolated
30/60/90/120/144/165/240 FPS or Uncapped, with the qualification scope described
in the [FPS guide](fps-performance.md). The frozen 2026-10-14 packages predate
that feature and retain their original 20 FPS mode. Settings tabs scroll on
smaller windows.
Import requires an unused destination.
The user supplies the APK; packages contain no game libraries or assets.

Game rendering uses an 800 × 480 logical framebuffer. Resizable/HiDPI drawable
sizes use an aspect-preserving blit with black letterboxes. SDL mouse coordinates
map through that same transform; presses in bars are ignored and releases during
a drag are clamped to the logical edge. Movies, diagnostics and the menu
focus outline draw into that logical surface. Screenshots capture its 800 × 480 pixels.
Alt+Enter toggles borderless desktop fullscreen, F3 diagnostics, Tab cursor,
F12 quit. Held input is released on focus loss, device removal and remapping.

Default controllers use left-stick tank movement, right-stick look, triggers
for aim/fire, A action, X reload, Y knife, Start status, and D-pad navigation.
In PC menus the D-pad or left stick moves the focus between the game's buttons
and A or B presses the focused one; there is no virtual cursor. All devices share named
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
re4mepc backup
re4mepc backups
re4mepc export-backup SNAPSHOT_ID '/path/with spaces/save-backup.zip'
re4mepc import-backup '/path/with spaces/save-backup.zip'
re4mepc restore-backup SNAPSHOT_ID
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

## Current public-test packages — 2026-10-14

The [refreshed experimental prerelease](https://github.com/aurelioochoa/re4mepc/releases/tag/v0.1.0-experimental.20261014)
includes the six-language selectors, bundled Japanese fonts and the dependency-notice
staging fix. Its [qualification summary](qualification-summary.md) records the new
artifact hashes and validation image IDs. Both formats pass clean Ubuntu 22.04,
Ubuntu 24.04 and Arch smoke/upgrade checks with no host Python/compiler, all six
launcher languages, saved language preferences and bundled Japanese glyph coverage.
Both formats also check all six native game-language IDs and 160 ticks per language
on Ubuntu 22.04. First-mission, inventory/submenu/cancellation and native save/load
replays pass on AMD RX 6700S using the refreshed bundled runtimes. These checks
remain separate from campaign, endurance and physical-device qualification.

Reproduce clean-system and preceding-release upgrade checks with:

```bash
.venv/bin/python tools/validate_package.py \
  --dist /external/refreshed-packages --previous-dist /external/20261013-packages \
  --output /external/refreshed-package-validation
```

The validator uses each format's own interpreter for the language checks. Japanese
font selection and glyph coverage are checked against a font inside that package.
Game data and all raw reports/captures remain outside the checkout. The previous
qualification below is historical and does not certify refreshed artifact bytes.

## Previous candidate qualification — 2026-10-13

The candidate pair includes desktop menu routing, achievement gallery exports
and optional portable save/media bundles, plus bounded JNI class-reference
allocation. Both formats pass clean Ubuntu 22.04,
Ubuntu 24.04 and Arch containers on these exact bytes:

| Artifact | SHA-256 |
|---|---|
| AppImage | dbf6dc7df6f70a2e96ee15a8eb89a3c350ea3cb84d90334cc491bb5a6c7d5c11 |
| Portable tar.gz | 20d94e814d2a0cf0aaf39c832779ccbcf1ec14c1d44027745ea7dcbe6495cd50 |

| Target | Validation image ID |
|---|---|
| Ubuntu 22.04 | sha256:4ef2da8a158d29e1f70e8c82b758d2e7dc8ca7230fc92148832ab4396faa566f |
| Ubuntu 24.04 | sha256:42a99fb2ec2edf3482ff703a764640a679b165bebe9030e4d35a38e01038dcac |
| Arch | sha256:004bdc81275499b16eb5b2722093c3adc2973c225d28e6d581ecfeeacf091ec7 |

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
`qualified-candidate-packages`, `qualified-package-validation`,
`qualified-package-amd` and `qualified-natural-package-menu-retry`.
Reproduce with:

```bash
.venv/bin/python tools/validate_package.py \
  --dist /external/candidate-packages --previous-dist /external/preceding-packages \
  --output /external/package-validation
```

Both formats also open a visible window and execute 160 startup ticks on the
host's AMD RX 6700S and Radeon 680M with Mesa 26.1.5. The selector and renderer
identity are recorded per run. These checks use dummy audio and cover startup,
not extended gameplay on each driver. An initial probe used a symlinked XDG state
path and was rejected by snapshot path validation; canonicalizing that test path
allowed both GPUs to pass without a package change. Intel and NVIDIA hardware
and a physical controller are unavailable.

Both final formats also replay 1,720 ticks of fresh-install keyboard/mouse input
through the first mission, manual panels, movement and inventory. Reviewed
captures show the item submenu, inventory return and gameplay return after
Escape/Start cancellation. Native save/load passes in both bundled runtimes.
These inputs do not write progression records or request synthetic stage changes;
they also do not complete a mission. A first runner attempt reused its extraction
directory as an evidence directory and stopped before launching; the retry uses
separate directories and is the qualification evidence.

These are automated smoke-qualified candidates. The full release gate remains
incomplete: natural campaign progression, physical controller hot-plug, audible
speaker output, physical display/HiDPI checks and extended package gameplay on
hardware drivers still need evidence. Source desktop checks cover resizing, fullscreen,
focus/cursor capture and SDL virtual-controller disconnect. Available hardware
is AMD RX 6700S/680M. The earlier candidates with AppImage hash beginning
`eb2df02f` and archive hash beginning `f74498ac` were superseded by the JNI fix;
the next pair beginning `49a0efe2` / `ec0b1f22` was superseded by inventory
cancellation. Their passing reports do not qualify the new bytes. Repacking invalidates all
qualification attached to the current hashes.

The 2026-10-13 prerelease is **experimental and not fully campaign-qualified**.
The final runtime's two-hour soak was stopped at the user's request after its
2,880.043-second checkpoint and remains incomplete. A native exception during
title-to-difficulty component initialization remains unresolved; 20 subsequent
entry trials passed, which does not establish an intermittent failure is fixed.
See the [authored qualification summary](qualification-summary.md) for the exact
scope, failures and manual handoff. Release assets contain only the audited host
packages, checksums and that summary; private game-derived evidence stays external.
