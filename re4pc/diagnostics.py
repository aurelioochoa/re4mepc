"""Bounded runtime telemetry. Phase times are exclusive CPU/wall submission time.

GPU execution is deliberately unknown: SDL swap timing is not a GPU timer.
Detailed traces and native function hooks are optional and perturb execution.
"""
from collections import Counter, deque
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time


class _Phase:
    __slots__ = ('owner', 'name', 'operation', 'started', 'children')

    def __init__(self, owner, name, operation):
        self.owner, self.name, self.operation = owner, name, operation
        self.started = self.children = 0.0

    def __enter__(self):
        owner = self.owner
        self.started = owner.clock()
        owner._stack.append(self)
        owner._active = (self.operation or self.name, self.started)
        return self

    def __exit__(self, *error):
        owner = self.owner
        elapsed = max(0.0, owner.clock() - self.started)
        exclusive = max(0.0, elapsed - self.children)
        owner._stack.pop()
        owner._seconds[self.name] += exclusive
        owner._counts[self.name] += 1
        owner._maximum[self.name] = max(owner._maximum[self.name], elapsed)
        if owner.import_hooks and self.operation and self.name in (
                'import_dispatch', 'host_services', 'graphics_upload', 'graphics_submission'):
            key = (self.name, self.operation)
            owner._operation_seconds[key] += exclusive
            owner._operation_counts[key] += 1
        if owner._stack:
            parent = owner._stack[-1]
            parent.children += elapsed
            owner._active = (parent.operation or parent.name, parent.started)
        else:
            owner._active = None
        if owner._trace is not None:
            owner._write_trace({'type': 'phase', 'name': self.name,
                'operation': self.operation, 'start_seconds': self.started-owner.started,
                'duration_seconds': elapsed, 'exclusive_seconds': exclusive,
                'failed': bool(error and error[0])})


