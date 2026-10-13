# Experimental prerelease qualification — 2026-10-13

**Experimental; not fully campaign-qualified.** Linux x86_64 only, with the
authoritative simulation and presentation at 20 Hz. Natural mission completion
is deferred to the user's later playtest. The final two-hour gate is incomplete.

## Frozen artifacts

| File | SHA-256 |
|---|---|
| re4mepc-linux-x86_64.AppImage | dbf6dc7df6f70a2e96ee15a8eb89a3c350ea3cb84d90334cc491bb5a6c7d5c11 |
| re4mepc-linux-x86_64.tar.gz | 20d94e814d2a0cf0aaf39c832779ccbcf1ec14c1d44027745ea7dcbe6495cd50 |

These exact bytes were rehashed before publication and matched every report
below. Repacking invalidates their qualification. The audited AppDir manifest
covers 2,334 files/links; all packaged application modules and artwork match
the final source. Runtime code is committed at `3aed82c`; its measured runtime
source digest is
`503295f0794cff95c44ff74e23d9a93f392b8c1801cd79f0740834b037dd82e7`.
Later source-publication changes concern documentation and its audit allowlist.

The four release assets are the AppImage, portable archive, SHA256SUMS and this
authored summary. Packages contain the host runtime and approved host artwork;
users must supply compatible game data separately. Proprietary game libraries,
assets, saves, private gameplay captures, raw logs and REA dumps remain external.

## Passed checks and their limits

- Final `make verify`: native helper builds, 294 component regressions and
  source/history publication audit. Each implementation phase also has its own
  staged-source verification and reviewable commit.
- Both formats pass clean Ubuntu 22.04, Ubuntu 24.04 and Arch container smoke
  checks using llvmpipe, Xvfb and dummy audio. The host images have no Python or
  compiler. Checks open Tk and run 160 engine ticks per format, share external
  settings/backups across formats, export selected achievement captures,
  deduplicate media, import PNG/MP4 save/media bundles then explicitly Restore,
  and round-trip legacy save-only archives. Paths include spaces.
- Upgrade coverage preserves settings and a snapshot created by the preceding
  portable build when launching either new format. The old AppImage is frozen
  as provenance but did not create the upgrade state.
- Four host startup cases pass: both formats on AMD RX 6700S and Radeon 680M,
  Mesa 26.1.5, with a visible window, 160 ticks and dummy audio. These are startup
  checks, not extended hardware gameplay or audible speaker qualification.
- Both bundled runtimes pass 1,720 ticks of fresh-install keyboard/mouse input
  through first-mission entry, manual panels, movement, inventory/submenu and
  cancellation back to gameplay. Captures were reviewed locally and native
  save/load passed. No synthetic progression or stage requests occur in these
  replays; neither replay completes a mission.
- Source keyboard/SDL virtual-controller replays cover held confirmation,
  focus loss, disconnect, inventory return, remappable menu routing, resizing,
  fullscreen and cursor capture. Physical controller behavior remains unverified.
- Capture and backup regressions cover duplicate/missing/conflicting media,
  unsafe paths, corrupt checksums, payload limits, stopped-installation locking
  and interrupted publication. Save-only compatibility is preserved.
- REA 6.4.0/Ghidra 12.1.4/JDK 21 inspect both supported ARM libraries, with six
  ARM/Thumb address mappings checked against ELF and Capstone. REA remains a
  development dependency. Its formal independent load-image verifier is DOS
  specific; ELF evidence is provider observation independently cross-checked
  by the project.

| Clean target | Exact validation image ID |
|---|---|
| Ubuntu 22.04 | sha256:4ef2da8a158d29e1f70e8c82b758d2e7dc8ca7230fc92148832ab4396faa566f |
| Ubuntu 24.04 | sha256:42a99fb2ec2edf3482ff703a764640a679b165bebe9030e4d35a38e01038dcac |
| Arch | sha256:004bdc81275499b16eb5b2722093c3adc2973c225d28e6d581ecfeeacf091ec7 |

## Actual findings and known failures

