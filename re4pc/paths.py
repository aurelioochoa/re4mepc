"""User-owned data and test artifacts, independent of the checkout directory."""
import os
import shutil
import sys
import tempfile
from pathlib import Path


def _native_home(variable):
    """Windows/macOS equivalent of an XDG base directory, or None on Linux."""
    if sys.platform == 'win32':
        name = 'APPDATA' if variable == 'XDG_CONFIG_HOME' else 'LOCALAPPDATA'
        value = os.environ.get(name)
        root = Path(value) if value and Path(value).is_absolute() else Path.home() / 'AppData' / (
            'Roaming' if name == 'APPDATA' else 'Local')
        return root / 'cache' if variable == 'XDG_CACHE_HOME' else root
    if sys.platform == 'darwin':
        library = Path.home() / 'Library'
        return library / ('Caches' if variable == 'XDG_CACHE_HOME' else 'Application Support')
    return None


def xdg_home(variable, fallback):
    value = os.environ.get(variable)
    # XDG paths must be absolute; never put default data in the checkout.
    if value and Path(value).is_absolute():
        return Path(value)
    return _native_home(variable) or Path.home() / fallback


def game_dir():
    return xdg_home('XDG_DATA_HOME', '.local/share') / 're4mepc/game'


def logs_dir():
    return xdg_home('XDG_STATE_HOME', '.local/state') / 're4mepc/logs'


def test_output(name, explicit=None):
    if explicit is not None:
        output = Path(explicit).absolute()
        output.mkdir(parents=True, exist_ok=True)
        return output
    parent = logs_dir() / name
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="run-", dir=parent))


def isolated_game(source, output):
    """Copy only inputs into a new per-run fixture with fresh saves.

    Real copies avoid linking writable files back to the user's installation.
    Every invocation gets a new directory, including interrupted/repeated tests.
    """
    from .assets import validate
    source = validate(source).resolve()
    output = Path(output).resolve()
    if output == source or source in output.parents:
        raise ValueError('Test output must be outside the source game directory')
    output.mkdir(parents=True, exist_ok=True)
    fixture = Path(tempfile.mkdtemp(prefix='game-', dir=output))
    try:
        for folder in ('lib', 'data'):
            shutil.copytree(source / folder, fixture / folder)
        (fixture / 'saves').mkdir()
    except BaseException:
        shutil.rmtree(fixture)
        raise
    return fixture


def native_dir():
    return Path(__file__).resolve().parent.parent / 'build'


def platform_library(name):
    """Map a Linux helper name (libre4fast.so) to this host's file name."""
    stem = name[3:-3] if name.startswith('lib') and name.endswith('.so') else name
    if sys.platform == 'win32':
        return stem + '.dll'
    if sys.platform == 'darwin':
        return 'lib' + stem + '.dylib'
    return 'lib' + stem + '.so'


def native_library(name):
    """Resolve helpers beside application code in source and staged releases."""
    if name not in ('libre4audio.so', 'libre4fast.so', 'libre4math.so'):
        raise ValueError('Unknown native helper')
    return native_dir() / platform_library(name)


def quiet_process():
    """Popen options that keep helper processes from opening console windows."""
    if sys.platform == 'win32':
        import subprocess
        return {'creationflags': subprocess.CREATE_NO_WINDOW}
    return {}


def ffmpeg_binary():
    """Prefer the bundled decoder while leaving source installs on PATH."""
    application = Path(__file__).resolve().parent.parent
    bundled = application.parent.parent / 'bin/ffmpeg'
    packaged = application.parent.name == 'lib' and application.parent.parent.name == 'usr'
    if packaged and bundled.is_file():
        return str(bundled)
    # Windows/macOS bundles keep ffmpeg beside the native helpers.
    beside = native_dir() / ('ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg')
    return str(beside) if beside.is_file() else 'ffmpeg'
