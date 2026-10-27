# Contributing to re4mepc / Contribuir a re4mepc

[English](#english) · [Español](#español)

## English

`re4mepc` is an experimental Linux compatibility host for Resident Evil 4 Mobile for Android. Unicorn executes the original ARM32 libraries while the host provides desktop graphics, audio, input and storage. Reports and changes are reviewed through this repository's [issues](https://github.com/aurelioochoa/re4mepc/issues) and [pull requests](https://github.com/aurelioochoa/re4mepc/pulls).

### Scope

The current target is **Linux x86_64** with the ARM libraries and resources accepted by the importer. Runtime, importer, controls, launcher, rendering, audio, saves, packaging, documentation and test improvements are useful. General Android compatibility is outside the current scope.

Read the [README](README.md), [detailed usage and architecture](docs/advanced-usage.md), [validation summary](docs/qualification-summary.md) and [campaign coverage](docs/campaign-coverage.md). Full campaign completion remains unverified. Physical controller, HiDPI and audible speaker qualification is incomplete; distinguish implemented behavior from observed results.

### Reports and proposals

Open an [issue](https://github.com/aurelioochoa/re4mepc/issues/new) in English or Spanish and include:

- Your revision (`git rev-parse HEAD`) or package version, Linux distribution, architecture and Python version for source installations.
- GPU/driver, desktop session and input devices when relevant.
- Reproduction steps, expected and observed results, and whether an earlier revision worked.
- Import/check results, selected game language and relevant logs. Remove private details; do not attach APKs, extracted libraries, game resources or save backups containing game material.

For larger proposals, explain the problem and intended design. Distinguish synthetic tests from real gameplay checks and identify the missions or scenarios exercised. A successful build or menu launch does not establish full campaign support.

### Development setup

Fork the repository, clone your fork and create a branch from `main`. Install the system packages listed in the [README requirements](README.md#requirements), then:

```sh
make setup
make check
```

The source setup requires Python 3.10+, venv, Tk, Make, a C compiler, Rust (cargo), pkg-config, SDL2 development headers and FFmpeg. `make setup` creates `.venv`, installs Python dependencies and builds native helpers. Synthetic tests require no APK. Real-game checks need your own compatible APK and a graphical desktop with an OpenGL compatibility profile.

### Changes and verification

Keep each pull request focused on one problem, follow existing Python/C style and add tests when they catch a meaningful regression. Preserve imported originals, settings and saves. Use synthetic fixtures and isolated game copies for tests; keep game data outside the repository.

| Command | Purpose |
| --- | --- |
| `make check` | Build native helpers and run synthetic component regressions |
| `make audit-source` | Audit the working tree, Git index, history and stored blobs |
| `make verify` | Run component checks and the complete source audit |
| `make check-game` | Verify your imported game installation |
| `make visible-test` | Check startup, video, menus, rendering, audio and save/load |
| `make controls-test` | Exercise PC gameplay controls and camera behavior |
| `make package` | Build AppImage and portable archive using Docker |

Run `make verify` for code, importer or build changes, with the relevant real-game checks when available. Packaging changes also need the checks described in [desktop release documentation](docs/desktop-release.md). For documentation, check links, examples and formatting and run `make audit-source`; rebuilding the runtime is unnecessary. State what you checked and identify checks you could not run.

The audit uses an explicit path allowlist in `tools/audit_source.py`. Review and register new source or documentation paths there; do not broadly relax the audit or bypass binary provenance checks. See the [reverse-engineering workflow](docs/rea-workflow.md) and [diagnostics](docs/diagnostics.md).

### Pull requests

Target **`aurelioochoa/re4mepc:main`**. Describe the problem, resulting behavior, verification and remaining limitations or regressions. Include screenshots when they help review visual changes. Report performance measurements with their scenario and environment; preserve the game's timing when changing scheduling or rendering.

### AI assistance

AI-assisted contributions are allowed. Contributors remain responsible for understanding and reviewing the content, verifying its behavior, and checking its provenance and license compatibility. Describe substantial AI assistance in the pull request.

### Provenance and licensing

Contribute only material you have the right to share. Prefer public documentation, reproducible observations and original work. Do not include copied proprietary code, leaked material, APKs, extracted ARM libraries, game assets or disassembly dumps. Follow the [piracy policy](CODE_OF_CONDUCT.md#english).

Original host source is covered by [MIT](LICENSE). Preserve copyright and license notices and dependency attribution. Imported game binaries, assets and trademarks are excluded; third-party dependencies retain their own licenses. Documentation media must follow the recorded provenance and source audit rules.

## Español

`re4mepc` es un host experimental de compatibilidad para ejecutar Resident Evil 4 Mobile de Android en Linux. Unicorn ejecuta las bibliotecas ARM32 originales y el host proporciona gráficos, audio, entrada y almacenamiento de escritorio. Los informes y cambios se revisan en los [issues](https://github.com/aurelioochoa/re4mepc/issues) y [pull requests](https://github.com/aurelioochoa/re4mepc/pulls) de este repositorio.

### Alcance

El objetivo actual es **Linux x86_64** con las bibliotecas ARM y los recursos aceptados por el importador. Son útiles las mejoras del runtime, importador, controles, lanzador, renderizado, audio, partidas, empaquetado, documentación y pruebas. La compatibilidad general con Android queda fuera del alcance actual.

Consulta el [README](README.md#español), el [uso detallado y arquitectura](docs/advanced-usage.md), el [resumen de validación](docs/qualification-summary.md) y la [cobertura de campaña](docs/campaign-coverage.md). Las tres últimas referencias están en inglés. La campaña completa sigue sin verificarse. Faltan comprobaciones físicas de mando, HiDPI y altavoces; distingue las funciones implementadas de los resultados observados.

### Informes y propuestas

Abre un [issue](https://github.com/aurelioochoa/re4mepc/issues/new) en inglés o español e incluye:

- Tu revisión (`git rev-parse HEAD`) o versión del paquete, distribución Linux, arquitectura y versión de Python para instalaciones desde código fuente.
- GPU/controlador, sesión gráfica y dispositivos de entrada cuando corresponda.
- Pasos para reproducirlo, resultado esperado y observado, y si funcionaba en una revisión anterior.
- Resultados de importación/verificación, idioma seleccionado y registros pertinentes. Elimina datos privados; no adjuntes APK, bibliotecas extraídas, recursos del juego ni copias de partidas que contengan material del juego.

Para propuestas amplias, explica el problema y el diseño previsto. Distingue las pruebas sintéticas de las comprobaciones reales e identifica las misiones o situaciones probadas. Compilar o llegar al menú no demuestra compatibilidad con toda la campaña.

### Preparar el entorno

Crea un fork, clónalo y abre una rama a partir de `main`. Instala los paquetes del sistema indicados en los [requisitos del README](README.md#requisitos) y ejecuta:

```sh
make setup
make check
```

La preparación desde código requiere Python 3.10 o posterior, venv, Tk, Make, compilador de C, Rust (cargo), pkg-config, cabeceras de desarrollo de SDL2 y FFmpeg. `make setup` crea `.venv`, instala las dependencias de Python y compila los helpers nativos. Las pruebas sintéticas no necesitan APK. Las pruebas reales requieren tu propio APK compatible y un escritorio gráfico con perfil de compatibilidad de OpenGL.

### Cambios y pruebas

Mantén cada pull request centrado en un problema, respeta el estilo Python/C existente y añade pruebas cuando detecten una regresión significativa. Conserva originales importados, ajustes y partidas. Usa datos sintéticos y copias aisladas del juego; guarda los datos del juego fuera del repositorio.

| Comando | Función |
| --- | --- |
| `make check` | Compilar helpers nativos y ejecutar regresiones sintéticas de componentes |
| `make audit-source` | Auditar archivos de trabajo, índice de Git, historial y blobs almacenados |
| `make verify` | Ejecutar pruebas de componentes y la auditoría completa de código |
| `make check-game` | Verificar tu instalación importada |
| `make visible-test` | Probar inicio, vídeo, menús, renderizado, audio y guardado/carga |
| `make controls-test` | Probar controles de PC y cámara durante el juego |
| `make package` | Compilar AppImage y archivo portátil mediante Docker |

Ejecuta `make verify` para cambios del código, importador o compilación, con las comprobaciones reales pertinentes cuando estén disponibles. Los cambios de empaquetado también necesitan las pruebas de la [documentación de distribución](docs/desktop-release.md). Para documentación, comprueba enlaces, ejemplos y formato y ejecuta `make audit-source`; no hace falta recompilar el runtime. Indica qué comprobaste y qué pruebas no pudiste ejecutar.

La auditoría usa una lista explícita de rutas permitidas en `tools/audit_source.py`. Revisa y registra allí las nuevas rutas de código o documentación; no relajes la auditoría de forma general ni omitas las comprobaciones de procedencia de binarios. Consulta el [flujo de ingeniería inversa](docs/rea-workflow.md) y los [diagnósticos](docs/diagnostics.md) (en inglés).

### Pull requests

Envía el pull request a **`aurelioochoa/re4mepc:main`**. Describe el problema, el comportamiento resultante, las pruebas y cualquier límite o regresión pendiente. Incluye capturas si ayudan a revisar cambios visuales. Acompaña las mediciones de rendimiento con la situación y el entorno utilizados; conserva los tiempos del juego al cambiar la planificación o el renderizado.

### Uso de IA

Se permiten contribuciones asistidas por IA. Quien contribuye sigue siendo responsable de comprender y revisar el contenido, comprobar su funcionamiento y verificar su procedencia y compatibilidad de licencia. Describe en el pull request el uso sustancial de IA.

### Procedencia y licencias

Aporta únicamente material que puedas compartir. Prioriza documentación pública, observaciones reproducibles y trabajo original. No incluyas código propietario copiado, material filtrado, APK, bibliotecas ARM extraídas, recursos del juego ni volcados de desensamblado. Cumple la [política de piratería](CODE_OF_CONDUCT.md#español).

El código original del host está cubierto por [MIT](LICENSE). Conserva los avisos de derechos de autor, licencias y atribución de dependencias. Se excluyen los binarios importados, recursos y marcas del juego; las dependencias mantienen sus propias licencias. El material visual de documentación debe respetar la procedencia registrada y las reglas de auditoría.
