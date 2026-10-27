"""User-owned data and test artifacts, independent of the checkout directory."""
import os
import shutil
import tempfile
from pathlib import Path


def xdg_home(variable, fallback):
    value = os.environ.get(variable)
    # XDG paths must be absolute; never put default data in the checkout.
    if value and Path(value).is_absolute():
        return Path(value)
    return Path.home() / fallback


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


def native_library(name):
    """Resolve helpers beside application code in source and staged releases."""
    if name not in ('libre4audio.so', 'libre4fast.so', 'libre4math.so'):
        raise ValueError('Unknown native helper')
    return Path(__file__).resolve().parent.parent / 'build' / name


def ffmpeg_binary():
    """Prefer the bundled decoder while leaving source installs on PATH."""
    application = Path(__file__).resolve().parent.parent
    bundled = application.parent.parent / 'bin/ffmpeg'
    packaged = application.parent.name == 'lib' and application.parent.parent.name == 'usr'
    return str(bundled) if packaged and bundled.is_file() else 'ffmpeg'
