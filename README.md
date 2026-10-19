# Resident Evil 4 Mobile PC Port

**English** · [Español](README.es.md)

![Resident Evil 4 Mobile — Tux as Leon and Ashley in a misty village](docs/readme-banner.png)

Play the original **Resident Evil 4 Mobile Android** engine in a Linux desktop window with keyboard, mouse and controller support. `re4mepc` is an experimental compatibility host: Unicorn executes the ARM32 libraries, SDL2 handles the window and audio, and a bridge maps OpenGL ES 1 to desktop OpenGL. No Android installation is required.

**Bring your own game:** supply a compatible APK. The project does not include or download the game. Imported libraries, resources and saves stay outside the checkout. Full campaign completion has not been validated.

[Gameplay](#gameplay) · [Quick start](#quick-start) · [Game files](#game-files) · [Controls](#controls) · [Development](#development)

## Gameplay

![Four Linux gameplay captures: village exploration, handgun aiming, village gameplay and knife stance](docs/gameplay-mosaic.png)

Actual Linux desktop captures; each frame preserves the original **800×480** game image. Clockwise from the top left: exploration, handgun aiming, village gameplay and knife stance. Game artwork © Capcom. The banner is generated artwork; see [references and prompts](docs/banner-artwork.md).

## Requirements

- **Linux x86_64** with a graphical desktop, audio device and desktop **OpenGL compatibility profile**.
- **Python 3.10+**, `venv`, Tk, GNU Make, a C compiler, `pkg-config` and SDL2 development headers for source installations.
- **FFmpeg** for original audio and movies. Japanese text needs suitable fonts.

On **Arch Linux**, install `python tk make gcc pkgconf sdl2-compat ffmpeg mesa noto-fonts-cjk`. On **Debian/Ubuntu**, install `python3-venv python3-tk build-essential pkg-config libsdl2-dev libgl1-mesa-dev ffmpeg fonts-ipafont-gothic`.

Portable releases bundle application dependencies, including Japanese fonts; host graphics drivers and system runtime libraries remain required. Windows, macOS and Linux ARM64 are outside this release.

## Quick start

Install the system prerequisites above, then:

```sh
git clone https://github.com/aurelioochoa/re4mepc.git
cd re4mepc
make install
make play
```

`make install` prepares the environment and installs the CLI and applications-menu entry for your user. Keep the checkout and `.venv` in place. For setup without desktop integration, use `make setup` followed by `make play`.

In the launcher, choose **Import APK**, select your compatible APK and an unused destination folder, then choose **Play** when import completes. For direct terminal use:

```sh
re4mepc import "/path/to/Resident Evil 4.apk"
re4mepc check
re4mepc run
```

If the command is not found, add `~/.local/bin` to `PATH` with `export PATH="$HOME/.local/bin:$PATH"`, or run `~/.local/bin/re4mepc`. From the checkout, use `make import APK="/path/to/game.apk"`, `make check-game` and `make run`.

### Portable builds

The [experimental prerelease](https://github.com/aurelioochoa/re4mepc/releases/tag/v0.1.0-experimental.20261014) provides an AppImage, portable archive and `SHA256SUMS`. Check the chosen download against the hashes in the [qualification summary](docs/qualification-summary.md). These packages contain no game data and are not fully campaign-qualified.

Make the AppImage executable and run it; if FUSE is unavailable, add `--appimage-extract-and-run`. For the archive, extract it and run `re4mepc/AppRun`. Both open the launcher without arguments and accept the same CLI commands as `re4mepc`. Build them with `make setup` and `make package` using Docker. See [portable build instructions](docs/advanced-usage.md#portable-builds) and [distribution requirements](docs/desktop-release.md).

## Game files

The importer restores the APK's resources and verifies both ARM libraries and every required stage resource before installing. It never overwrites an existing destination, even an empty directory. Repackaged APKs may work if they contain the same libraries and complete resources.

| Supported library | SHA-256 |
| --- | --- |
| `libbio4af.so` | `6f6e52ef26b096cda44fc08c3f541cdc3bf1056a88f13fc1c3e17201589a0423` |
| `libmc_eruption_for_android_jni.so` | `25109c3b799045312073243b644f6053726689d7baf05bcf09b7acd786cff4f6` |

Import, check and run enforce these hashes. Use `re4mepc import "/path/to/game.apk" --output /external/re4/game` to select another location, then pass `--game /external/re4/game` to check or run. See [engine validation and migration](docs/advanced-usage.md#data-locations-and-supported-engine).

## Launcher

![Native case-file launcher with village photograph and installation controls](docs/launcher-preview.png)

Open it with `re4mepc`, `make play` or `make launcher`.

- **Import APK / Browse:** import into a new folder or select an existing installation.
- **Play / Stop:** start the game or stop the active operation.
- **Settings & controls:** configure display, keyboard, mouse, controllers and laser sight; changes apply on the next launch.
- **Save backups:** create, import, export, restore or delete snapshots while the game is stopped.
- **Diagnostics / View logs:** collect measurements or inspect optional session output.

The launcher supports mouse and keyboard navigation and adapts down to 640×520. See [launcher behavior](docs/advanced-usage.md#graphical-launcher), [settings and backup windows](docs/dialogs.md), and [artwork provenance](docs/launcher-assets.md).

### Languages

**Game language** and **Launcher language** independently offer **English, Spanish, French, German, Italian and Japanese**. Launcher changes apply immediately, including open dialogs; game changes apply on the next launch. **Use game's saved language** preserves the engine's own selection. Both preferences persist in `settings.json`.

For a single session, use `re4mepc run --language es` or `--language saved`. Supported codes are `en`, `es`, `fr`, `de`, `it`, `ja` and `saved`. Current portable builds bundle IPAGothic and its license; older packages need updating or rebuilding. See [language details](docs/advanced-usage.md#languages).

### Achievements

**Achievements** displays 21 local goals, including mission/rank progress, weapon purchases and tune-ups, and a Platinum for earning the other 20. Existing saves recover mission and rank progress after play; purchases and tune-ups count when observed by the launcher.

**Settings & controls → Achievements** enables unlock screenshots or silent replay clips. The gallery exports selected or all captures with metadata and deduplicates shared files. Achievement records are part of save backups; referenced media requires **Include achievement media** during export. See [achievement coverage](docs/achievements.md) and [portable captures](docs/portable-captures.md).

### Desktop integration

`make desktop` installs or refreshes the applications-menu entry. Add `DESKTOP_ARGS="--desktop"` for a desktop shortcut; `--apk '/path/to/game.apk'` or `--icon '/path/to/icon.png'` chooses a local icon. Existing installed icons are preserved by default. `make uninstall` removes the CLI and desktop integration while preserving game data and saves. See [desktop installation details](docs/advanced-usage.md#linux-app-and-desktop-shortcut).

## Controls

| Input | Action |
| --- | --- |
| W / S | Forward / backward |
| A / D | Turn left / right (classic tank movement) |
| Arrows | Same directions; menu navigation |
| Mouse movement | Look and aim |
| Hold right mouse / X | Aim |
| Left mouse / Z | Fire |
| R | Reload |
| Hold F, then left mouse / Z | Ready knife, then slash |
| E / Enter / Space | Context action; Enter / Space advance story text |
| Escape | Open status; cancel inventory submenu or return to gameplay |
| Tab | Release / capture cursor |
| F3 | Toggle diagnostics |
| Alt+Enter | Toggle borderless fullscreen |
| F12 | Close the game window |

To pick up a ground item, press Space to select it and again to take it. PC mode hides the main touch controls and captures the cursor during gameplay; Tab frees it, and a scene click recaptures without firing. Contextual actions, companion commands, scope controls, status and menus remain visible. Losing focus releases held inputs. Enter, Space, Escape or a click skips a video.

In menus, WASD/D-pad or the right stick moves the cursor, Space/A selects, Enter/B continues or confirms the recognized difficulty slider, and Escape/Start cancels or returns. Normal mouse navigation also works.

Controllers use left stick for movement/tank turns, right stick for look, triggers for aim/fire, A for action, X for reload, Y for knife and Start for status. Physical controller behavior remains unverified. Remap inputs and sensitivities in **Settings & controls**; Tab, F3 and F12 are reserved. Use `re4mepc run --controls touch` for original touch input. See [full controls](docs/advanced-usage.md#controls) and [menu behavior](docs/menu-controls.md).

## Saves and settings

| Content | Default location |
| --- | --- |
| Imported game | `~/.local/share/re4mepc/game` |
| Saves | `~/.local/share/re4mepc/game/saves` |
| Achievement screenshots/clips | `~/.local/share/re4mepc/game/achievement-media` |
| Settings | `~/.config/re4mepc/settings.json` |
| Save snapshots | `~/.local/state/re4mepc/backups/<installation-path-hash>` |
| Audio cache | `~/.local/share/re4mepc/game/cache/audio` |
| Experimental texture cache | `~/.cache/re4mepc/textures` |
| Diagnostics and test artifacts | `~/.local/state/re4mepc/logs` |

Absolute `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME` and `XDG_CACHE_HOME` override the base directories; empty or relative values use defaults. Replacing portable application files preserves external data.

The host snapshots saves before startup and around native saves, retaining ten distinct sets. With the game stopped:

```sh
re4mepc backup
re4mepc backups
re4mepc export-backup SNAPSHOT_ID "/path/to/backup.zip"
re4mepc import-backup "/path/to/backup.zip"
re4mepc restore-backup SNAPSHOT_ID
```

Use an ID listed by `backups`. Import creates an inactive snapshot; restore activates it after verification and keeps a recovery copy. Add `--include-media` when exporting to include referenced achievement captures. See [backup operations](docs/advanced-usage.md#save-backups) and [storage and recovery](docs/desktop-release.md).

## Status and limitations

Linux x86_64 is the target. The host needs shared memory below 4 GiB and OpenGL compatibility functions. Resizing, HiDPI, controllers and borderless fullscreen are implemented, but physical controllers, display/HiDPI and audible speakers still lack qualification.

Visible tests have exercised the title, English menus, original audio/video and village gameplay. Gameplay and presentation run at **20 Hz** to preserve the engine's mission clock; higher rates also speed up game logic. ARM execution and Python bridges add overhead, especially during loading. A safe higher rendering rate has not been established.

**Full campaign completion is unverified.** The earlier two-hour soak stopped at its preserved 2,880.043-second checkpoint and remains incomplete. An intermittent native difficulty-initialization exception is unresolved; no loading optimization met the performance gate.

The experimental packages have documented smoke/upgrade checks on Ubuntu 22.04, Ubuntu 24.04 and Arch, language checks, and first-mission/inventory/save replays on AMD RX 6700S. These checks do not establish full campaign support; Intel/NVIDIA hardware was unavailable. See [VALIDATION.md](VALIDATION.md), the [qualification summary](docs/qualification-summary.md), [campaign coverage](docs/campaign-coverage.md), and [roadmap measurements](docs/roadmap-results.md).

## Development

| Command | Purpose |
| --- | --- |
| `make help` | Show available targets |
| `make setup` / `make build` | Prepare dependencies / compile native helpers |
| `make run` / `make dev` | Run with live terminal logs |
| `make check` | Build helpers and run synthetic tests without an APK |
| `make verify` | Run component tests and audit source/index/history |
| `make check-game` | Verify imported game data |
| `make visible-test` | Exercise startup, video, menus, rendering, audio and save/load |
| `make controls-test` | Exercise gameplay input and camera behavior |
| `make package` | Build AppImage and portable archive |
| `make clean` / `make distclean` | Remove helpers/caches / also remove `.venv` |

Real-engine tests open desktop windows and use isolated game copies. Cleaning preserves imported data, saves and logs. `make audit-source` checks the Git index, history and stored blobs against an explicit allowlist; documentation paths must be reviewed there too.

See [detailed usage, architecture and testing](docs/advanced-usage.md), [diagnostics](docs/diagnostics.md), [rendering audit](docs/render-audit.md), and [reverse-engineering workflow](docs/rea-workflow.md).

## License and credits

The host's original source is licensed under [MIT](LICENSE). This excludes original game data, trademarks and third-party dependencies. Resident Evil belongs to its respective rights holders. The repository distributes the host and documentation, not the game.
