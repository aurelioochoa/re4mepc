import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from re4pc.diagnostics import Diagnostics


class FakeClock:
    now = 0.0
    def __call__(self):
        return self.now


class DiagnosticsTests(unittest.TestCase):
    def test_import_dispatch_services_and_unresolved_engine_partition_exclusively(self):
        clock = FakeClock()
        diagnostics = Diagnostics(clock=clock, import_hooks=True)
        with diagnostics.phase('native_frame'):
            clock.now += 2
            with diagnostics.phase('import_dispatch', 'fread'):
                clock.now += 1
                with diagnostics.phase('host_services', 'fread'):
                    clock.now += 3
                    with diagnostics.phase('file_read'):
                        clock.now += 5
                clock.now += 2
            clock.now += 4
        metrics = diagnostics.metrics()
        costs = {(r['phase'], r['operation']): r['seconds'] for r in metrics['import_operations']}
        self.assertEqual(costs, {('import_dispatch', 'fread'): 3, ('host_services', 'fread'): 3})
        self.assertEqual(metrics['import_attribution']['unresolved_engine_seconds'], 6)
        self.assertEqual(sum(p['seconds'] for p in metrics['phases'].values()), 17)
        plain = Diagnostics(clock=clock)
        plain.graphics_service('graphics_submission', 'glFinish', lambda: None, [])
        self.assertEqual(plain.metrics()['import_operations'], [])
        self.assertFalse(plain.metrics()['import_hooks_enabled'])

    def test_graphics_fast_service_partitions_parent_and_restores_operation_on_failure(self):
        clock = FakeClock()
        diagnostics = Diagnostics(clock=clock)
        def driver(value):
            self.assertEqual(value, 4)
            self.assertEqual(diagnostics.active_operation['name'], 'glFinish')
            clock.now += 3
            raise OSError('driver failed')
        with diagnostics.phase('native_unknown', 'engine'):
            clock.now += 2
            with self.assertRaises(OSError):
                diagnostics.graphics_service('graphics_submission', 'glFinish', driver, [4])
            self.assertEqual(diagnostics.active_operation['name'], 'engine')
            clock.now += 1
        phases = diagnostics.metrics()['phases']
        self.assertEqual(phases['native_unknown']['seconds'], 3)
        self.assertEqual(phases['graphics_submission']['seconds'], 3)
        self.assertEqual(phases['graphics_submission']['calls'], 1)
        self.assertIsNone(diagnostics.active_operation)

    def test_nested_phases_partition_wall_time_and_restore_stall_operation(self):
        clock = FakeClock()
        diagnostics = Diagnostics(clock=clock)
        with diagnostics.phase('native_unknown', 'engine tick'):
            clock.now = 1
            with diagnostics.phase('host_services', 'fread'):
                clock.now = 2
                with diagnostics.phase('file_read', 'resource.bin'):
                    clock.now = 5
                    self.assertEqual(diagnostics.active_operation, {'name':'resource.bin','seconds':3})
                clock.now = 6
                self.assertEqual(diagnostics.active_operation, {'name':'fread','seconds':5})
            clock.now = 10
        values = diagnostics.metrics()
        self.assertEqual(values['phases']['native_unknown']['seconds'], 5)
        self.assertEqual(values['phases']['host_services']['seconds'], 2)
        self.assertEqual(values['phases']['file_read']['seconds'], 3)
        self.assertEqual(sum(p['seconds'] for p in values['phases'].values()), 10)
        self.assertIsNone(values['active_operation'])
        self.assertIsNone(values['gpu_execution_seconds'])

    def test_exception_restores_phase_and_atomic_profile_contains_final_summary(self):
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'trace.jsonl'
            diagnostics = Diagnostics(profile=target, clock=clock)
            self.assertFalse(target.exists())
            with self.assertRaisesRegex(ValueError, 'failure'):
                with diagnostics.phase('startup', 'loading'):
                    clock.now = 3
                    raise ValueError('failure')
            self.assertIsNone(diagnostics.active_operation)
            diagnostics.close()
            diagnostics.close()
            records = [json.loads(line) for line in target.read_text().splitlines()]
            self.assertEqual(records[0]['schema_version'], 1)
            self.assertEqual(records[1]['exclusive_seconds'], 3)
            self.assertTrue(records[1]['failed'])
            self.assertEqual(records[-1]['type'], 'summary')
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_bounded_frame_percentiles_and_independent_presentation_counts(self):
        clock = FakeClock()
        diagnostics = Diagnostics(frame_capacity=3, clock=clock)
        for index, duration in enumerate((.1,.01,.02,.04)):
            clock.now = index*.05
            diagnostics.frame(duration)
            diagnostics.presentation()
            clock.now += .02
            diagnostics.presentation()
        values = diagnostics.metrics()
        self.assertEqual(values['frame_work_ms'], {'samples':3,'capacity':3,'p50':20,'p95':40,'p99':40})
        self.assertEqual(values['frames'], 4)
        self.assertEqual(values['presentations'], 8)
        self.assertEqual(values['overruns'], 1)
        self.assertAlmostEqual(values['simulation_hz'], 20)
        self.assertEqual(diagnostics.graph(), (10,20,40))
        for invalid in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError): diagnostics.frame(invalid)

    def test_allocation_search_is_reported_without_double_counting_phases(self):
        diagnostics = Diagnostics()
        diagnostics.allocation(1,16,2,.001)
        diagnostics.allocation(100,112,5,.002)
        diagnostics.freed(16)
        values = diagnostics.metrics()
        self.assertEqual(values['guest_live_bytes'],112)
        self.assertEqual(values['guest_peak_bytes'],128)
        self.assertEqual(values['counters']['allocation_requested_bytes'],101)
        self.assertEqual(values['counters']['free_block_search_probes'],7)
        self.assertAlmostEqual(values['allocator_search_seconds'],.003)
        self.assertNotIn('allocator_search',values['phases'])

    def test_overlay_reports_pending_audio_and_unknown_gpu(self):
        diagnostics = Diagnostics()
        game = SimpleNamespace(media=SimpleNamespace(pending_audio={1:[100],2:[80]}))
        lines = diagnostics.overlay_lines(game)
        self.assertIn('Audio decoding 2',lines[2])
        self.assertIn('GPU execution unknown',lines[-1])

    def test_operation_context_restores_parent_without_inventing_timed_phase(self):
        clock = FakeClock()
        diagnostics = Diagnostics(clock=clock)
        with diagnostics.phase('media'):
            clock.now = 1
            with diagnostics.operation('ffmpeg wait'):
                clock.now = 4
                self.assertEqual(diagnostics.active_operation['name'],'ffmpeg wait')
            self.assertEqual(diagnostics.active_operation['name'],'media')
        self.assertEqual(list(diagnostics.metrics()['phases']),['media'])
