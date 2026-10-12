import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from re4pc.settings import Settings, validate, settings_path


class SettingsTests(unittest.TestCase):
    def test_unlock_capture_defaults_modes_and_duration_validation(self):
        self.assertEqual(validate({})['achievement_capture'], 'screenshot')
        for mode in ('off', 'screenshot', 'clip', 'both'):
            self.assertEqual(validate({'achievement_capture':mode})['achievement_capture'], mode)
        for values in ({'achievement_capture':'video'}, {'achievement_clip_seconds':4},
                       {'achievement_clip_seconds':16}, {'achievement_clip_seconds':True}):
            with self.assertRaises(ValueError):
                validate(values)
    def test_xdg_load_overrides_and_atomic_save(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'XDG_CONFIG_HOME':directory}):
            self.assertEqual(settings_path(), Path(directory)/'re4mepc/settings.json')
            values=Settings.load()
            values['sensitivity']=2
            Settings.save(values)
            self.assertEqual(Settings.load()['sensitivity'],2)
            self.assertEqual(Settings.load(overrides={'sensitivity':3})['sensitivity'],3)
            self.assertEqual(list(settings_path().parent.glob('.settings-*')),[])

    def test_failed_publication_preserves_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            Settings.save({},path)
            original=path.read_bytes()
            with patch('re4pc.settings.os.replace',side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):Settings.save({'sensitivity':2},path)
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(Path(directory).glob('.settings-*')),[])

    def test_invalid_settings_and_unaudited_rates_rejected(self):
        for values in ({'presentation_rate':30},{'presentation_rate':60},{'invert_y':1},
                       {'sensitivity':float('nan')},{'stick_dead_zone':1},{'version':2},
                       {'window_width':True},{'unexpected':1}):
            with self.subTest(values=values), self.assertRaises(ValueError):validate(values)
        values=validate({})
        values['bindings']['keyboard']['fire']=[119]
        with self.assertRaises(ValueError):validate(values)

    def test_corruption_is_explicit_and_does_not_overwrite_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            path.write_text('{bad')
            with self.assertRaises(json.JSONDecodeError):Settings.load(path)
            self.assertEqual(path.read_text(),'{bad')

    def test_relative_xdg_home_ignored(self):
        with patch.dict('os.environ',{'XDG_CONFIG_HOME':'relative/config'}):
            self.assertEqual(settings_path(),Path.home()/'.config/re4mepc/settings.json')
