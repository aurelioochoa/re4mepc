# Native analysis workflow

REA is a development tool only. Neither game launch nor either distribution
format requires Node, Java, Ghidra or REA. Analysis output and supported game
libraries belong outside the source checkout.

The initial toolchain uses REA 6.4.0, Ghidra 12.1.4 and a full x86_64 JDK 21.
These match the [REA provider baseline](https://github.com/morluto/rea/blob/main/docs/installation.md#ghidra).
The local run used Temurin 21.0.12.1+1 and Node 22.23.1. Package downloads were
hashed before extraction; REA was installed under `/tmp/re4-roadmap/toolchain`
without running `rea setup` or changing agent configuration.

| Download | SHA-256 |
|---|---|
| rea-agents-6.4.0.tgz | 59eb1604b8db75f522d4a975c36ce6b4a2ad465e43bad165f9a8f728391db9b8 |
| ghidra_12.1.4_PUBLIC_20260921.zip | ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db |
| OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz | ce79869e1307ed8ee1e2baa86a412b1eb5b75d10a01006d788a6f968bcfaee94 |

The Ghidra digest was compared with its GitHub release asset digest. The JDK
digest was compared with Adoptium release metadata. REA's npm lock records the
registry integrity value; the table additionally identifies the downloaded
package bytes. Paths and release metadata are local evidence, not shipped game
resources.

With the extracted installations available, run:

```bash
.venv/bin/python tools/rea_workflow.py \
  --rea /external/toolchain/rea/node_modules/.bin/rea \
  --ghidra /external/toolchain/ghidra_12.1.4_PUBLIC \
  --java-home /external/toolchain/jdk-21 \
  --output /external/analysis/rea \
  --package-artifact /external/toolchain/rea-agents-6.4.0.tgz
```

The verifier checks provider readiness, exact tool versions and supported engine
hashes. It compares three named functions per library with ELF/Capstone entries,
instruction boundaries and mnemonics, including ARM and Thumb examples. It saves
raw instructions, dossiers, pseudocode, provider errors and snapshots externally.
A provider error or mapping disagreement leaves `gate_passed` false and returns
an unsuccessful process status. The source tests exercise known good evidence
and independently corrupt identity, addresses, boundaries and decoding.

ELF function values retain the Thumb selector in bit zero. Capstone and Ghidra
instruction addresses in Capstone use `ELF_value & ~1`. Ghidra rebases these shared libraries by `0x10000` with its default ELF loader. The verifier reads `inspect-native-load-image` and checks the source file offset and backing digest at each rebased entry before comparing instructions. Runtime addresses add the host shared
memory base and a module offset: zero for the eruption library and `0x200000`
for `libbio4af.so`. Runtime `ArmRuntime.call` uses the original symbol value,
including its ISA selector. File offsets use the containing ELF section's offset
plus the instruction address minus the section virtual address.

For focused investigations, use the [REA CLI](https://github.com/morluto/rea/blob/main/docs/cli.md):

```bash
rea function /external/game/lib/libbio4af.so SYMBOL --provider ghidra --json
rea decompile /external/game/lib/libbio4af.so ADDRESS --provider ghidra --json
rea xrefs /external/game/lib/libbio4af.so ADDRESS --provider ghidra --json
```

Snapshots cache exact queries and are not a persistent provider database. A new
query may re-import/analyze the library. Static references and pseudocode explain
runtime observations; they do not measure execution time. Preserve provider
limitations when interpreting incomplete call graphs or decompilation.

## Aiming and firing investigation

The 2026-10-14 investigation used the same REA/Ghidra toolchain to inspect
`GM_CtrlSub_LaserSite::Draw`, `GM_CtrlMain_Player::_State_AtkAimM` and
`GM_CtrlMain_Player::_Set_AimMainRot` in the supported engine. REA evidence,
supporting Capstone disassembly and private runtime captures are stored under
`/tmp/re4-combat/`; they are not distribution assets.

The laser draw uses a separate visibility flag. The native difficulty table
suppresses it on Extreme (index 4), which was also the selected difficulty in
a private copy of the reported save. Both PC and touch mode keep that native
suppression; `Get_Diff_LaserSiteNonDrawFlg` is not overridden. Custom sights
only reskin the native draw, so they are hidden too.

The native aiming state reads the fire scan, ignores its initialization
substate, and checks the shot cooldown and previous-press latch. A click that
ends during startup or recoil previously vanished. PC controls now retain one
pending click for up to 20 engine updates and submit it once the native aiming
state can accept it. A held button retains native repeat behavior. Releasing
aim, losing focus, entering a menu/story, damage, expiry or a new player
lifecycle discards the queued click. Aim startup receives no repeated toggle
trigger while the weapon is being raised.

Run the isolated engine regression with your imported game available:

```bash
SDL_VIDEODRIVER=offscreen SDL_AUDIODRIVER=dummy \
  .venv/bin/python tools/test_combat.py --output /tmp/re4-combat/check
```

It enters the existing synthetic mission-2 fixture on Extreme and checks that
the original and a custom sight draw no pixels immediately before/after the
native laser draw. For the remaining checks it reports the sight as drawn, as
a fixture-only positive control, sweeps aim angles and measures ammunition for quick mouse/keyboard
clicks during startup and recoil. It also checks reload and cancellation. It
does not qualify a full campaign or physical input hardware.

## Laser sight appearance

The launcher now offers Original, Circle, Predator (three dots) and animated
Black Matter artwork, with an RGB color picker and size multiplier. Defaults
preserve the native draw. Settings are host preferences; the renderer does not
patch game resources, saves, collision or damage calculations. Black Matter's
procedural purple/blue pattern uses the selected color as an accent.

The draw scope follows the same REA/Ghidra evidence described above and checked
against Capstone for the supported library. Only GL submissions inside the
laser draw are customized. Custom artwork reuses the endpoint model's native
vertices, indices, model/view/projection matrices and draw calls. The engine
therefore determines distance scaling, visibility, depth tests, blending and
fade/alpha. No extra endpoint is drawn from the beam alone. Original keeps its
native point geometry; other shapes change the artwork within that geometry.
The optional user size multiplier scales the native model about its own origin.
Host textures, UV arrays, upload state, matrices and color are restored after
each draw. The launcher preview uses the same procedural artwork.

The game-free tests cover preference migration and validation, color-picker
cancellation, preview/save/reset, minimum-size layout, Predator's three separate
dots, Black Matter animation, projection and real offscreen GL state/depth.
An isolated native-engine regression is available with imported game data:

```bash
SDL_VIDEODRIVER=offscreen SDL_AUDIODRIVER=dummy \
  .venv/bin/python tools/test_laser.py --output /tmp/re4-laser/check
```

All game fixtures, screenshots and analysis stay outside the checkout.

## FPS and graphics investigation — 2026-10-23

REA 6.4.0 with Ghidra 12.1.4/JDK 21 inspected
`PLT_Application::Check_FpsUpDate`, `GM_MisConduct::Frame` and
`Bio4_FrameWork::doMain`. The exact engine digest, Ghidra load-image source
mapping, ELF Thumb entries and first instructions were compared against the
existing Capstone verifier. Ghidra's measured image delta was `0x10000`.
Raw dossiers and verification records are under `/tmp/re4-fps/rea-*.json`,
outside the checkout.

The FPS check returns true unconditionally. Mission time increments after 20
native ticks. Framework execution and drawing occur consecutively in `doMain`.
These observations support retaining 20 Hz native calls and doing extra graphics
work entirely in the host. The resulting renderer copies submission state and
geometry, then interpolates it in a shared context on a separate presentation
thread. It never calls an extra native draw or restores guest memory snapshots.
See [rendering audit](render-audit.md) and [FPS verification](fps-performance.md).