class Diagnostics:
    """Phase scopes belong to the runtime/GL thread; the heartbeat may read them."""
    SCHEMA_VERSION = 1

    def __init__(self, profile=None, native_hooks=False, frame_capacity=240, clock=None, import_hooks=False):
        if frame_capacity < 1:
            raise ValueError('Frame capacity must be positive')
        self.clock = clock or time.perf_counter
        self.started = self.clock()
        self.native_hooks = native_hooks
        self.import_hooks = import_hooks
        if import_hooks:
            self.graphics_service = self._profile_graphics_service
        self._operation_seconds, self._operation_counts = Counter(), Counter()
        self._stack = []
        self._active = None
        self._seconds, self._counts, self._maximum = Counter(), Counter(), Counter()
        self._counters, self._sizes = Counter(), Counter()
        self._size_overflow = 0
        self._frames = deque(maxlen=frame_capacity)
        self._ticks, self._presentations = deque(maxlen=frame_capacity), deque(maxlen=frame_capacity)
        self.frames = self.presentations = self.overruns = 0
        self.live_memory = self.peak_memory = 0
        self._profile = Path(profile) if profile is not None else None
        self._trace = self._trace_path = None
        self._trace_lock = threading.Lock()
        self.trace_error = None
        if self._profile is not None:
            self._profile.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix=self._profile.name+'.', suffix='.tmp',
                                                dir=self._profile.parent)
            self._trace_path = Path(name)
            self._trace = os.fdopen(descriptor, 'w', encoding='utf-8')
            self._write_trace({'type': 'header', 'schema_version': self.SCHEMA_VERSION,
                'format': 're4mepc-profile-jsonl', 'timing': 'exclusive wall time',
                'gpu_execution_seconds': None})

    def phase(self, name, operation=None):
        return _Phase(self, name, operation)

    def graphics_service(self, name, operation, callback, arguments):
        """Time a GL import that cannot open child phases, without scope allocation.

        Compressed conversion uses normal nested scopes. Detailed traces also
        take that path so each trace records the same exception information.
        This fast path still attributes every call and sets its active operation
        before entering the graphics driver. It never estimates GPU execution.
        """
        if self._trace is not None:
            with self.phase(name, operation):
                return callback(*arguments)
        started = self.clock()
        previous = self._active
        self._active = (operation, started)
        try:
            return callback(*arguments)
        finally:
            elapsed = max(0.0, self.clock()-started)
            self._active = previous
            self._seconds[name] += elapsed
            self._counts[name] += 1
            if elapsed > self._maximum[name]:
                self._maximum[name] = elapsed
            if self._stack:
                self._stack[-1].children += elapsed

    def _profile_graphics_service(self, name, operation, callback, arguments):
        with self.phase(name, operation):
            return callback(*arguments)

    def external_graphics(self, seconds, calls, maximum):
        """Attribute native bridge CPU time once per engine call, never as GPU time."""
        self._seconds['graphics_submission'] += seconds
        self._counts['graphics_submission'] += calls
        self._maximum['graphics_submission'] = max(self._maximum['graphics_submission'], maximum)
        if self._stack:
            self._stack[-1].children += seconds

    @contextmanager
    def operation(self, name):
        previous = self._active
        self._active = (name, self.clock())
        try:
            yield
        finally:
            self._active = previous

    @property
    def active_operation(self):
        active = self._active
        if active is None:
            return None
        return {'name': active[0], 'seconds': max(0.0, self.clock()-active[1])}

    def count(self, name, amount=1):
        self._counters[name] += amount

    def allocation(self, requested, reserved, probes, search_seconds):
        self.count('allocation_count')
        self.count('allocation_requested_bytes', requested)
        self.count('allocation_reserved_bytes', reserved)
        self.count('free_block_search_probes', probes)
        self._seconds['allocator_search'] += search_seconds
        if reserved in self._sizes or len(self._sizes) < 128:
            self._sizes[reserved] += 1
        else:
            self._size_overflow += 1
        self._maximum['allocator_search_probes'] = max(self._maximum['allocator_search_probes'], probes)
        self.live_memory += reserved
        self.peak_memory = max(self.peak_memory, self.live_memory)

    def freed(self, reserved):
        self.count('free_count')
        self.live_memory -= reserved

    def frame(self, seconds):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError('Frame duration must be finite and nonnegative')
        self.frames += 1
        self._frames.append(seconds)
        self._ticks.append(self.clock())
        if seconds > .05:
            self.overruns += 1

    def presentation(self):
        self.presentations += 1
        self._presentations.append(self.clock())

    @staticmethod
    def _rate(samples):
        return (len(samples)-1)/(samples[-1]-samples[0]) if len(samples)>1 and samples[-1]>samples[0] else 0.0

    def graph(self):
        return tuple(value*1000 for value in self._frames)

    def metrics(self):
        frames = sorted(self._frames)
        def percentile(samples, value):
            if not samples:
                return 0.0
            return samples[max(0, math.ceil(value*len(samples))-1)] * 1000
        times = tuple(self._presentations)
        presentations = sorted(b-a for a, b in zip(times, times[1:]))
        # Allocator search is a nested measurement, not an attributable phase.
        phases = {name: {'seconds': value, 'calls': self._counts[name],
                        'max_inclusive_seconds': self._maximum[name]}
                  for name, value in self._seconds.items() if name != 'allocator_search'}
        return {'schema_version': self.SCHEMA_VERSION, 'phase_timing': 'exclusive_wall_seconds',
            'phases': phases, 'gpu_execution_seconds': None,
            'native_attribution': 'unhooked native and native-helper time is native_unknown',
            'frames': self.frames, 'presentations': self.presentations,
            'simulation_hz': self._rate(self._ticks), 'presentation_fps': self._rate(self._presentations),
            'frame_work_ms': {'samples': len(frames), 'capacity': self._frames.maxlen,
                'p50': percentile(frames, .5), 'p95': percentile(frames, .95), 'p99': percentile(frames, .99)},
            'presentation_interval_ms': {'samples': len(presentations),
                'p50': percentile(presentations, .5), 'p95': percentile(presentations, .95),
                'p99': percentile(presentations, .99)},
            'overruns': self.overruns, 'active_operation': self.active_operation,
            'counters': dict(self._counters), 'allocation_sizes': dict(self._sizes),
            'allocation_size_histogram_overflow': self._size_overflow,
            'guest_live_bytes': self.live_memory, 'guest_peak_bytes': self.peak_memory,
            'allocator_search_seconds': self._seconds['allocator_search'],
            'allocator_max_search_probes': self._maximum['allocator_search_probes'],
            'native_hooks_enabled': bool(self.native_hooks), 'trace_error': self.trace_error,
            'import_hooks_enabled': bool(self.import_hooks),
            'import_attribution': {
                'dispatch': 'Python trap after symbol lookup, excluding nested service scopes; C/FFI hook entry remains unresolved',
                'service_bodies': 'exclusive host_services, graphics_submission and graphics_upload; nested I/O and conversions are separate phases',
                'unresolved_engine_seconds': self._seconds['native_unknown'] + self._seconds['native_frame'],
                'unresolved_includes': 'Unicorn execution, C native helpers and uninstrumented C/FFI dispatch; no static timing estimate'},
            'import_operations': [{'phase': phase, 'operation': operation, 'seconds': seconds,
                                   'calls': self._operation_counts[(phase, operation)]}
                                  for (phase, operation), seconds in sorted(self._operation_seconds.items(),
                                      key=lambda item: (-item[1], item[0]))]}

    def overlay_lines(self, game):
        values = self.metrics()
        frame = values['frame_work_ms']
        media = getattr(game, 'media', None)
        futures = getattr(media, 'decoding', None)
        pending = sum(not future.done() for future in futures.values()) if futures is not None else getattr(media, 'pending_audio', None)
        if pending is None:
            pending = getattr(media, '_audio_futures', ())
        try:
            pending = len(pending)
        except TypeError:
            pending = pending if isinstance(pending, int) else 0
        active = values['active_operation']
        if active and active['name'] == 'diagnostics_overlay':
            active = None
        pc = getattr(game, 'pc', None)
        state = 'video' if getattr(media, 'video', None) is not None else 'gameplay' if getattr(pc, 'active', False) else 'menu/loading'
        reads = self._counters['file_read_count']
        return (
            f"Simulation {values['simulation_hz']:.1f} Hz   Presentation {values['presentation_fps']:.1f} FPS",
            f"Work p50 {frame['p50']:.1f}  p95 {frame['p95']:.1f}  p99 {frame['p99']:.1f} ms",
            f"Overruns {self.overruns}   Audio decoding {pending}",
            f"Guest {self.live_memory/1048576:.1f} MiB   peak {self.peak_memory/1048576:.1f} MiB",
            f"Operation: {active['name']} ({active['seconds']:.2f}s)" if active else f'Mode: {state}   Resource reads: {reads}',
            'Graphics: CPU submission; GPU execution unknown',
        )

    def _write_trace(self, record):
        # Trace failure must not crash gameplay; it remains visible in stats.
        with self._trace_lock:
            if self._trace is None:
                return
            try:
                self._trace.write(json.dumps(record, separators=(',', ':'))+'\n')
            except OSError as error:
                self.trace_error = str(error)
                try:
                    self._trace.close()
                except OSError:
                    pass
                self._trace = None

    def close(self):
        if self._trace is None:
            self._discard_partial_trace()
            return
        self._write_trace({'type': 'summary', 'metrics': self.metrics()})
        if self._trace is None:
            self._discard_partial_trace()
            return
        try:
            self._trace.flush()
            os.fsync(self._trace.fileno())
            self._trace.close()
            self._trace = None
            os.replace(self._trace_path, self._profile)
        except OSError as error:
            self.trace_error = str(error)
            if self._trace is not None:
                try:
                    self._trace.close()
                except OSError:
                    pass
                self._trace = None
            self._discard_partial_trace()

    def _discard_partial_trace(self):
        if self._trace_path is not None:
            try:
                self._trace_path.unlink(missing_ok=True)
            except OSError:
                pass
