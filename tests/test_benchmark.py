import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
from copy import deepcopy
from contextlib import ExitStack
from unittest.mock import Mock, patch
from tools import validate_session

spec = importlib.util.spec_from_file_location('benchmark', Path(__file__).resolve().parents[1]/'tools/benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    def test_nearest_rank_statistics_expose_outliers(self):
        values = list(range(1, 101))
        self.assertEqual(benchmark.quantiles(values), {'p50':50, 'p95':95, 'p99':99})
        self.assertEqual(benchmark.quantiles([]), {})
        self.assertEqual(benchmark.quantiles([50]), {'p50':50, 'p95':50, 'p99':50})

    def test_checkpoint_resume_preserves_cases_and_rejects_mixed_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'results.json'
            config = {'native_transition':3}
            case = {'repetition':1, 'mode':'cold', 'diagnostics_enabled':True,
                    'profiled':False, 'transition':{'verified':True, 'after_stage':3},
                    'stats':{'engine_hashes':benchmark.COMPATIBLE_LIBRARIES,
                             'settings':benchmark.validate_settings({}),
                             'graphics':{'renderer':'reference', 'version':'1'}}}
            document = {'schema_version':1, 'hardware':{'cpu':'reference'},
                        'configuration':config, 'records':[case]}
            benchmark.checkpoint(path, document)
            self.assertEqual(benchmark.resume_document(path, document['hardware'], config), document)
            self.assertFalse(path.with_suffix('.json.tmp').exists())
            with self.assertRaises(ValueError):
                benchmark.resume_document(path, {'cpu':'other'}, config)
            with self.assertRaises(ValueError):
                benchmark.resume_document(path, document['hardware'], {'native_transition':4})
            changed = deepcopy(case)
            changed['repetition'] = 2
            changed['stats']['graphics']['renderer'] = 'software fallback'
            document['records'].append(changed)
            benchmark.checkpoint(path, document)
            with self.assertRaisesRegex(ValueError, 'graphics drivers'):
                benchmark.resume_document(path, document['hardware'], config)
            document['records'].pop()
            document['records'].append(case)
            benchmark.checkpoint(path, document)
            with self.assertRaises(ValueError):
                benchmark.resume_document(path, document['hardware'], config)
            self.assertEqual(len(json.loads(path.read_text())['records']), 2)

    def test_session_failures_preserve_incomplete_report_and_close_resources(self):
        for failure_at in ('startup', 'save'):
            with self.subTest(failure_at=failure_at), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                root = Path(directory)
                game, replay = Mock(), Mock()
                stack.enter_context(patch.object(validate_session.sys, 'argv', [
                    'validate_session', '--game', directory, '--output', directory,
                    '--seconds', '0', '--cycles', '0']))
                stack.enter_context(patch.object(validate_session, 'isolated_game', return_value=root))
                factory = stack.enter_context(patch.object(validate_session, 'Game', return_value=game))
                stack.enter_context(patch.object(validate_session, 'Replay', return_value=replay))
                stack.enter_context(patch.object(validate_session, 'source_identity', return_value={}))
                stack.enter_context(patch.object(validate_session, 'sample', return_value={
                    'elapsed_seconds':0, 'held_keys':0, 'held_buttons':0}))
                if failure_at == 'startup':
                    factory.side_effect = RuntimeError('startup failure')
                else:
                    game.verify_save_roundtrip.side_effect = RuntimeError('save failure')
                with self.assertRaisesRegex(RuntimeError, failure_at + ' failure'):
                    validate_session.main()
                report = json.loads((root/'results.json').read_text())
                self.assertFalse(report['completed'])
                self.assertFalse(report['natural_campaign_verified'])
                self.assertEqual(report['failure'], failure_at + ' failure')
                if failure_at == 'save':
                    game.close.assert_called_once()
                    self.assertTrue(replay.close.called)
