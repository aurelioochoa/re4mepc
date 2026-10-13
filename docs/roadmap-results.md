# Performance, engine and desktop roadmap results

This roadmap preserves Linux x86_64 and the authoritative 20 Hz simulation.
The work does not qualify a completed campaign or a higher presentation rate.
Phase results below distinguish implemented interfaces, measured checks and
remaining qualification gates. Raw game fixtures, captures, profiler output and
REA evidence are external under
`~/.local/state/re4mepc/roadmap-20261012/work/evidence`.

| Phase | Result | Remaining gate |
|---|---|---|
| Baseline and REA | Five repetitions per cache mode; supported ARM/Thumb mappings verified | Intermittent aim failure not reproduced |
| Loading investigation | Exclusive attribution and paired experiment implemented; candidate rejected | No loading improvement qualified |
| Desktop menus | Keyboard/virtual-controller navigation, inventory and cancellation checks pass | Intermittent native difficulty initialization exception; physical controller coverage |
| Portable captures | Gallery and optional save/media bundles implemented and round-trip checked | None for the implemented interfaces |
| Campaign and sessions | Input-only first-mission entry and separate synthetic/session evidence | User-deferred natural campaign, difficulties/modes/restarts; final two-hour gate incomplete |
| Release packages | Frozen candidates pass three clean OS smoke environments | Complete campaign and physical device/display/audio qualification |
| Rendering feasibility | Draw effects observed; independent boundary blocked by coupling | Shipping presentation remains 20 Hz |

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

Loading work now offers opt-in import dispatch profiling, per-service operation
ranking and separate loading/gameplay exclusive phases. Detailed profiles are
marked `profiled` and excluded from qualification. A profiled exploratory run
observes substantial dispatch work around repeated GLES calls; cProfile and
native hooks perturb its timings and ran alongside static analysis. They are
hotspot evidence, not paired performance proof. No runtime acceleration is
retained and texture caching stays opt-in.

The exploratory loading profile ranks exclusive unresolved native execution at
84.163 s, import dispatch at 22.815 s, graphics submission at 6.335 s and host
service bodies at 2.163 s. Unresolved execution also includes the separate
native-frame scope and unhooked C/FFI work. Repeated `glTexParameterf`,
`glMatrixMode` and `glLoadMatrixf` calls dominate dispatch operations. REA's
`Bio4_FrameWork::_execState_ResCtl` dossier follows resource-state queries,
resume handling and error-state changes; computed calls remain unresolved.
Static evidence explains this lifecycle but cannot attribute wall time to
individual indirect callees. Existing native helper coverage already handles
bounded memory/string operations. No additional helper or redundant GL-state
suppression was adopted without proven memory, output and GL-error equivalence.

One bounded candidate removes a redundant list copy after ctypes register
slicing. Register/callback arguments, stack arguments and negative-count errors
match the original before measurement. Two unprofiled batches of five pairs
alternate execution order on the same AMD renderer. They target the worst
loading frame and retain the exact source and candidate driver checksums.

| Batch | Paired median improvement | Baseline range / median | Gameplay p95 change | Timing gate |
|---|---:|---:|---:|---|
| 1 | −0.005% | 52.68% | −2.94% | Failed |
| 2 | 5.30% | 17.04% | +10.23% | Failed |

The candidate is rejected: neither batch achieves 10% above variability and
the second regresses gameplay p95 beyond 5%. Concurrent soak/static analysis
and source checks introduce contention; the observed figures do not establish
a causal speedup or regression. No optimization is shipped from this experiment.
The pre-JNI-fix source's five interleaved default-diagnostics pairs measure 3.26%
median overhead; the JNI-fix probe measures 0.69%, and the final inventory-cancel
runtime measures 1.10%. These probes pass the 5% gate.
An earlier 11.6% probe under heavier
contention failed and remains in the evidence; default trap and GL dispatch
paths were then kept separate from opt-in import profiling before the final run.

The longer session exposed per-frame JNI class-reference retention. Reusing the
existing class identity cache removes the observed 16-byte allocation per tick;
the isolated before/after probe and regression are recorded in campaign coverage.
This is a lifecycle correction, not an accepted loading-performance candidate.

Desktop menu routing and its visible input checks are documented in
[menu controls](menu-controls.md). Gallery exports and optional save/media
bundles are documented in [portable captures](portable-captures.md).
Natural campaign checkpoints and long-session coverage are tracked in
[campaign coverage](campaign-coverage.md). Package reports identify immutable
artifact hashes and their automated smoke scope separately from physical
hardware checks and campaign qualification. Independent rendering remains a
research result with demonstrated coupling; the release stays at 20 Hz.

Each phase has a separate reviewable commit and a fresh staged-source
`make verify` report. Package smoke reports belong to the immutable candidate
bytes, even while later authored tooling and documentation are committed.
Candidates are also copied to the ignored `dist/` directory with checked hashes.
They are not described as fully qualified releases while the campaign and
physical-device gates remain incomplete.

Session publication on 2026-10-13 is an experimental prerelease, with natural
mission completion explicitly deferred to the user's later playtest. Both soak
processes were stopped after preserving checkpoints. The final runtime reached
2,880.043 seconds; this does not satisfy the two-hour gate. The full campaign
and physical-device release gates remain unmet. The
[qualification summary](qualification-summary.md) records the exact artifact
hashes, matched reports, known intermittent native failure and manual checks.