No loading optimization qualified. Five baseline repetitions per cache mode
were recorded on one AMD renderer. The bounded dispatch candidate failed both
independent five-pair batches: −0.005% and 5.30% median target improvement,
below the required 10% and measured variability; the second batch's gameplay
p95 increased 10.23%. Contention limits causal conclusions. Texture caching
stays opt-in. Final default diagnostics overhead measured 1.10%, below 5%.

An earlier completed 7,200.035-second soak exposed JNI class-reference growth:
one retained 16-byte handle per frame. Reusing the existing class identity cache
removes that growth in the isolated 1,200-tick probe. That earlier runtime's
two-hour duration does not qualify the final packages. A ten-minute follow-up
passed native save/load and 20 synthetic lifecycle cycles.

At the user's request, both remaining isolated soak processes were stopped
with SIGTERM on 2026-10-13 at 06:27:14 UTC after preserving their checkpoints.
Neither was restarted. The final runtime's last sample records 2,880.043 seconds
of continuous gameplay, 100% gameplay occupancy and 20 synthetic stage cycles.
From the five-minute warm-up sample, guest live bytes grew by 448, guest heap
bytes by 512, RSS decreased by 9,695,232 bytes and descriptor count was unchanged.
The last sample has no held inputs or queued audio. Its report is incomplete
(`completed: false`), with no recorded failure; the end-of-run save/load check
was not reached. The superseded concurrent run also stopped, at its
4,320.044-second checkpoint. **The final two-hour acceptance gate is unmet.**

An intermittent native title-to-difficulty initialization exception was observed
before and after the JNI correction. REA identifies a component lookup/virtual
call path; the underlying failure remains unresolved. Ten subsequent PC entry
trials and ten touch-only trials passed, which does not establish a fix. The
previous keyboard-aim failure was not reproduced in repeated original-source
replays and is not claimed fixed.

Qualification harness failures were corrected without changing the frozen
artifacts: Arch initially lacked `cmp` (test dependency `diffutils` added), a
symlinked XDG state path was rejected (test path canonicalized), and a replay
runner reused an extraction directory (retry separated extraction/evidence).
Only passing retries tied to the final hashes count as qualification.

Independent rendering research observes guest-memory writes and host effects
from extra draw calls. Static evidence shows draw-side interaction-state writes;
selected equal-tick fields alone cannot prove safe separation. No prototype or
30/60 FPS behavior ships. Interpolation across stage changes, destruction and
teleports remains unproved.

## Unmet gates and manual handoff

The roadmap ledger has nine met gates and two unmet phase gates: campaign/session
qualification and full package/device qualification. Publication is authorized
as an experimental prerelease despite those unmet gates.

- Complete all 22 story missions on Normal through natural progression, with
  local evidence for doors, bosses, companions, merchant actions, inventory,
  death/retry, completion and save/load. Currently zero story completions are
  qualified. Check representative missions on other difficulties, additional
  modes, ranks and achievement recovery, plus 20 natural restart/load cycles.
- Complete a two-hour session on the final runtime in a later validation session.
  Synthetic stage cycles and the interrupted final soak do not satisfy this gate.
- Check a physical controller, hot-plug, focus/cursor capture, resizing, HiDPI,
  fullscreen and audible speakers using final packages. Run extended gameplay
  on available AMD drivers. Intel/NVIDIA hardware and a physical controller were
  unavailable during this session and are not qualified.
- Reproduce and investigate the intermittent difficulty-initialization exception
  if encountered during playtest; preserve its evidence locally.

Authored details and reproduction commands are in the repository's
`docs/roadmap-results.md`, `docs/desktop-release.md`, `docs/campaign-coverage.md`,
`docs/menu-controls.md`, `docs/portable-captures.md`, `docs/rea-workflow.md` and
`docs/render-audit.md`. Raw evidence is retained outside the checkout at
`~/.local/state/re4mepc/roadmap-20261012/work/evidence/`, including
`session-stop-20261013`, `qualified-package-validation`, `qualified-package-amd`
and `qualified-natural-package-menu-retry`.
