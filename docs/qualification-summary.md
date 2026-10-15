# Experimental public test qualification — 2026-10-14

[Release v0.1.0-experimental.20261014](https://github.com/aurelioochoa/re4mepc/releases/tag/v0.1.0-experimental.20261014)
is **experimental and not fully campaign-qualified**. Linux x86_64 only;
authoritative simulation and presentation remain at 20 Hz. Users supply their
own compatible APK. Campaign, endurance and broader physical-device work remain
deferred; this refresh qualifies packaging, languages and the startup/inventory path.

## Frozen artifacts

| File | SHA-256 |
|---|---|
| re4mepc-linux-x86_64.AppImage | d492232505f33e386e1a37034dcf59075e763a743bd88e3f3c2e93c4ed32ca46 |
| re4mepc-linux-x86_64.tar.gz | 2454aabd36526d3c8f8d9eb726cf6bcc1772b25d4682f3bfc595a5008df293c2 |

Both formats were rebuilt from the same Ubuntu 22.04 AppDir. Its audited manifest
contains 2,338 files/links. All application modules and artwork match the current
source. The runtime code is unchanged from commit `3052793`; its measured source
digest, including native inputs and the benchmark identity helper, is
`d826e79b9f13eaf7612c350b261914daa06994b4bb446301b89fcb97d4a6943d`.
The release commit additionally includes the packaging fix, validation harness
and this qualification record. Repacking invalidates qualification of these bytes.

The refresh includes independent game/launcher selectors for English, Spanish,
French, German, Italian and Japanese, plus bundled Japanese fonts and their
license. The first fresh build exposed an existing staging conflict: the font
license created `usr/share/doc` before the dependency-notice copy. Merging the
notices fixes that build failure; a regression checks preservation of the font
license and dependency notices across repeated copies.

Release assets are the AppImage, portable archive, SHA256SUMS and this summary.
Imported engine libraries/assets, saves, private gameplay captures and raw logs
remain external. Runtime dependencies and notices accompany the packages.

## Clean-system checks on these exact bytes

Both formats pass clean Ubuntu 22.04, Ubuntu 24.04 and Arch images with Mesa,
Xvfb and dummy audio. Hosts have no Python or compiler. Checks cover real Tk
launchers, 160 engine ticks, settings/backups shared between formats, selected
achievement exports with media deduplication, PNG/MP4 save/media bundles followed
by explicit Restore, and legacy save-only roundtrips. Paths contain spaces.

Each format on each OS also opens all six launcher languages, exercises language
selection, restores saved preferences in a reopened launcher, and verifies
Japanese glyph coverage from the bundled IPAGothic font. On Ubuntu 22.04, both
bundled runtimes additionally verify the native language ID and execute 160 ticks
for each of the six game languages. These checks cover selection and startup,
not a campaign playthrough in each language. Six packaged launcher screenshots
were reviewed locally, including Japanese.

| Clean target | Exact validation image ID |
|---|---|
| Ubuntu 22.04 | sha256:c13f92ac9065498426f64bb54fdb10224344ab21421da660d1e50b0272053983 |
| Ubuntu 24.04 | sha256:50929d2825d645a8e1f49359283b92e2a3177a95f3efa47e0d60a5416bc94385 |
| Arch | sha256:f41096f88c54b01091e7f5d3bcbe8c52dfe3abcbe5b46f408654cb63f388d5e0 |

Upgrade checks start with the preceding portable prerelease, retain its settings
and save snapshot, then launch both refreshed formats. The previous AppImage is
also frozen and hashed, but does not create the upgrade state. Neither preceding
artifact was changed.

## First-mission and inventory replay

Both extracted bundled runtimes use fresh isolated game fixtures on AMD RX 6700S,
Mesa 26.1.5. Keyboard/mouse events reach the first mission; observed native menu
states confirm inventory entry, handgun submenu, cancellation to inventory and
return to active gameplay. Screenshots of each state were reviewed locally.
Native save/load passes, and the replays finish in gameplay without GL errors.
No progression records or stage changes are injected; no mission is completed.
Audio uses the dummy device and does not qualify speakers.

| Format | Measured ticks | Native save/load |
|---|---|---|
| portable | 1610 | Passed |
| appimage | 1610 | Passed |

The initial fixed-timestamp replay exited successfully but screenshot review
showed a transition frame and an incomplete inventory round trip. It is not
counted as a pass for these interactions. The qualifying retry waits for observed
menu states before capturing and checking each result; application code was
unchanged. Arch initially inherited bundled libraries while starting the host
Xvfb shell, causing a Readline symbol conflict. Starting host Xvfb before applying
the package environment makes the unchanged artifacts pass; the failed log is
preserved separately. A separate screenshot-helper retry corrected its container display
startup; it did not change the package bytes.

Source verification covers **313 component tests**, native helper builds and the
complete source/history publication audit. The release commit must pass the same
CI check before repository visibility changes.

## Retained limitations and historical evidence

- Zero naturally completed story missions are qualified. All 22 missions,
  other difficulties/modes/ranks and natural restart cycles remain unverified.
- There is no completed two-hour qualification on this refreshed runtime.
  The previous runtime's interrupted 2,880.043-second checkpoint remains historical.
- The intermittent native title-to-difficulty initialization exception remains
  unresolved. Passing startup/replay runs do not establish a fix.
- Physical controllers, display/HiDPI, audible speakers, extended GPU gameplay
  and Intel/NVIDIA hardware remain outside this refresh's qualification.
- No loading optimization qualified; converted-texture caching stays opt-in.
  Independent rendering is unproved and no 30/60 FPS mode ships.

The preceding [2026-10-13 prerelease](https://github.com/aurelioochoa/re4mepc/releases/tag/v0.1.0-experimental.20261013)
and its attached qualification summary remain unchanged. Its AppImage hash is
`dbf6dc7df6f70a2e96ee15a8eb89a3c350ea3cb84d90334cc491bb5a6c7d5c11`;
its archive hash is
`20d94e814d2a0cf0aaf39c832779ccbcf1ec14c1d44027745ea7dcbe6495cd50`.
Earlier RX 6700S/680M startup checks and session/performance measurements apply to
those recorded artifacts/runtime identities, not automatically to this refresh.

Raw evidence stays local under
`~/.local/state/re4mepc/public-launch-20261014/evidence/`, including
`clean-packages`, `launcher-previews` and `natural-package-menu-verified`.
See [desktop package validation](desktop-release.md),
[campaign coverage](campaign-coverage.md) and [roadmap results](roadmap-results.md).
