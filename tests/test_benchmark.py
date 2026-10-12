import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
from copy import deepcopy

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
