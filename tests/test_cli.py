import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from re4pc.__main__ import argument_parser, main, write_json
from re4pc.settings import Settings


class CLITests(unittest.TestCase):
    def test_absent_overrides_preserve_saved_settings(self):
        args = argument_parser().parse_args(['run'])
        self.assertIsNone(args.width)
        self.assertIsNone(args.invert_y)
        self.assertIsNone(args.presentation_rate)
        self.assertFalse(args.cache)
        self.assertEqual(argument_parser().parse_args(['run', '--no-invert-y']).invert_y, False)
        self.assertTrue(argument_parser().parse_args(['run', '--cache']).cache)

    def test_unqualified_render_rates_are_rejected(self):
        with patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                argument_parser().parse_args(['run', '--presentation-rate', '30'])

    def test_settings_and_backup_cli_share_xdg_data_without_engine_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = dict(os.environ, XDG_STATE_HOME=str(root/'state'), XDG_CONFIG_HOME=str(root/'config'))
            installation = root/'game with spaces'
            (installation/'saves').mkdir(parents=True)
            (installation/'saves/save.dat').write_bytes(b'original')
            def command(*args):
                result = subprocess.run([sys.executable, '-m', 're4pc', *args], env=env,
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)
            snapshot = command('backup', '--game', str(installation))
            self.assertEqual(command('backups', '--game', str(installation))[0]['id'], snapshot['id'])
            archive = root/'export with spaces.zip'
            command('export-backup', snapshot['id'], str(archive), '--game', str(installation))
            (installation/'saves/save.dat').write_bytes(b'changed')
            command('restore-backup', snapshot['id'], '--game', str(installation))
            self.assertEqual((installation/'saves/save.dat').read_bytes(), b'original')
            self.assertEqual(command('settings', '--set', 'invert_y', 'true')['invert_y'], True)
            self.assertEqual(command('settings')['invert_y'], True)
            self.assertTrue(archive.is_file())

    def test_atomic_stats_failure_preserves_old_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'stats.json'
            path.write_text('old')
            with patch('re4pc.__main__.os.replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    write_json(path, {'frames': 4})
            self.assertEqual(path.read_text(), 'old')
            self.assertEqual(list(path.parent.iterdir()), [path])
