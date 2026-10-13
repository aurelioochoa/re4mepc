"""Exercise desktop installation in isolated homes without running the game."""
import io
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from re4pc.desktop import apk_icon, exec_value, inspect_icon, install, locations, uninstall


def png(size):
    stream = io.BytesIO()
    Image.new('RGBA', (size, size), (20, 40, 60, 255)).save(stream, format='PNG')
    return stream.getvalue()


class DesktopTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.home = base / 'home with spaces'
        self.home.mkdir()
        self.root = base / 'checkout with spaces \' "$`%\\'
        self.root.mkdir()
        for name in ('re4pc.sh', '.venv/bin/python', 'build/libre4audio.so', 'build/libre4fast.so'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            path.chmod(0o755)
        self.icon = base / 'cover.png'
        self.icon.write_bytes(png(32))
        self.addCleanup(patch.stopall)
        patch('pathlib.Path.home', return_value=self.home).start()
        patch.dict(os.environ, {
            'XDG_DATA_HOME': str(self.home / 'data with spaces'),
            'XDG_STATE_HOME': str(self.home / 'state with spaces'),
        }).start()

    def test_install_launch_and_remove_preserve_game(self):
        desktop = self.home / 'Escritorio'
        desktop.mkdir()
        game = self.home / 'my game'
        game.mkdir()
        save = game / 'save.dat'
        save.write_text('synthetic save')
        launcher, entry, icon = install(self.root, icon=self.icon, game=game, desktop=desktop)
        self.assertTrue(os.access(launcher, os.X_OK))
        self.assertEqual(icon.read_bytes(), self.icon.read_bytes())
        shortcut = desktop / entry.name
        self.assertEqual(entry.read_bytes(), shortcut.read_bytes())
        self.assertIn('Terminal=false', entry.read_text())
        self.assertTrue(os.access(shortcut, os.X_OK))
        result = subprocess.run([str(launcher), '--help'], cwd='/', text=True,
                                capture_output=True, check=True)
        self.assertEqual(result.stdout.splitlines(), [
            '--help',
        ])
        for args, expected in (
                ([], ['launcher', '--game', str(game)]),
                (['--game', '/another game'], ['launcher', '--game', str(game), '--game', '/another game']),
                (['run', '--skip-videos'], ['run', '--game', str(game), '--skip-videos']),
                (['check', '--game', '/another game'], ['check', '--game', str(game), '--game', '/another game']),
                (['import', '/path/to/game.apk'], ['import', '/path/to/game.apk']),
                (['settings'], ['settings']),
                (['export-backup', 'snapshot', '/backup with spaces.zip'],
                 ['export-backup', '--game', str(game), 'snapshot', '/backup with spaces.zip'])):
            with self.subTest(args=args):
                result = subprocess.run([str(launcher), *args], cwd='/', text=True,
                                        capture_output=True, check=True)
                self.assertEqual(result.stdout.splitlines(), expected)
        if shutil.which('desktop-file-validate'):
            subprocess.run(['desktop-file-validate', str(entry)], check=True, capture_output=True)
        # An update can reuse the installed icon after the original is removed.
        self.icon.unlink()
        install(self.root, game=game)
        uninstall(desktop)
        self.assertFalse(any(path.exists() for path in (launcher, entry, icon, shortcut)))
        self.assertEqual(save.read_text(), 'synthetic save')

    def test_apk_selects_largest_launcher_png_and_never_extracts_paths(self):
        apk = self.home / 'synthetic.apk'
        large = png(128)
        with zipfile.ZipFile(apk, 'w') as archive:
            archive.writestr('res/drawable/icon.png', png(32))
            archive.writestr('res/mipmap-xxhdpi/ic_launcher.png', large)
            archive.writestr('res/drawable/background.png', png(256))
            archive.writestr('../outside.png', png(256))
            archive.writestr('res/drawable-hdpi/app_icon.png', b'invalid PNG')
        self.assertEqual(apk_icon(apk), large)
        _, _, icon = install(self.root, apk=apk)
        self.assertEqual(icon.read_bytes(), large)
        self.assertFalse((self.home.parent / 'outside.png').exists())

    def test_apk_without_conventional_icon_gives_actionable_error(self):
        apk = self.home / 'synthetic.apk'
        with zipfile.ZipFile(apk, 'w') as archive:
            archive.writestr('res/drawable/background.png', png(32))
        with self.assertRaisesRegex(ValueError, 'use --icon'):
            apk_icon(apk)

    def test_invalid_icon_or_missing_setup_does_not_install(self):
        self.icon.write_bytes(b'not an image')
        with self.assertRaises(OSError):
            install(self.root, icon=self.icon)
        self.assertFalse(any(path.exists() for path in locations()))
        self.icon.write_bytes(png(32))
        (self.root / 'build/libre4audio.so').unlink()
        with self.assertRaisesRegex(ValueError, 'setup.sh'):
            install(self.root, icon=self.icon)
        self.assertFalse(any(path.exists() for path in locations()))

    def test_exec_escapes_field_codes_and_reserved_characters(self):
        # Desktop strings decode backslashes once, then Exec parses its quotes.
        value = exec_value('/tmp/50% "quote" $cash `tick` \\slash')
        self.assertEqual(value, '"/tmp/50%% \\\\"quote\\\\" \\\\$cash \\\\`tick\\\\` \\\\\\\\slash"')

    def test_icon_validation_rejects_other_formats_and_oversized_images(self):
        stream = io.BytesIO()
        Image.new('RGB', (4, 4)).save(stream, format='JPEG')
        with self.assertRaisesRegex(ValueError, 'PNG'):
            inspect_icon(stream.getvalue())
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            inspect_icon(png(4097))

    def test_missing_icon_and_invalid_desktop_fail_before_writing(self):
        with self.assertRaisesRegex(ValueError, 'Choose an icon'):
            install(self.root)
        with self.assertRaisesRegex(ValueError, 'existing directory'):
            install(self.root, icon=self.icon, desktop=self.home / 'absent')
        self.assertFalse(any(path.exists() for path in locations()))

    def test_generated_default_icon_is_used_without_an_apk(self):
        bundled = self.root / 're4pc/ui_assets/icon.png'
        bundled.parent.mkdir(parents=True)
        bundled.write_bytes(png(128))
        _, entry, icon = install(self.root)
        self.assertEqual(icon.read_bytes(), bundled.read_bytes())
        self.assertIn('Terminal=false', entry.read_text())
