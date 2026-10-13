# Performance, engine and desktop roadmap results

This roadmap preserves Linux x86_64 and the authoritative 20 Hz simulation.
The work does not qualify a completed campaign or a higher presentation rate.
Phase results below distinguish implemented interfaces, measured checks and
remaining qualification gates. Raw game fixtures, captures, profiler output and
REA evidence are external under
`~/.local/state/re4mepc/roadmap-20261012/work/evidence`.

The original source baseline is revision
`4f8c1d4910d6535ed90aeadce37dce9369b299a5`. Before implementation, `make verify`
passed 265 component tests and the source/history audit. The benchmark added
source provenance before measurement; its recorded runtime-source digest is
`29354a6eeef171cdc4d8401eb0d945404ef859ac225f3d3596951decdaaf04e5`.
That run loaded its source before later edits. Reports now record the revision,
dirty status and a checksum of runtime sources plus the benchmark driver.
Resume rejects a different source identity, configuration, hardware or renderer.

The fixed reference system is Ryzen 9 6900HS, 15,943,704,576 bytes of RAM, Arch
Linux kernel 7.1.4-1-g14, and AMD Radeon RX 6700S with radeonsi/ACO, Mesa
26.1.5-arch1.1, OpenGL 4.6 compatibility profile. Logical rendering is 800×480.
All 15 baseline cases use that renderer; software renderer results are separate.
Each mode has five unprofiled repetitions with default diagnostics. Cold means
application caches only; OS page-cache eviction is not performed. Warm mode is
primed by a discarded run. Desktop background activity is uncontrolled; source
checks ran during some baseline samples, so variability is retained and no
optimization claim is made from small differences.

| Cache mode | Startup median (s) | Title→village median / range (s) | Worst loading frame median (ms) | Gameplay p95 median (ms) | Stage blocking median (s) |
|---|---:|---:|---:|---:|---:|
| Disabled | 0.7545 | 75.4360 / 74.8611–75.5514 | 4434.3 | 48.17 | 3.2401 |
| Cold | 0.7794 | 75.8044 / 75.2040–75.8418 | 4380.5 | 48.39 | 3.1752 |
| Warm | 0.7722 | 75.3523 / 75.1788–75.4946 | 4388.0 | 47.53 | 3.2299 |

The title replay includes fixed 150-tick settling periods after clicks. Its
elapsed time measures the reproducible navigation scenario, not pure loading
CPU time. Frame stalls and the separately measured stage blocking call expose
engine costs more directly. All stage transitions reach native stage 3 through
the existing synthetic lifecycle fixture; they do not certify a natural door.
Raw reports retain gameplay p50/p95/p99 and native/host phase counters.

Memory reports preserve the explicitly named process-lifetime peak RSS field.
Cases share one process; the approximately 2.706 GB late-run peak is not an
independent per-case RSS measurement or a proof of a leak. Guest live/peak
allocation counters remain separately available. The interleaved diagnostics
probe has five baseline/instrumented gameplay pairs and measures 0.70% median
work overhead, below the 5% gate for the original source.

Visible startup renders the intro, title and menu, receives nonzero audio output,
resizes/toggles fullscreen and passes native save/load. Its media callbacks peak
at 7.338 ms (audio), 0.812 ms (video) and 0.315 ms (video teardown). The original
visible gameplay replay passes keyboard aim/fire, aim release, mouse look,
movement, reload, knife, focus release, cursor capture and native mission timing.
Repeated original-source replays are recorded separately. A finite set of passes
does not establish that an intermittent aim failure is fixed; gameplay aiming
code is unchanged.

REA tool versions, download identities, address mappings and reproduction
commands are documented in [the native-analysis workflow](rea-workflow.md).
The provider initially failed in the temporary filesystem quota, then exposed a
Ghidra image rebase of 0x10000. Raw ELF addresses must be translated before
querying by address. The verifier checks measured mappings and source offsets,
not a guessed offset. REA's format-specific independent load-image verifier
supports DOS; ELF exposes provider observations. The project cross-checks those
observations against ELF and Capstone and retains that limitation.

REA validates three sampled functions per library with checked ARM/Thumb decoding, rebased source offsets, dossiers and pseudocode. All six mapping checks pass. This verifies the sampled provider coordinates, not every function or a complete relocation audit. The remaining roadmap phases are tracked separately.
