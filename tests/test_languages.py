import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from re4pc.languages import (GAME_LANGUAGES, GAME_LANGUAGE_IDS, LAUNCHER_LANGUAGES,
                             CATALOGS, TEMPLATE_CATALOGS, apply_game_language, translate)
from re4pc.settings import Settings, validate
from re4pc.__main__ import argument_parser, main


class LanguageTests(unittest.TestCase):
    def test_old_settings_defaults_and_independent_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_text('{"sensitivity": 2}')
            values = Settings.load(path)
            self.assertEqual((values['game_language'], values['launcher_language']), ('en', 'en'))
            values.update(game_language='ja', launcher_language='es')
            Settings.save(values, path)
            loaded = Settings.load(path)
            self.assertEqual((loaded['game_language'], loaded['launcher_language']), ('ja', 'es'))
            override = Settings.load(path, {'game_language': 'saved'})
            self.assertEqual(override['game_language'], 'saved')
            self.assertEqual(override['launcher_language'], 'es')
            self.assertEqual(Settings.load(path)['game_language'], 'ja')
            self.assertEqual(loaded['sensitivity'], 2)

    def test_invalid_languages_do_not_publish(self):
        for key in ('game_language', 'launcher_language'):
            for value in ('xx', None, True, [], {}):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate({key: value})
        with self.assertRaises(ValueError):
            validate({'launcher_language': 'saved'})
        for code in GAME_LANGUAGES:
            self.assertEqual(validate({'game_language': code})['game_language'], code)

    def test_launcher_parity_and_complete_catalogs(self):
        from string import Formatter
        from re4pc.achievements import ACHIEVEMENTS
        self.assertEqual(set(LAUNCHER_LANGUAGES), set(GAME_LANGUAGE_IDS))
        fields = lambda text: {field for _, field, _, _ in Formatter().parse(text) if field}
        for code in CATALOGS:
            with self.subTest(language=code):
                self.assertEqual(set(CATALOGS[code]), set(CATALOGS['es']))
                self.assertEqual(set(TEMPLATE_CATALOGS[code]), set(TEMPLATE_CATALOGS['es']))
                for source, target in {**CATALOGS[code], **TEMPLATE_CATALOGS[code]}.items():
                    self.assertTrue(target.strip(), source)
                    self.assertEqual(fields(source), fields(target), source)
                for item in ACHIEVEMENTS:
                    self.assertIn(item.title, CATALOGS[code])
                    self.assertIn(item.description, CATALOGS[code])

    def test_all_launcher_languages_roundtrip_independently_and_keep_dynamic_values(self):
        expected = {'en': 'Play', 'es': 'Jugar', 'fr': 'Jouer', 'de': 'Spielen', 'it': 'Gioca', 'ja': 'プレイ'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            for code in LAUNCHER_LANGUAGES:
                with self.subTest(language=code):
                    Settings.save({'game_language': 'saved', 'launcher_language': code}, path)
                    self.assertEqual(Settings.load(path)['launcher_language'], code)
                    self.assertEqual(Settings.load(path)['game_language'], 'saved')
                    self.assertEqual(translate('Play', code), expected[code])
                    self.assertIn('3 / 22', translate('Progress: 3 / 22', code))
                    exported = translate('Exported 7 media files. 2 missing references are listed in achievements.json.', code)
                    for value in ('7', '2', 'achievements.json'):
                        self.assertIn(value, exported)
                    self.assertEqual(translate('/tmp/my saved game', code), '/tmp/my saved game')

    def test_native_languages_and_saved_noop(self):
        arm = Mock()
        arm.symbols = {'_ZZN13Bio4_UserData11GetInstanceEvE4inst': 0x1000}
        for code, identity in GAME_LANGUAGE_IDS.items():
            arm.reset_mock()
            apply_game_language(arm, code)
            arm.call.assert_called_once_with('_ZN13Bio4_UserData9SetLangIdEh', 0x1000, identity)
        arm.reset_mock()
        apply_game_language(arm, 'saved')
        arm.call.assert_not_called()

    def test_cli_defaults_to_preference_and_override_reaches_game(self):
        self.assertIsNone(argument_parser().parse_args(['run']).language)
        for code in GAME_LANGUAGES:
            self.assertEqual(argument_parser().parse_args(['run', '--language', code]).language, code)
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'XDG_CONFIG_HOME': directory}):
            Settings.save({'game_language': 'es', 'launcher_language': 'es'})
            with patch('re4pc.game.Game') as game:
                game.return_value.run.return_value = {'frames': 1, 'mean_engine_ms': 1}
                self.assertEqual(main(['run', '--frames', '1']), 0)
                self.assertEqual(game.call_args.args[6], 'es')
                self.assertEqual(main(['run', '--frames', '1', '--language', 'fr']), 0)
                self.assertEqual(game.call_args.args[6], 'fr')
            self.assertEqual(Settings.load()['game_language'], 'es')

    def test_translation_preserves_counts_and_unknown_paths(self):
        self.assertEqual(translate('Play', 'es'), 'Jugar')
        self.assertEqual(translate('Play'), 'Play')
        self.assertEqual(translate('Progress: 3 / 22', 'es'), 'Progreso: 3 / 22')
        self.assertEqual(translate('1 / 21 unlocked\nNo completions recorded yet.', 'es'),
                         '1 / 21 obtenidos\nTodavía no hay logros registrados.')
        self.assertEqual(translate('/tmp/my saved game', 'es'), '/tmp/my saved game')
        self.assertEqual(translate('Could not save settings: Permission denied', 'es'),
                         'No se pudieron guardar los ajustes: Permission denied')
