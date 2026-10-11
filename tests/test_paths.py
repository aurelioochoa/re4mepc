import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from re4pc.paths import game_dir, logs_dir, isolated_game, test_output
from re4pc.__main__ import main


class PathTests(unittest.TestCase):
    def test_xdg_defaults_and_overrides_are_independent_of_cwd(self):
        with patch.dict(os.environ, {'HOME':'/tmp/synthetic-home', 'XDG_DATA_HOME':'', 'XDG_STATE_HOME':''}):
            self.assertEqual(game_dir(),Path('/tmp/synthetic-home/.local/share/re4mepc/game'))
            self.assertEqual(logs_dir(),Path('/tmp/synthetic-home/.local/state/re4mepc/logs'))
        with patch.dict(os.environ, {'XDG_DATA_HOME':'/tmp/synthetic-data', 'XDG_STATE_HOME':'/tmp/synthetic-state'}):
            self.assertEqual(game_dir(),Path('/tmp/synthetic-data/re4mepc/game'))
            self.assertEqual(logs_dir(),Path('/tmp/synthetic-state/re4mepc/logs'))
        with patch.dict(os.environ, {'XDG_DATA_HOME':'relative', 'XDG_STATE_HOME':'relative'}):
            self.assertTrue(game_dir().is_absolute())
            self.assertTrue(logs_dir().is_absolute())
            self.assertNotIn('relative',game_dir().parts)

    def test_cli_defaults_and_explicit_import_check_paths(self):
        with patch.dict(os.environ, {'XDG_DATA_HOME':'/tmp/synthetic-data'}):
            for arguments,expected in [(['import','fixture.apk'],game_dir()),
                                       (['import','fixture.apk','--output','custom'],Path('custom'))]:
                with patch('sys.argv',['re4pc',*arguments]), patch('re4pc.__main__.import_apk') as importer, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(),0)
                    importer.assert_called_once_with(Path('fixture.apk'),expected)
            for arguments,expected in [(['check'],game_dir()),(['check','--game','custom'],Path('custom'))]:
                with patch('sys.argv',['re4pc',*arguments]), patch('re4pc.__main__.validate') as validator, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(),0)
                    validator.assert_called_once_with(expected)

    def test_cli_run_defaults_and_explicit_game_path(self):
        with patch.dict(os.environ, {'XDG_DATA_HOME':'/tmp/synthetic-data'}):
            for arguments,expected in [(['run','--frames','1'],game_dir()),(['run','--game','custom','--frames','1'],Path('custom'))]:
                with patch('sys.argv',['re4pc',*arguments]), patch('re4pc.game.Game') as game:
                    game.return_value.run.return_value={'frames':1,'mean_engine_ms':0}
                    self.assertEqual(main(),0)
                    self.assertEqual(game.call_args.args[0],expected)

    def test_each_fixture_has_fresh_saves_and_independent_input_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';output=root/'output'
            for folder in ('lib','data','saves','cache'):
                (source/folder).mkdir(parents=True)
                (source/folder/'synthetic').write_bytes(b'preserve')
            with patch('re4pc.assets.validate',return_value=source):
                first=isolated_game(source,output);second=isolated_game(source,output)
            self.assertNotEqual(first,second)
            self.assertEqual(list((first/'saves').iterdir()),[])
            self.assertFalse((first/'cache').exists())
            (first/'lib/synthetic').write_bytes(b'changed')
            (first/'saves/save.dat').write_bytes(b'test save')
            self.assertEqual((source/'lib/synthetic').read_bytes(),b'preserve')
            self.assertEqual((source/'saves/synthetic').read_bytes(),b'preserve')
            self.assertEqual((second/'lib/synthetic').read_bytes(),b'preserve')

    def test_fixture_rejects_output_inside_user_game(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)
            with patch('re4pc.assets.validate',return_value=source):
                for output in (source,source/'child'):
                    with self.assertRaisesRegex(ValueError,'outside'): isolated_game(source,output)

    def test_default_test_outputs_are_external_and_unique(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'XDG_STATE_HOME':directory}):
            first=test_output('visible-test');second=test_output('visible-test')
            self.assertNotEqual(first,second)
            self.assertEqual(first.parent,logs_dir()/'visible-test')
