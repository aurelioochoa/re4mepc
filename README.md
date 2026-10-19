# Resident Evil 4 Mobile PC Port

[English](#english) · [Español](#español)

## English

![Resident Evil 4 Mobile — Tux as Leon and Ashley in a misty village](docs/readme-banner.png)

Play the original **Resident Evil 4 Mobile Android** engine in a Linux desktop window with keyboard, mouse and controller support. `re4mepc` is an experimental compatibility host: Unicorn executes the ARM32 libraries, SDL2 handles the window and audio, and a bridge maps OpenGL ES 1 to desktop OpenGL. No Android installation is required.

**Bring your own game:** supply a compatible APK. The project does not include or download the game. Imported libraries, resources and saves stay outside the checkout. Full campaign completion has not been validated.

[Gameplay](#gameplay) · [Quick start](#quick-start) · [Game files](#game-files) · [Controls](#controls) · [Development](#development)

### Gameplay

![Four Linux gameplay captures: village exploration, handgun aiming, village gameplay and knife stance](docs/gameplay-mosaic.png)

Actual Linux desktop captures; each frame preserves the original **800×480** game image. Clockwise from the top left: exploration, handgun aiming, village gameplay and knife stance. Game artwork © Capcom. The banner is generated artwork; see [references and prompts](docs/banner-artwork.md).

### Requirements

- **Linux x86_64** with a graphical desktop, audio device and desktop **OpenGL compatibility profile**.
- **Python 3.10+**, `venv`, Tk, GNU Make, a C compiler, `pkg-config` and SDL2 development headers for source installations.
- **FFmpeg** for original audio and movies. Japanese text needs suitable fonts.

On **Arch Linux**, install `python tk make gcc pkgconf sdl2-compat ffmpeg mesa noto-fonts-cjk`. On **Debian/Ubuntu**, install `python3-venv python3-tk build-essential pkg-config libsdl2-dev libgl1-mesa-dev ffmpeg fonts-ipafont-gothic`.

Portable releases bundle application dependencies, including Japanese fonts; host graphics drivers and system runtime libraries remain required. Windows, macOS and Linux ARM64 are outside this release.

### Quick start

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

#### Portable builds

The [experimental prerelease](https://github.com/aurelioochoa/re4mepc/releases/tag/v0.1.0-experimental.20261014) provides an AppImage, portable archive and `SHA256SUMS`. Check the chosen download against the hashes in the [qualification summary](docs/qualification-summary.md). These packages contain no game data and are not fully campaign-qualified.

Make the AppImage executable and run it; if FUSE is unavailable, add `--appimage-extract-and-run`. For the archive, extract it and run `re4mepc/AppRun`. Both open the launcher without arguments and accept the same CLI commands as `re4mepc`. Build them with `make setup` and `make package` using Docker. See [portable build instructions](docs/advanced-usage.md#portable-builds) and [distribution requirements](docs/desktop-release.md).

### Game files

The importer restores the APK's resources and verifies both ARM libraries and every required stage resource before installing. It never overwrites an existing destination, even an empty directory. Repackaged APKs may work if they contain the same libraries and complete resources.

| Supported library | SHA-256 |
| --- | --- |
| `libbio4af.so` | `6f6e52ef26b096cda44fc08c3f541cdc3bf1056a88f13fc1c3e17201589a0423` |
| `libmc_eruption_for_android_jni.so` | `25109c3b799045312073243b644f6053726689d7baf05bcf09b7acd786cff4f6` |

Import, check and run enforce these hashes. Use `re4mepc import "/path/to/game.apk" --output /external/re4/game` to select another location, then pass `--game /external/re4/game` to check or run. See [engine validation and migration](docs/advanced-usage.md#data-locations-and-supported-engine).

### Launcher

![Native case-file launcher with village photograph and installation controls](docs/launcher-preview.png)

Open it with `re4mepc`, `make play` or `make launcher`.

- **Import APK / Browse:** import into a new folder or select an existing installation.
- **Play / Stop:** start the game or stop the active operation.
- **Settings & controls:** configure display, keyboard, mouse, controllers and laser sight; changes apply on the next launch.
- **Save backups:** create, import, export, restore or delete snapshots while the game is stopped.
- **Diagnostics / View logs:** collect measurements or inspect optional session output.

The launcher supports mouse and keyboard navigation and adapts down to 640×520. See [launcher behavior](docs/advanced-usage.md#graphical-launcher), [settings and backup windows](docs/dialogs.md), and [artwork provenance](docs/launcher-assets.md).

#### Languages

**Game language** and **Launcher language** independently offer **English, Spanish, French, German, Italian and Japanese**. Launcher changes apply immediately, including open dialogs; game changes apply on the next launch. **Use game's saved language** preserves the engine's own selection. Both preferences persist in `settings.json`.

For a single session, use `re4mepc run --language es` or `--language saved`. Supported codes are `en`, `es`, `fr`, `de`, `it`, `ja` and `saved`. Current portable builds bundle IPAGothic and its license; older packages need updating or rebuilding. See [language details](docs/advanced-usage.md#languages).

#### Achievements

**Achievements** displays 21 local goals, including mission/rank progress, weapon purchases and tune-ups, and a Platinum for earning the other 20. Existing saves recover mission and rank progress after play; purchases and tune-ups count when observed by the launcher.

**Settings & controls → Achievements** enables unlock screenshots or silent replay clips. The gallery exports selected or all captures with metadata and deduplicates shared files. Achievement records are part of save backups; referenced media requires **Include achievement media** during export. See [achievement coverage](docs/achievements.md) and [portable captures](docs/portable-captures.md).

#### Desktop integration

`make desktop` installs or refreshes the applications-menu entry. Add `DESKTOP_ARGS="--desktop"` for a desktop shortcut; `--apk '/path/to/game.apk'` or `--icon '/path/to/icon.png'` chooses a local icon. Existing installed icons are preserved by default. `make uninstall` removes the CLI and desktop integration while preserving game data and saves. See [desktop installation details](docs/advanced-usage.md#linux-app-and-desktop-shortcut).

### Controls

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

### Saves and settings

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

### Status and limitations

Linux x86_64 is the target. The host needs shared memory below 4 GiB and OpenGL compatibility functions. Resizing, HiDPI, controllers and borderless fullscreen are implemented, but physical controllers, display/HiDPI and audible speakers still lack qualification.

Visible tests have exercised the title, English menus, original audio/video and village gameplay. Gameplay and presentation run at **20 Hz** to preserve the engine's mission clock; higher rates also speed up game logic. ARM execution and Python bridges add overhead, especially during loading. A safe higher rendering rate has not been established.

**Full campaign completion is unverified.** The earlier two-hour soak stopped at its preserved 2,880.043-second checkpoint and remains incomplete. An intermittent native difficulty-initialization exception is unresolved; no loading optimization met the performance gate.

The experimental packages have documented smoke/upgrade checks on Ubuntu 22.04, Ubuntu 24.04 and Arch, language checks, and first-mission/inventory/save replays on AMD RX 6700S. These checks do not establish full campaign support; Intel/NVIDIA hardware was unavailable. See [VALIDATION.md](VALIDATION.md), the [qualification summary](docs/qualification-summary.md), [campaign coverage](docs/campaign-coverage.md), and [roadmap measurements](docs/roadmap-results.md).

### Development

Contributions use this repository's GitHub issues and pull requests. Read the bilingual [contribution guide](CONTRIBUTING.md#english) and [piracy policy](CODE_OF_CONDUCT.md#english).

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

### License and credits

The host's original source is licensed under [MIT](LICENSE). This excludes original game data, trademarks and third-party dependencies. Resident Evil belongs to its respective rights holders. The repository distributes the host and documentation, not the game.

## Español

![Resident Evil 4 Mobile: Tux como Leon y Ashley en una aldea con niebla](docs/readme-banner.png)

Ejecuta el motor original de **Resident Evil 4 Mobile para Android** en una ventana de Linux con teclado, ratón y mando. `re4mepc` es un host experimental de compatibilidad: Unicorn ejecuta las bibliotecas ARM32, SDL2 gestiona la ventana y el audio, y un puente traduce OpenGL ES 1 a OpenGL de escritorio. No necesitas instalar Android.

**Debes aportar tu propio juego:** proporciona un APK compatible. El proyecto no incluye ni descarga el juego. Las bibliotecas importadas, recursos y partidas se guardan fuera del repositorio. La campaña completa no está validada.

[Jugabilidad](#jugabilidad) · [Inicio rápido](#inicio-rápido) · [Archivos del juego](#archivos-del-juego) · [Controles](#controles) · [Desarrollo](#desarrollo)

### Jugabilidad

![Cuatro capturas en Linux: exploración de la aldea, apuntado con pistola, juego en la aldea y postura con cuchillo](docs/gameplay-mosaic.png)

Capturas reales del escritorio Linux; cada imagen conserva la resolución original de **800×480**. En sentido horario desde arriba a la izquierda: exploración, apuntado con pistola, juego en la aldea y postura con cuchillo. Arte del juego © Capcom. El banner es arte generado; consulta las [referencias y prompts](docs/banner-artwork.md) (en inglés).

### Requisitos

- **Linux x86_64** con escritorio gráfico, dispositivo de audio y **perfil de compatibilidad de OpenGL de escritorio**.
- **Python 3.10 o posterior**, `venv`, Tk, GNU Make, compilador de C, `pkg-config` y cabeceras de desarrollo de SDL2 para instalar desde el código fuente.
- **FFmpeg** para audio y vídeos originales. El japonés requiere fuentes adecuadas.

En **Arch Linux**, instala `python tk make gcc pkgconf sdl2-compat ffmpeg mesa noto-fonts-cjk`. En **Debian/Ubuntu**, instala `python3-venv python3-tk build-essential pkg-config libsdl2-dev libgl1-mesa-dev ffmpeg fonts-ipafont-gothic`.

Las versiones portátiles incluyen las dependencias de la aplicación y fuentes japonesas; siguen necesitando los controladores gráficos y bibliotecas del sistema. Windows, macOS y Linux ARM64 quedan fuera de esta versión.

### Inicio rápido

Instala los requisitos del sistema y ejecuta:

```sh
git clone https://github.com/aurelioochoa/re4mepc.git
cd re4mepc
make install
make play
```

`make install` prepara el entorno e instala el CLI y la entrada del menú para tu usuario. Conserva el repositorio y `.venv` en su ubicación. Para preparar sin instalar accesos, usa `make setup` y después `make play`.

En el lanzador, elige **Import APK**, selecciona tu APK compatible y una carpeta de destino nueva; pulsa **Play** cuando termine. Para usar la terminal:

```sh
re4mepc import "/ruta/a/Resident Evil 4.apk"
re4mepc check
re4mepc run
```

Si no se encuentra el comando, añade `~/.local/bin` a `PATH` con `export PATH="$HOME/.local/bin:$PATH"` o ejecuta `~/.local/bin/re4mepc`. Desde el repositorio, usa `make import APK="/ruta/al/juego.apk"`, `make check-game` y `make run`.

#### Versiones portátiles

La [preversión experimental](https://github.com/aurelioochoa/re4mepc/releases/tag/v0.1.0-experimental.20261014) ofrece un AppImage, un archivo portátil y `SHA256SUMS`. Comprueba la descarga elegida con los hashes del [resumen de validación](docs/qualification-summary.md) (en inglés). Los paquetes no incluyen el juego y no están completamente validados para la campaña.

Da permiso de ejecución al AppImage y ejecútalo; sin FUSE, añade `--appimage-extract-and-run`. Para el archivo portátil, extráelo y ejecuta `re4mepc/AppRun`. Ambos abren el lanzador sin argumentos y aceptan los mismos comandos que `re4mepc`. Compílalos con `make setup` y `make package` usando Docker. Consulta las [instrucciones de compilación portátil](docs/advanced-usage.md#portable-builds) y los [requisitos de distribución](docs/desktop-release.md) (en inglés).

### Archivos del juego

El importador restaura los recursos del APK y verifica las dos bibliotecas ARM y todos los recursos de fases necesarios antes de instalar. No sobrescribe destinos existentes, aunque estén vacíos. Un APK reempaquetado puede funcionar si conserva las mismas bibliotecas y los recursos completos.

| Biblioteca compatible | SHA-256 |
| --- | --- |
| `libbio4af.so` | `6f6e52ef26b096cda44fc08c3f541cdc3bf1056a88f13fc1c3e17201589a0423` |
| `libmc_eruption_for_android_jni.so` | `25109c3b799045312073243b644f6053726689d7baf05bcf09b7acd786cff4f6` |

La importación, comprobación y ejecución exigen estos hashes. Usa `re4mepc import "/ruta/al/juego.apk" --output /external/re4/game` para elegir otra ubicación y pasa `--game /external/re4/game` al comprobar o ejecutar. Consulta la [validación del motor y migración](docs/advanced-usage.md#data-locations-and-supported-engine) (en inglés).

### Lanzador

![Lanzador con aspecto de expediente, fotografía de la aldea y controles de instalación](docs/launcher-preview.png)

Ábrelo con `re4mepc`, `make play` o `make launcher`.

- **Import APK / Browse:** importa a una carpeta nueva o selecciona una instalación existente.
- **Play / Stop:** inicia el juego o detén la operación activa.
- **Settings & controls:** configura pantalla, teclado, ratón, mando y mira láser; los cambios se aplican al siguiente inicio.
- **Save backups:** crea, importa, exporta, restaura o elimina copias con el juego detenido.
- **Diagnostics / View logs:** recoge mediciones o consulta los registros opcionales.

El lanzador admite ratón y teclado y se adapta hasta 640×520. Consulta el [comportamiento del lanzador](docs/advanced-usage.md#graphical-launcher), las [ventanas de ajustes y copias](docs/dialogs.md) y la [procedencia del arte](docs/launcher-assets.md) (en inglés).

#### Idiomas

**Idioma del juego** e **Idioma del lanzador** ofrecen por separado **inglés, español, francés, alemán, italiano y japonés**. El lanzador cambia al instante, incluidas las ventanas abiertas; el juego cambia en el siguiente inicio. **Usar idioma guardado del juego** conserva la selección del motor. Ambas preferencias se guardan en `settings.json`.

Para una sola sesión, usa `re4mepc run --language es` o `--language saved`. Los códigos admitidos son `en`, `es`, `fr`, `de`, `it`, `ja` y `saved`. Los paquetes actuales incluyen IPAGothic y su licencia; los anteriores requieren actualizarse o recompilarse. Consulta los [detalles de idiomas](docs/advanced-usage.md#languages) (en inglés).

#### Logros

**Achievements** muestra 21 objetivos locales: progreso de misiones y rangos, compras y mejoras de armas, y un Platino al obtener los otros 20. Las partidas existentes recuperan el progreso de misiones y rangos tras jugar; las compras y mejoras cuentan cuando las observa el lanzador.

**Settings & controls → Achievements** activa capturas o clips silenciosos al desbloquear logros. La galería exporta las capturas seleccionadas o todas con sus metadatos y evita duplicar archivos compartidos. Los registros de logros forman parte de las copias de partidas; sus archivos multimedia requieren **Include achievement media** al exportar. Consulta la [cobertura de logros](docs/achievements.md) y las [capturas portátiles](docs/portable-captures.md) (en inglés).

#### Integración con el escritorio

`make desktop` instala o actualiza la entrada del menú de aplicaciones. Añade `DESKTOP_ARGS="--desktop"` para un acceso directo de escritorio; `--apk '/ruta/al/juego.apk'` o `--icon '/ruta/al/icono.png'` eligen un icono local. Por defecto se conserva el icono instalado. `make uninstall` elimina el CLI y los accesos, conservando el juego y las partidas. Consulta los [detalles de instalación en el escritorio](docs/advanced-usage.md#linux-app-and-desktop-shortcut) (en inglés).

### Controles

| Entrada | Acción |
| --- | --- |
| W / S | Avanzar / retroceder |
| A / D | Girar a izquierda / derecha (movimiento clásico tipo tanque) |
| Flechas | Mismas direcciones; navegar por menús |
| Mover el ratón | Mirar y apuntar |
| Mantener botón derecho / X | Apuntar |
| Botón izquierdo / Z | Disparar |
| R | Recargar |
| Mantener F y pulsar botón izquierdo / Z | Preparar el cuchillo y atacar |
| E / Enter / Espacio | Acción contextual; Enter / Espacio avanzan el texto |
| Escape | Abrir estado; cancelar submenú de inventario o volver al juego |
| Tab | Liberar / capturar el cursor |
| F3 | Mostrar / ocultar diagnósticos |
| Alt+Enter | Alternar la pantalla completa sin bordes |
| F12 | Cerrar la ventana del juego |

Para recoger un objeto del suelo, pulsa Espacio para seleccionarlo y otra vez para tomarlo. El modo PC oculta los controles táctiles principales y captura el cursor durante el juego; Tab lo libera y un clic en la escena lo recupera sin disparar. Las acciones contextuales, órdenes al acompañante, controles de mira, estado y menús siguen visibles. Perder el foco libera las entradas mantenidas. Enter, Espacio, Escape o un clic omiten un vídeo.

En menús, WASD/cruceta o el stick derecho mueve el cursor, Espacio/A selecciona, Enter/B continúa o confirma el deslizador de dificultad reconocido, y Escape/Start cancela o vuelve. También funciona la navegación normal con ratón.

Los mandos usan el stick izquierdo para moverse/girar, el derecho para mirar, gatillos para apuntar/disparar, A para acción, X para recargar, Y para cuchillo y Start para estado. El comportamiento con mandos físicos sigue sin verificarse. Reasigna entradas y sensibilidades en **Settings & controls**; Tab, F3 y F12 están reservados. Usa `re4mepc run --controls touch` para los controles táctiles originales. Consulta los [controles completos](docs/advanced-usage.md#controls) y el [comportamiento de menús](docs/menu-controls.md) (en inglés).

### Partidas y ajustes

| Contenido | Ubicación predeterminada |
| --- | --- |
| Juego importado | `~/.local/share/re4mepc/game` |
| Partidas | `~/.local/share/re4mepc/game/saves` |
| Capturas y clips de logros | `~/.local/share/re4mepc/game/achievement-media` |
| Ajustes | `~/.config/re4mepc/settings.json` |
| Copias de partidas | `~/.local/state/re4mepc/backups/<installation-path-hash>` |
| Caché de audio | `~/.local/share/re4mepc/game/cache/audio` |
| Caché experimental de texturas | `~/.cache/re4mepc/textures` |
| Diagnósticos y archivos de pruebas | `~/.local/state/re4mepc/logs` |

Las rutas absolutas de `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME` y `XDG_CACHE_HOME` sustituyen los directorios base; los valores vacíos o relativos usan los predeterminados. Reemplazar los archivos de la aplicación portátil conserva los datos externos.

El host crea copias antes de iniciar y alrededor de los guardados nativos, conservando diez conjuntos distintos. Con el juego detenido:

```sh
re4mepc backup
re4mepc backups
re4mepc export-backup SNAPSHOT_ID "/ruta/a/copia.zip"
re4mepc import-backup "/ruta/a/copia.zip"
re4mepc restore-backup SNAPSHOT_ID
```

Usa un ID mostrado por `backups`. Importar crea una copia inactiva; restaurar la activa tras verificarla y conserva una copia de recuperación. Añade `--include-media` al exportar para incluir las capturas de logros referenciadas. Consulta las [operaciones de copias](docs/advanced-usage.md#save-backups) y el [almacenamiento y recuperación](docs/desktop-release.md) (en inglés).

### Estado y limitaciones

La plataforma objetivo es Linux x86_64. El host necesita memoria compartida por debajo de 4 GiB y funciones de compatibilidad de OpenGL. Redimensionado, HiDPI, mandos y pantalla completa sin bordes están implementados, pero faltan las comprobaciones físicas de mando, pantalla/HiDPI y altavoces.

Las pruebas visibles han ejercitado el título, los menús en inglés, audio/vídeo originales y juego en la aldea. La lógica y presentación funcionan a **20 Hz** para conservar el reloj de misiones; aumentar la frecuencia también acelera la lógica. La ejecución ARM y los puentes de Python añaden sobrecarga, especialmente al cargar. No se ha establecido una frecuencia de renderizado superior segura.

**La campaña completa no está verificada.** La prueba anterior de dos horas se detuvo en su punto conservado de 2.880,043 segundos y sigue incompleta. Una excepción nativa intermitente al inicializar la dificultad continúa sin resolverse; ninguna optimización de carga cumplió el criterio de rendimiento.

Los paquetes experimentales tienen comprobaciones documentadas de inicio/actualización en Ubuntu 22.04, Ubuntu 24.04 y Arch, de idiomas y repeticiones de primera misión/inventario/guardado en AMD RX 6700S. Estas pruebas no demuestran soporte de toda la campaña; no hubo hardware Intel/NVIDIA disponible. Consulta [VALIDATION.md](VALIDATION.md), el [resumen de validación](docs/qualification-summary.md), la [cobertura de campaña](docs/campaign-coverage.md) y las [mediciones de la hoja de ruta](docs/roadmap-results.md) (en inglés).

### Desarrollo

Las contribuciones se revisan en los issues y pull requests de este repositorio. Lee la [guía de contribución](CONTRIBUTING.md#español) y la [política de piratería](CODE_OF_CONDUCT.md#español); ambos documentos contienen inglés y español.

| Comando | Función |
| --- | --- |
| `make help` | Mostrar los objetivos disponibles |
| `make setup` / `make build` | Preparar dependencias / compilar helpers nativos |
| `make run` / `make dev` | Ejecutar con registros en la terminal |
| `make check` | Compilar helpers y ejecutar pruebas sintéticas sin APK |
| `make verify` | Ejecutar pruebas y auditar código, índice e historial |
| `make check-game` | Verificar los datos importados |
| `make visible-test` | Probar inicio, vídeo, menús, renderizado, audio y guardado/carga |
| `make controls-test` | Probar controles y cámara durante el juego |
| `make package` | Compilar AppImage y archivo portátil |
| `make clean` / `make distclean` | Eliminar helpers/cachés / eliminar también `.venv` |

Las pruebas del motor real abren ventanas y usan copias aisladas del juego. La limpieza conserva datos, partidas y registros. `make audit-source` comprueba el índice, historial y blobs contra una lista explícita de archivos permitidos; las nuevas rutas de documentación también requieren revisión allí.

Consulta la [guía detallada de uso, arquitectura y pruebas](docs/advanced-usage.md), los [diagnósticos](docs/diagnostics.md), la [auditoría de renderizado](docs/render-audit.md) y el [flujo de ingeniería inversa](docs/rea-workflow.md) (en inglés).

### Licencia y créditos

El código original del host tiene licencia [MIT](LICENSE). Esto excluye datos originales del juego, marcas y dependencias de terceros. Resident Evil pertenece a sus respectivos titulares. El repositorio distribuye el host y documentación, no el juego.
