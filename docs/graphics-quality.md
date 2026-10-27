# Graphics quality

The engine always renders to an 800×480 logical surface. These host options
change how that surface is drawn and shown, never the game data: textures,
models and movies are the originals. Every option defaults to the previous
behavior. Choose them in the launcher under **Settings & controls → Graphics**,
save them with `re4mepc settings --set render_scale 2` (string values are JSON, such as
`'"16:9"'`), or override one session:

```sh
make run ARGS="--render-scale 2 --msaa 4 --texture-filtering anisotropic --display-filter sharpen"
```

| Setting | CLI flag | Values (default first) | Effect |
|---|---|---|---|
| `render_scale` | `--render-scale` | 1, 2, 3, 4 | Internal resolution multiple: 2 renders 1600×960 |
| `msaa` | `--msaa` | 0, 2, 4, 8 | Multisampled edges, clamped to the driver maximum |
| `texture_filtering` | `--texture-filtering` | original, trilinear, anisotropic | Generated mipmaps with trilinear, optionally 16× anisotropic filtering |
| `display_filter` | `--display-filter` | bilinear, sharpen, fxaa, pixel, crt | Final scaling to the window |
| `aspect_ratio` | `--aspect-ratio` | original, 16:9, 21:9 | Widens 3D views; HUD and menus stay 5:3 |

Changes apply on the next launch. Combine them freely, including with
[interpolated presentation rates](fps-performance.md).

## How it works

`native/display.c` maps the engine's GL state in the engine context. The
native import bridge and the Python GL path both call it, so they cannot
diverge. Viewports and scissor boxes are multiplied by the render scale. The
host framebuffer is multisampled when MSAA is enabled and resolved before
presentation, screenshots, achievement captures and interpolation snapshots.
Movies, the menu focus outline and the F3 overlay are drawn in logical
coordinates at the same scale.

Trilinear modes replace the engine's per-texture filters, which are mostly
`GL_NEAREST` without mipmaps. Every level-0 upload, including converted OES
paletted textures, then regenerates a complete mipmap chain from the original
image. `original` passes the engine's filters through unchanged.

Display filters run as a GLSL pass from the resolved surface to the window:

- **bilinear**: the previous framebuffer blit.
- **sharpen**: contrast-adaptive sharpening (CAS-style); flat areas are unchanged.
- **fxaa**: FXAA edge smoothing, useful when MSAA is off or too expensive.
- **pixel**: sharp bilinear; integer nearest scaling, blending only at texel edges.
- **crt**: scanlines on the original 480 rows with a soft aperture-grille mask.

### Widescreen

The engine has no widescreen layout. Given a 16:9 surface it pillarboxes the
same 5:3 image, so the host keeps the engine at 800×480 and widens only
perspective projections. Traces of title-to-village gameplay found projections
loaded only with `glLoadMatrixf`: one perspective form for 3D and orthographic
forms for HUD and menus. For a perspective load, `P[0]` is scaled by
`800/surface_width` and the viewport extends into equal margins (854 wide for
16:9, 1120 for 21:9). Orthographic layers keep the centered 5:3 area, so HUD,
menus and touch targets do not move. Untextured full-screen orthographic quads
(fades and story or loading covers) also span the margins. Textured full-screen
art stays pillarboxed instead of stretching. Pointer input in the margins
reaches no native control.

Known limitation: the engine still culls objects against its original 5:3
view, so objects can appear late at the screen edges. Achievement captures crop
to the 5:3 engine area to keep clip sizes consistent; `--screenshot` saves the
full widescreen frame.

### Framebuffer reads

Runtime traces from title to village gameplay observed no `glReadPixels` or
`glCopyTexImage2D` calls, and only full-screen viewport and scissor boxes. If
the engine reads the framebuffer anyway, the host maps the rectangle,
resolves MSAA and downsamples into a logical-size buffer, so the guest still
receives `w×h` pixels. The first such read is logged.

## Measurements — 2026-10-27

Isolated village fixture on the reference system (Ryzen 9 6900HS, RX 6700S,
Mesa radeonsi). 200 gameplay ticks at 60 FPS presentation:

| Settings | Surface | Median tick work | Presentation FPS | Mean render + swap (CPU) |
|---|---|---:|---:|---:|
| Defaults | 800×480 | 28.4 ms | 60.0 | 0.54 ms |
| 2×, MSAA 4×, anisotropic | 1600×960 | 26.2 ms | 60.0 | 0.58 ms |
| 4×, MSAA 8×, anisotropic, FXAA, 16:9 | 3416×1920 | 26.5 ms | 59.8 | 0.65 ms |

Tick work differences are within run-to-run noise: scaling adds GPU work, not
emulation work. GPU time is not measured separately; slower GPUs should lower
the render scale or MSAA first. Interpolation counters were identical to
defaults (182 of 218 frames interpolated in the shorter comparison run).

Game-free checks in `tests/test_display.py` cover setting validation, launcher
labels, rectangle and projection mapping, scaled MSAA rendering through the
engine's GL imports, widescreen margins and covers, mipmap completeness and
every display filter. Run them with `make check`.
