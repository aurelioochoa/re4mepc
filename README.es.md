# Resident Evil 4 Mobile PC Port

[English](README.md) · **Español**

![Resident Evil 4 Mobile: Tux como Leon y Ashley en una aldea con niebla](docs/readme-banner.png)

Ejecuta el motor original de **Resident Evil 4 Mobile para Android** en una ventana de Linux con teclado, ratón y mando. `re4mepc` es un host experimental de compatibilidad: Unicorn ejecuta las bibliotecas ARM32, SDL2 gestiona la ventana y el audio, y un puente traduce OpenGL ES 1 a OpenGL de escritorio. No necesitas instalar Android.

**Debes aportar tu propio juego:** proporciona un APK compatible. El proyecto no incluye ni descarga el juego. Las bibliotecas importadas, recursos y partidas se guardan fuera del repositorio. La campaña completa no está validada.

[Jugabilidad](#jugabilidad) · [Inicio rápido](#inicio-rápido) · [Archivos del juego](#archivos-del-juego) · [Controles](#controles) · [Desarrollo](#desarrollo)

## Jugabilidad

![Cuatro capturas en Linux: exploración de la aldea, apuntado con pistola, juego en la aldea y postura con cuchillo](docs/gameplay-mosaic.png)

Capturas reales del escritorio Linux; cada imagen conserva la resolución original de **800×480**. En sentido horario desde arriba a la izquierda: exploración, apuntado con pistola, juego en la aldea y postura con cuchillo. Arte del juego © Capcom. El banner es arte generado; consulta las [referencias y prompts](docs/banner-artwork.md) (en inglés).

## Requisitos

- **Linux x86_64** con escritorio gráfico, dispositivo de audio y **perfil de compatibilidad de OpenGL de escritorio**.
- **Python 3.10 o posterior**, `venv`, Tk, GNU Make, compilador de C, `pkg-config` y cabeceras de desarrollo de SDL2 para instalar desde el código fuente.
- **FFmpeg** para audio y vídeos originales. El japonés requiere fuentes adecuadas.

En **Arch Linux**, instala `python tk make gcc pkgconf sdl2-compat ffmpeg mesa noto-fonts-cjk`. En **Debian/Ubuntu**, instala `python3-venv python3-tk build-essential pkg-config libsdl2-dev libgl1-mesa-dev ffmpeg fonts-ipafont-gothic`.

Las versiones portátiles incluyen las dependencias de la aplicación y fuentes japonesas; siguen necesitando los controladores gráficos y bibliotecas del sistema. Windows, macOS y Linux ARM64 quedan fuera de esta versión.

## Inicio rápido

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

### Versiones portátiles

La [preversión experimental](https://github.com/aurelioochoa/re4mepc/releases/tag/v0.1.0-experimental.20261014) ofrece un AppImage, un archivo portátil y `SHA256SUMS`. Comprueba la descarga elegida con los hashes del [resumen de validación](docs/qualification-summary.md) (en inglés). Los paquetes no incluyen el juego y no están completamente validados para la campaña.

Da permiso de ejecución al AppImage y ejecútalo; sin FUSE, añade `--appimage-extract-and-run`. Para el archivo portátil, extráelo y ejecuta `re4mepc/AppRun`. Ambos abren el lanzador sin argumentos y aceptan los mismos comandos que `re4mepc`. Compílalos con `make setup` y `make package` usando Docker. Consulta las [instrucciones de compilación portátil](docs/advanced-usage.md#portable-builds) y los [requisitos de distribución](docs/desktop-release.md) (en inglés).

## Archivos del juego

El importador restaura los recursos del APK y verifica las dos bibliotecas ARM y todos los recursos de fases necesarios antes de instalar. No sobrescribe destinos existentes, aunque estén vacíos. Un APK reempaquetado puede funcionar si conserva las mismas bibliotecas y los recursos completos.

| Biblioteca compatible | SHA-256 |
| --- | --- |
| `libbio4af.so` | `6f6e52ef26b096cda44fc08c3f541cdc3bf1056a88f13fc1c3e17201589a0423` |
| `libmc_eruption_for_android_jni.so` | `25109c3b799045312073243b644f6053726689d7baf05bcf09b7acd786cff4f6` |

La importación, comprobación y ejecución exigen estos hashes. Usa `re4mepc import "/ruta/al/juego.apk" --output /external/re4/game` para elegir otra ubicación y pasa `--game /external/re4/game` al comprobar o ejecutar. Consulta la [validación del motor y migración](docs/advanced-usage.md#data-locations-and-supported-engine) (en inglés).

## Lanzador

![Lanzador con aspecto de expediente, fotografía de la aldea y controles de instalación](docs/launcher-preview.png)

Ábrelo con `re4mepc`, `make play` o `make launcher`.

- **Import APK / Browse:** importa a una carpeta nueva o selecciona una instalación existente.
- **Play / Stop:** inicia el juego o detén la operación activa.
- **Settings & controls:** configura pantalla, teclado, ratón, mando y mira láser; los cambios se aplican al siguiente inicio.
- **Save backups:** crea, importa, exporta, restaura o elimina copias con el juego detenido.
- **Diagnostics / View logs:** recoge mediciones o consulta los registros opcionales.

El lanzador admite ratón y teclado y se adapta hasta 640×520. Consulta el [comportamiento del lanzador](docs/advanced-usage.md#graphical-launcher), las [ventanas de ajustes y copias](docs/dialogs.md) y la [procedencia del arte](docs/launcher-assets.md) (en inglés).

### Idiomas

**Idioma del juego** e **Idioma del lanzador** ofrecen por separado **inglés, español, francés, alemán, italiano y japonés**. El lanzador cambia al instante, incluidas las ventanas abiertas; el juego cambia en el siguiente inicio. **Usar idioma guardado del juego** conserva la selección del motor. Ambas preferencias se guardan en `settings.json`.

Para una sola sesión, usa `re4mepc run --language es` o `--language saved`. Los códigos admitidos son `en`, `es`, `fr`, `de`, `it`, `ja` y `saved`. Los paquetes actuales incluyen IPAGothic y su licencia; los anteriores requieren actualizarse o recompilarse. Consulta los [detalles de idiomas](docs/advanced-usage.md#languages) (en inglés).

### Logros

**Achievements** muestra 21 objetivos locales: progreso de misiones y rangos, compras y mejoras de armas, y un Platino al obtener los otros 20. Las partidas existentes recuperan el progreso de misiones y rangos tras jugar; las compras y mejoras cuentan cuando las observa el lanzador.

**Settings & controls → Achievements** activa capturas o clips silenciosos al desbloquear logros. La galería exporta las capturas seleccionadas o todas con sus metadatos y evita duplicar archivos compartidos. Los registros de logros forman parte de las copias de partidas; sus archivos multimedia requieren **Include achievement media** al exportar. Consulta la [cobertura de logros](docs/achievements.md) y las [capturas portátiles](docs/portable-captures.md) (en inglés).

### Integración con el escritorio

`make desktop` instala o actualiza la entrada del menú de aplicaciones. Añade `DESKTOP_ARGS="--desktop"` para un acceso directo de escritorio; `--apk '/ruta/al/juego.apk'` o `--icon '/ruta/al/icono.png'` eligen un icono local. Por defecto se conserva el icono instalado. `make uninstall` elimina el CLI y los accesos, conservando el juego y las partidas. Consulta los [detalles de instalación en el escritorio](docs/advanced-usage.md#linux-app-and-desktop-shortcut) (en inglés).

## Controles

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

## Partidas y ajustes

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

## Estado y limitaciones

La plataforma objetivo es Linux x86_64. El host necesita memoria compartida por debajo de 4 GiB y funciones de compatibilidad de OpenGL. Redimensionado, HiDPI, mandos y pantalla completa sin bordes están implementados, pero faltan las comprobaciones físicas de mando, pantalla/HiDPI y altavoces.

Las pruebas visibles han ejercitado el título, los menús en inglés, audio/vídeo originales y juego en la aldea. La lógica y presentación funcionan a **20 Hz** para conservar el reloj de misiones; aumentar la frecuencia también acelera la lógica. La ejecución ARM y los puentes de Python añaden sobrecarga, especialmente al cargar. No se ha establecido una frecuencia de renderizado superior segura.

**La campaña completa no está verificada.** La prueba anterior de dos horas se detuvo en su punto conservado de 2.880,043 segundos y sigue incompleta. Una excepción nativa intermitente al inicializar la dificultad continúa sin resolverse; ninguna optimización de carga cumplió el criterio de rendimiento.

Los paquetes experimentales tienen comprobaciones documentadas de inicio/actualización en Ubuntu 22.04, Ubuntu 24.04 y Arch, de idiomas y repeticiones de primera misión/inventario/guardado en AMD RX 6700S. Estas pruebas no demuestran soporte de toda la campaña; no hubo hardware Intel/NVIDIA disponible. Consulta [VALIDATION.md](VALIDATION.md), el [resumen de validación](docs/qualification-summary.md), la [cobertura de campaña](docs/campaign-coverage.md) y las [mediciones de la hoja de ruta](docs/roadmap-results.md) (en inglés).

## Desarrollo

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

## Licencia y créditos

El código original del host tiene licencia [MIT](LICENSE). Esto excluye datos originales del juego, marcas y dependencias de terceros. Resident Evil pertenece a sus respectivos titulares. El repositorio distribuye el host y documentación, no el juego.
