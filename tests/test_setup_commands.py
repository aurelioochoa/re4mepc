"""Exercise public setup commands in isolated checkouts without installing packages."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class SetupCommandTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='re4 commands ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copy2(ROOT / 'Makefile', self.root / 'Makefile')
        self.script('re4pc.sh', 'printf "%s\\n" "$@"\n')

    def script(self, name, body):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/bash\nset -eu\n' + body)
        path.chmod(0o755)
        return path

    def make(self, *args):
        return subprocess.run(['make', '--silent', *args], cwd=self.root,
                              capture_output=True, text=True)

    def test_import_preserves_literal_apk_path_and_requires_a_path(self):
        apk = '/tmp/game with spaces \' "$`$(touch injected);.apk'
        result = self.make('import', 'APK=' + apk, 'ARGS=--output "/tmp/game data"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ['import', apk, '--output', '/tmp/game data'])
        self.assertFalse((self.root / 'injected').exists())
        result = self.make('import')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Usage: make import APK=', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_make_dispatches_launcher_and_cli_commands(self):
        for target, options, expected in (
                ('play', [], ['launcher']),
                ('launcher', ['ARGS=--game "/custom game"'], ['launcher', '--game', '/custom game']),
                ('cli', ['ARGS=--help'], ['--help']),
                ('run', ['ARGS=--language es'], ['run', '--language', 'es']),
                ('check-game', [], ['check']),
                ('settings', [], ['settings']),
                ('backup', [], ['backup']),
                ('backups', [], ['backups'])):
            with self.subTest(target=target):
                result = self.make(target, *options)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), expected)

    def test_install_finishes_setup_before_installing_even_with_parallel_make(self):
        self.script('setup.sh', 'touch prepared\n')
        installer = self.root / 'tools/install_desktop.py'
        installer.parent.mkdir()
        installer.write_text('from pathlib import Path\nimport json, sys\n'
                             'assert Path("prepared").is_file()\n'
                             'print(json.dumps(sys.argv[1:]))\n')
        result = self.make('-j4', 'install', 'PYTHON=' + sys.executable,
                           'DESKTOP_ARGS=--game "/custom game"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ['--game', '/custom game'])
        result = self.make('uninstall', 'PYTHON=' + sys.executable)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ['--uninstall'])

    def test_setup_reports_all_missing_prerequisites_before_creating_environment(self):
        shutil.copy2(ROOT / 'setup.sh', self.root / 'setup.sh')
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'dirname').symlink_to(shutil.which('dirname'))
        self.script('bin/uname', 'if [ "$1" = -s ]; then echo Linux; else echo x86_64; fi\n')
        self.script('bin/pkg-config', 'exit 1\n')
        self.script('bin/python3', 'case "$*" in *sys.version_info*) exit 0;; *) exit 1;; esac\n')
        result = subprocess.run(['/bin/bash', str(self.root / 'setup.sh')], cwd='/',
                                env=dict(os.environ, PATH=str(bin_dir)), capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        for dependency in ('cc', 'ffmpeg', 'SDL2 development headers', 'Python/Tk', 'Python venv/ensurepip'):
            self.assertIn(dependency, result.stderr)
        self.assertIn('make install', result.stderr)
        self.assertFalse((self.root / '.venv').exists())
