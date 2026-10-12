# Timing and cache comparisons

F3 toggles an overlay with measured simulation Hz, presentation FPS, a bounded
frame-work graph, p50/p95/p99, overruns, guest memory and queued audio activity.
The host records the active operation before ARM calls and imported blocking
services. Periodic logs can report a stalled operation without waiting for a
frame to finish. The OpenGL context, guest execution and input consumption stay
on the main thread.

`run --stats PATH` writes an atomic JSON report with `schema_version: 2`.
Existing fields retain their meanings:

| Field | Meaning |
|---|---|
| frames | Executed native simulation ticks |
| mean_engine_ms / max_engine_ms | Legacy full frame work: queued input, native callback, imported host calls and media service; excludes polling, swap and pacing |
| heap_bytes | Guest heap high-water address extent, including free blocks |
| draw_calls / texture_uploads | Native GL draw/import upload counts; exclude host presentation blits |
| native_import_calls | Fast native memory/string helper invocation count |
| audio_output_frames / audio_nonzero_samples | Audio callback measurements; not speaker loudness |
| frame_overruns | Pacer missed deadlines; distinct from work exceeding 50 ms |
| elapsed_seconds | Game.run elapsed time excluding constructor/startup and shutdown |

New fields include separate presentation count, startup time, effective settings,
engine hashes, pending audio requests, successful/failed save transactions,
cache metrics and `diagnostics` (its own schema version 1).

`diagnostics.phases.*.seconds` is exclusive measured **wall time**: a child
phase is subtracted from its parent. `max_inclusive_seconds` includes child
work and must not be summed across phases. Startup validation/host/linking,
input polling/consumption, native frame/unknown work, imported host services,
file open/read/write/close/seek, texture conversion, graphics upload/submission,
audio/video service, swap and pacing have separate categories. The small
`native_frame` residue measures host entry overhead; `native_unknown` includes
unhooked ARM execution, Unicorn work, native helper CPU, and scheduler delays.
It also includes unclassified host-import dispatch and argument setup; it is not
a pure ARM-instruction CPU counter. Python profiling separates that dispatch
cost from imported service bodies and emulator self time.
It explicitly identifies unresolved work instead of attributing it to graphics.
GPU execution is `null`: CPU submission or window swap is not a GPU timer.
Allocator search time is a separate nested measurement; do not add it to the
exclusive phases. Memory is guest allocation reservation, not process RSS.
The allocation-size histogram keeps at most 128 exact sizes with an overflow
counter. Frame and presentation percentiles use nearest rank over the latest
240 samples; accumulated counts/totals/maxima span the run.

`--profile PATH` writes versioned JSONL phases and a final summary, atomically
publishing on close. Detailed traces add overhead. `--native-profile SYMBOL`
(repeatable) enables selected entry/return hooks; recursion and imported services
are excluded from exclusive native symbol time. Unknown symbols fail visibly.
Use `--no-diagnostics` for the default-instrumentation comparison; it is
incompatible with profiles. A failed trace remains visible in diagnostics.

`--cache` enables the experimental converted paletted texture cache;
`--no-cache` is the default comparison path. Cache entries contain immutable
RGBA bytes and dimensions, never guest pointers or GL objects. Source content,
format, dimensions, mip levels and converter version form the key. Each runtime
creates its own GL objects on the context thread. Memory is bounded at 64 MiB
and persistent entries at 256 MiB; publication uses a process lock, temporary
file, checksum validation and atomic replacement. Corruption recomputes pixels.
The default directory follows XDG_CACHE_HOME; `--cache-dir` isolates comparisons.
The cache remains opt-in until repeated loading measurements justify retention.
No allocator or parser acceleration is claimed from timing instrumentation.

`tools/benchmark.py` runs an isolated mission-2 fixture with fresh saves. It
records startup, title-to-village loading, sustained gameplay, hardware, settings,
hashes, peaks/stalls, cache metrics and versioned statistics. Default five runs
per disabled/cold/warm mode; `--compare-diagnostics` pairs instrumentation modes.
Startup measures constructor/linking readiness. The replay advances 200 engine
ticks before its title-to-village boundary; those initial resource-loading stalls
remain included in cumulative phases and maximum loading-frame work.
Warm samples are primed in the same installation. Cold refers to application
texture/audio caches; OS page cache remains uncontrolled. A supplied
`--transition-script PATH` uses JSON entries containing relative `frame` and
`event` tuples and must change the native loaded stage ID. Without a verified
transition, the report explicitly leaves the four-scenario release gate unmet.
`--python-profile` writes a cProfile artifact for the first sample; profiling
samples must be excluded from performance qualification.

`pending_audio_decodes` counts unfinished worker futures;
`pending_audio_requests` counts slots waiting to play. The overlay counts actual
unfinished decodes. File-read counts cover ARM imports and ELF loading; independent
media-worker file reads are outside those counters. Process RSS is additionally
reported as `peak_process_rss_bytes_since_process_start` (Linux ru_maxrss), so a
multi-case benchmark's later peaks include earlier cases. GL imports use one
attributed scope; non-nested imports avoid allocating a scope object in default
diagnostics, while detailed traces use the full scope path.

For a reproducible loading-lifecycle fixture, `--native-transition 3` requests a
change from the mission-2 fixture's loaded stage 2 to stage 3 through the native
event controller's audited stage-change routine. It ends/restarts native objects
and loads the actual stage assets. This is a synthetic request; it does not
certify a natural door/mission-completion route. `--overhead-probe` adds five
interleaved stationary gameplay windows per instrumentation mode in the first
case. It preserves the original 20 Hz pacing and records both medians and each
window, with a separate 5% acceptance result. Selective `--native-profile SYMBOL`
and cProfile samples are labelled `profiled` and cannot qualify optimizations.

Completed benchmark cases are atomically checkpointed after each run. Use the
same `--output`, modes, tick count and transition options with `--resume` to run
missing repetitions after interruption. Resume checks the schema, hardware,
configuration and duplicate case keys, then uses a fresh isolated installation
and primes its warm cache. Earlier reports without configuration metadata need
independent review of their original command before reuse. It never resumes a
partially executed case or accepts profiled samples as qualification evidence.
The overhead probe temporarily disables instrumentation. Its first case's
diagnostic counters, rates and allocation accounting therefore cover enabled
windows only; use subsequent fully instrumented cases for phase/memory totals.
The current top-level frame and presentation counts cover the complete run.
