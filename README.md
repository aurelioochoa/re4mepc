![re4mepc — Resident Evil 4 Mobile Linux PC port; Tux dressed as Leon and Ashley in a misty village](docs/readme-banner.png)

# Resident Evil 4 Mobile on Linux

## About

Play the original ARM32 Android engine in a Linux desktop window with mouse and keyboard controls. **re4mepc** is an experimental compatibility host: Unicorn executes the game's native libraries, SDL2 handles the window and audio, and a graphics bridge translates OpenGL ES 1 rendering to desktop OpenGL.

You supply the APK. The repository contains the host, importer, synthetic tests and documentation; it never downloads the game. Imported libraries, resources, saves and captures stay outside the checkout. No Android installation is required.

[Setup](#setup-and-play) · [Linux app and desktop shortcut](#linux-app-and-desktop-shortcut) · [Controls](#controls) · [How the port was made](#how-the-port-was-made) · [How it works](#how-it-works) · [Español](#español)

## Gameplay gallery

<p>
  <a href="https://www.mobygames.com/game/42794/resident-evil-4-mobile-edition/screenshots/"><img src="https://cdn.mobygames.com/d6238dc0-ac1c-11ed-9c12-02420a00012f.webp" width="420" alt="Original mobile edition: Leon aiming his handgun at a villager, with the red laser sight and touch controls visible"></a>
  <a href="https://www.mobygames.com/game/42794/resident-evil-4-mobile-edition/screenshots/"><img src="https://cdn.mobygames.com/dc72a67a-ac1c-11ed-9c12-02420a00012f.webp" width="420" alt="Original mobile edition: Leon facing a chainsaw-wielding Ganado in the village"></a>
</p>

Reference screenshots of the original **Resident Evil 4: Mobile Edition**, hosted by [MobyGames](https://www.mobygames.com/game/42794/resident-evil-4-mobile-edition/screenshots/). These show the mobile game and its touch interface, rather than captures from this Linux port. Game artwork © Capcom. The generated Tux banner's references and prompts are documented in [Banner artwork](docs/banner-artwork.md).

## Status and limitations

Linux x86_64 is the first target. Shared guest memory requires a mapping below 4 GiB, and the renderer requires desktop OpenGL compatibility functions. Windows, macOS, ARM64 Linux, controllers, resizing and fullscreen are not implemented.

The title, English menus, original video and audio, and village gameplay have been exercised in visible desktop tests. ARM translation and Python import calls impose substantial overhead, especially during level loading; this is not yet a performance-equivalent native x86 port. A full campaign playthrough has not been validated. See [VALIDATION.md](VALIDATION.md) for the recorded checks and limitations.

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

## Linux app and desktop shortcut

After setup and importing your game, build the native helpers and install an executable launcher and applications-menu entry with the APK's original icon:

```bash
make desktop DESKTOP_ARGS="--apk '/path/to/Resident Evil 4.apk'"
```

The installer chooses the largest PNG named `icon`, `ic_launcher`, `ic_launcher_round`, `app_icon` or `launcher_icon` under the APK's `res/drawable*` or `res/mipmap*` directories. For APKs with other icon names, or to use your own cover image, supply a PNG instead:

```bash
make desktop DESKTOP_ARGS="--icon '/path/to/re4-cover.png'"
```

Launch **Resident Evil 4 Mobile** from your applications menu, or run `~/.local/bin/re4mepc` from any directory. To also place a double-click shortcut on your desktop:

```bash
make desktop DESKTOP_ARGS="--desktop --apk '/path/to/Resident Evil 4.apk'"
```

The desktop folder follows `xdg-user-dir DESKTOP`, including localized folder names. Your desktop may require **Allow Launching** or **Trust this launcher** on first use. If no desktop folder is configured, omit `--desktop` to use the applications menu.

This installs a small executable script that runs the host from this checkout and its `.venv`; keep both in place. It is not a standalone binary. A terminal opens alongside the game for status and errors, and runtime logs append to `~/.local/state/re4mepc/logs/desktop.log`. Launch options still work, for example `~/.local/bin/re4mepc --skip-videos`.

The menu entry and a byte-for-byte copy of the chosen PNG are stored under `~/.local/share/applications/re4mepc.desktop` and `~/.local/share/re4mepc/icons/re4mepc.png`, respecting `XDG_DATA_HOME`. Logs respect `XDG_STATE_HOME`. Icons are kept locally and are never added to the repository. Subsequent `make desktop` calls reuse the installed icon. If you move the checkout, run the installer again at its new location. For a custom game location, include `--game /external/re4/game` in `DESKTOP_ARGS`.

```bash
make uninstall-desktop                         # Remove menu entry, executable and icon
make uninstall-desktop DESKTOP_ARGS="--desktop" # Also remove the desktop shortcut
```

Uninstalling the launcher preserves the checkout, imported game, saves and logs.

## Controls

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

## How the port was made

The port was built around the native engine distributed in the Android APK. The original ARM machine code still handles game logic; the work in this repository supplies the environment it expects and adapts it to a desktop.

1. **Identify the engine and restore its resources.** The importer extracts `libbio4af.so` and `libmc_eruption_for_android_jni.so`, follows the APK's asset manifest and removes packaging-only `.png` suffixes to restore resource names. Both library hashes and the required resources are checked before an import is installed.
2. **Load and link the ARM libraries.** A custom ELF loader maps the libraries into shared memory, reads their exported symbols and applies ARM relocations. Calls to Android or C runtime imports are connected to host implementations. Unicorn executes ARM and Thumb instructions; EABI helpers supply the floating point operations the engine imports.
3. **Implement the Android interfaces the engine uses.** A small JNI layer supplies objects, strings, arrays, native method registration and the requested application services. The host calls the engine's `JNI_OnLoad` and Android lifecycle callbacks directly. Bionic/libc replacements provide memory, file and save operations. Unsupported imports and JNI services fail with an error.
4. **Bridge graphics and media to Linux.** Fixed-function GLES calls are mapped to desktop OpenGL, including expansion of OES paletted textures. FFmpeg decodes the original audio and movies, while SDL2 presents the window and mixes audio. Small C helpers accelerate frequent memory operations and the audio callback.
5. **Add desktop input at the engine's own control points.** SDL keyboard and mouse events feed menus through the original key/touch callbacks. During gameplay, symbol-based hooks translate desktop input into the engine's control state and camera angles. Mouse look adjusts the native camera orbit before its wall-collision checks, and aim transitions preserve vertical look direction.
6. **Check components, then exercise the real engine.** Synthetic tests cover the loader and service bridges without game data. Separate visible tests use a locally imported engine to check startup, rendering, audio, save/load and gameplay controls. Recorded results and remaining gaps are in [VALIDATION.md](VALIDATION.md).

The symbol inspection utility, [tools/disassemble.py](tools/disassemble.py), uses ELF symbols and Capstone to inspect a locally supplied library. Hooks depend on the supported engine's symbol layout and offsets, which is why matching library hashes are required. Original libraries, assets and disassembly dumps are excluded from publication.

## How it works

At startup, the host validates the imported data, allocates shared ARM32 memory, loads and relocates the libraries, runs their constructors and calls their JNI initialization and lifecycle methods. The default window is 800 × 480.

```text
Your APK → local importer → validated ARM libraries + resources
                                      │
                          Unicorn executes the engine
                                      │
                    Imported calls → Linux host bridges
                                      │
                  OpenGL rendering · SDL2 audio · file I/O

Each frame:
SDL2 input → desktop control bridge → engine draw callback
           → movie overlay update → SDL2 window swap
```

The engine sees 32-bit addresses. The host maps a 256 MiB region below 4 GiB into both Unicorn and the Linux process at the same address, letting host bridges read validated guest buffers directly. This shared mapping is one reason the current implementation requires Linux x86_64.

When the engine calls an imported function, an ARM trampoline routes that call to a Python or native C implementation. Rendering calls reach desktop OpenGL; file calls operate on the imported data and save directories; JNI media requests reach the FFmpeg/SDL2 media layer. The host then returns control to the ARM engine. Android's Java application and operating system are replaced by this limited set of services.

The frame loop polls desktop events, applies queued input and camera changes, calls `native_onDrawFrame`, updates movie playback and swaps the window. It targets 45 frames per second when processing allows. ARM execution and host callbacks still cost time, so loading and gameplay speed depend on this compatibility layer.

| Responsibility | Source |
| --- | --- |
| APK restoration and engine validation | [assets.py](re4pc/assets.py) |
| ARM/Thumb execution, ELF loading and relocations | [arm.py](re4pc/arm.py) |
| Android JNI services and lifecycle entry points | [jni.py](re4pc/jni.py), [game.py](re4pc/game.py) |
| C runtime, files and ARM math helpers | [bionic.py](re4pc/bionic.py), [eabi.py](re4pc/eabi.py) |
| GLES rendering and texture conversion | [graphics.py](re4pc/graphics.py), [textures.py](re4pc/textures.py) |
| Keyboard, touch routing and gameplay mouse controls | [input.py](re4pc/input.py), [pc_controls.py](re4pc/pc_controls.py) |
| FFmpeg audio/movie decoding and SDL2 mixing | [media.py](re4pc/media.py), [audio.c](native/audio.c) |
| Fast memory imports | [fast.py](re4pc/fast.py), [fast.c](native/fast.c) |

## Data locations and supported engine

The importer restores the bundled files' original names and checks both ARM
libraries and every required stage resource. Extraction is temporary until
validation succeeds. Existing destinations, including empty directories and
symlinks, are never overwritten.

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

## Development and testing

Run `make` to list the available commands. The synthetic suite needs no APK; tests that exercise the real engine open a desktop window and use isolated game copies.

| Command | Purpose |
| --- | --- |
| `make build` | Compile the native memory and audio helpers |
| `make desktop` | Build helpers and install the per-user executable and app shortcut |
| `make uninstall-desktop` | Remove the installed launcher and icon; preserve game data |
| `make run` / `make dev` | Launch the game with live terminal logs |
| `make check` | Build helpers and run synthetic component tests |
| `make verify` | Run component tests and audit the Git index/history |
| `make check-game` | Validate the imported libraries and resources |
| `make visible-test` | Exercise startup, video, menus, rendering, audio and save/load |
| `make controls-test` | Exercise gameplay controls and camera behavior |
| `make clean` / `make distclean` | Remove build caches / also remove `.venv` |

<details>
<summary>Runtime logs, command options and cleaning</summary>

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

To capture a bounded run and its measurements:

```bash
./re4pc.sh run --frames 600 --screenshot /tmp/frame.png --stats /tmp/stats.json
```

</details>

<details>
<summary>Component coverage and visible game tests</summary>

```bash
make test
make visible-test
make controls-test
```

`make test` checks APK restoration and rejection of unsafe paths, texture palette decoding, ARM/Thumb execution, floating point helpers, JNI argument alignment, save file I/O, and the native memory bridge, including invalid-pointer rejection and quick press/release sampling. These are component tests; they do not launch a hidden game.

`make visible-test` opens a normal SDL window, plays the original intro, displays the title, clicks through to the menu, and plays audio through the desktop audio device. It creates a fresh game copy with separate saves under the external
`logs/visible-test/run-*/game-*` directory and checks the original engine's save/load routines by saving a language change, changing it in memory, loading it back and restoring the original setting. Captures, the input replay, and measured statistics are written to that run directory. The replay accepts F12 and the window's close button; other desktop input is ignored during this timed test so clicks cannot interrupt its sequence. Rendering, video playback, actual mixed audio output, input delivery and nonblank captures are checked automatically; screenshots still need visual inspection for scene correctness.

`make controls-test` opens the real game window, uses an isolated story mission fixture and checks gameplay controls through SDL events one by one. It measures camera direction as well as player rotation, repeated aim transitions, idle drift, focus release and ammunition. Captures and measurements are saved under the external `logs/pc-controls/run-*` directory. F12 or closing the window interrupts the test.

</details>

<details>
<summary>Interactive test commands</summary>

For an interactive visible test with JSON commands on stdin:

```bash
.venv/bin/python -u tools/live_test.py
```

For example, enter `{"action":"screenshot","path":"/tmp/game.png"}` to capture the window, `{"action":"stats"}` for live measurements, or `{"action":"quit"}` to close it. It creates an isolated game copy with fresh saves; normal mouse and keyboard
events also reach this window. Once a mission is running, `{"action":"test_pc"}` runs visible SDL gameplay checks and writes captures and measurements to its external run directory. During this short test only F12 and close-window input are accepted.

</details>

<details>
<summary>Source audit, CI and test artifact locations</summary>

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
explicit source/documentation allowlist, symlinks, submodules, unapproved binary contents,
and large encoded payloads or disassembly dumps. It also checks past commits
whose forbidden files have been deleted from the tip. Updating the allowed
source inventory requires editing `tools/audit_source.py` and reviewing the
new source. The audit does not replace reviewing source provenance.

CI installs host dependencies, builds the C helpers, runs synthetic tests and
audits the complete fetched history. It needs no APK, game saves or game
captures. Binary distribution packages containing the game are not produced.

The README banner is generated fan artwork at `docs/readme-banner.png`. Its exact path and reviewed SHA-256 are included in the publication allowlist; altered or additional binary images are rejected. The previous SVG remains available at `docs/readme-banner.svg`. References and generation prompts are recorded in [Banner artwork](docs/banner-artwork.md). The gameplay gallery links to external reference screenshots; game assets and local captures remain outside the repository.

</details>

## Español

### Qué es este proyecto

**re4mepc** permite ejecutar el motor original de Resident Evil 4 Mobile para Android en una ventana de Linux, con teclado y ratón. Es un port experimental de compatibilidad: Unicorn ejecuta las bibliotecas ARM32 originales, SDL2 gestiona la ventana y el audio, y un puente convierte las llamadas de OpenGL ES 1 a OpenGL de escritorio. No requiere instalar Android.

Debes proporcionar tu propio APK compatible. El proyecto no descarga ni incluye el juego; sus bibliotecas, recursos y partidas guardadas se almacenan fuera del repositorio.

### Instalación y ejecución

Necesitas Linux **x86_64**, Python 3.10 o posterior con `venv`, un compilador de C, `pkg-config`, las cabeceras de desarrollo de SDL2, OpenGL de escritorio con perfil de compatibilidad y FFmpeg. Ejecuta el juego desde una sesión de escritorio con pantalla y audio disponibles.

- **Arch Linux:** instala `python gcc pkgconf sdl2-compat ffmpeg mesa`.
- **Debian/Ubuntu:** instala `python3-venv build-essential pkg-config libsdl2-dev libgl1-mesa-dev ffmpeg`.

```bash
git clone https://github.com/aurelioochoa/re4mepc.git
cd re4mepc
./setup.sh
./re4pc.sh import '/ruta/a/Resident Evil 4.apk'
./re4pc.sh check
./re4pc.sh run
```

Para crear una aplicación en el menú de Linux con el icono original del APK, ejecuta `make desktop DESKTOP_ARGS="--apk '/ruta/al/juego.apk'"` después de instalar e importar el juego. Añade `--desktop` para crear también un acceso directo en el escritorio, o usa `--icon '/ruta/a/portada.png'` para elegir una imagen PNG. El ejecutable `~/.local/bin/re4mepc` utiliza este repositorio y su `.venv`; conserva ambos en su ubicación. Para quitar los accesos e icono, usa `make uninstall-desktop DESKTOP_ARGS="--desktop"`; el juego y las partidas se conservan.

La importación verifica las dos bibliotecas y todos los recursos necesarios antes de instalar los datos. Solo se admite el motor con los hashes indicados en [Data locations and supported engine](#data-locations-and-supported-engine). Un APK reempaquetado puede funcionar si conserva esas bibliotecas y los recursos completos. El importador no sobrescribe destinos existentes, aunque estén vacíos.

### Controles

| Entrada | Acción |
| --- | --- |
| W / S | Avanzar / retroceder |
| A / D | Girar a izquierda / derecha, con movimiento clásico tipo tanque |
| Flechas | Mismas direcciones; navegar por los menús |
| Mover el ratón | Mirar y apuntar |
| Mantener botón derecho / X | Apuntar |
| Botón izquierdo / Z | Disparar |
| R | Recargar |
| Mantener F y pulsar botón izquierdo / Z | Preparar el cuchillo y atacar |
| E / Enter / Espacio | Acción contextual; Enter / Espacio avanzan el texto |
| Escape | Menú de estado |
| Tab | Liberar / capturar el cursor; hacer clic para capturarlo de nuevo |
| F12 | Cerrar la ventana |

Los menús usan clics normales. Para confirmar con un deslizador móvil, arrastra la flecha de un extremo al otro. Enter, Espacio, Escape o un clic omiten el vídeo en reproducción. Al perder el foco, la ventana libera las teclas y el cursor.

El juego inicia en inglés. `./re4pc.sh run --language saved` conserva el idioma guardado por el juego; esta opción no añade una traducción al español. Para usar el ratón como pantalla táctil, ejecuta `./re4pc.sh run --controls touch`.

### Cómo se hizo el port y cómo funciona

El trabajo consistió en restaurar los archivos del APK, cargar las bibliotecas ELF de ARM y conectar sus llamadas externas con implementaciones para Linux. Se implementaron los servicios JNI que solicita el motor, operaciones de archivos y memoria, funciones matemáticas de ARM, el puente gráfico y la reproducción de audio y vídeo. Los controles de escritorio se añadieron mediante hooks basados en los símbolos y offsets del motor compatible.

Al arrancar, el host valida los datos, carga y enlaza las bibliotecas en una región de memoria compartida de 256 MiB situada por debajo de 4 GiB y llama a las funciones de inicialización y ciclo de vida originales. Unicorn ejecuta el código ARM/Thumb. Cuando el motor solicita un servicio externo, el host atiende la llamada en Python o C y devuelve el control al motor.

En cada fotograma, SDL2 recoge las entradas, el puente aplica los controles y ajustes de cámara, el motor ejecuta `native_onDrawFrame`, el host actualiza el vídeo y presenta la imagen. El ratón modifica la órbita de la cámara antes de las comprobaciones de colisión del propio motor.

### Datos, pruebas y limitaciones

Por defecto, los datos están en `~/.local/share/re4mepc/game`, las partidas en su subdirectorio `saves` y la caché de audio en `cache/audio`. Los registros y capturas de pruebas están en `~/.local/state/re4mepc/logs`. Se respetan `XDG_DATA_HOME` y `XDG_STATE_HOME` cuando contienen rutas absolutas. Puedes indicar otra ubicación con `--output` al importar y `--game` al comprobar o ejecutar.

- `make check` compila los helpers y ejecuta pruebas sintéticas sin necesitar el juego.
- `make verify` añade la auditoría de fuentes e historial Git.
- `make check-game` valida tu importación.
- `make visible-test` y `make controls-test` abren una ventana real y usan copias aisladas con partidas propias.

Se han probado el título, los menús en inglés, el audio y vídeo originales y el juego en la aldea. La campaña completa sigue sin validarse. La ejecución ARM y las llamadas a Python añaden sobrecarga, especialmente al cargar niveles. Windows, macOS, Linux ARM64, mandos, redimensionado y pantalla completa no están implementados. Consulta [VALIDATION.md](VALIDATION.md) para los resultados y límites registrados.

El código del host tiene licencia MIT; esa licencia excluye los datos originales del juego, las marcas y las dependencias de terceros.

## License

The source written for this host is MIT licensed. The license excludes original
game data, trademarks and third-party dependencies. Interoperability names,
symbols, offsets and hashes identify the supported engine; executable test
snippets are hand-written synthetic fixtures and host ABI trampolines.
