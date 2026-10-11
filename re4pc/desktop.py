"""Install a per-user Linux executable and desktop entry, without game bundles."""
import argparse
import io
import os
import shlex
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

from PIL import Image

from .paths import game_dir, logs_dir, xdg_home

APP_ID = 're4mepc'
MAX_ICON_BYTES = 8 * 1024 * 1024
ICON_NAMES = {'icon', 'ic_launcher', 'ic_launcher_round', 'app_icon', 'launcher_icon'}


def inspect_icon(data):
    """Accept actual PNGs, copying their original bytes without changing artwork."""
    if len(data) > MAX_ICON_BYTES:
        raise ValueError('Icon exceeds 8 MiB')
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'PNG' or not (1 <= image.width <= 4096 and 1 <= image.height <= 4096):
            raise ValueError('Use a PNG icon with dimensions up to 4096 x 4096')
        size = image.width * image.height
        image.verify()
    return size


def apk_icon(apk):
    """Find the largest conventional launcher PNG; never extract archive paths."""
    with zipfile.ZipFile(apk) as archive:
        candidates = []
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            if (len(path.parts) != 3 or path.parts[0] != 'res'
                    or not path.parts[1].startswith(('drawable', 'mipmap'))
                    or path.suffix.lower() != '.png' or path.stem not in ICON_NAMES
                    or info.file_size > MAX_ICON_BYTES):
                continue
            data = archive.read(info)
            try:
                size = inspect_icon(data)
            except (ValueError, OSError, Image.DecompressionBombError):
                continue
            candidates.append((size, info.filename, data))
        if not candidates:
            raise ValueError('No conventional launcher PNG found in APK; use --icon /path/to/icon.png')
        return max(candidates, key=lambda item: (item[0], item[1]))[2]


def entry_value(value):
    """Escape desktop-entry string values (not shell strings)."""
    return str(value).replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')


def exec_value(path):
    # Exec has its own quoting rules before desktop-entry backslashes are read.
    value = str(path).replace('%', '%%')
    for character in ('\\', '"', '`', '$'):
        value = value.replace(character, '\\' + character)
    return entry_value('"' + value + '"')


def desktop_folder():
    """Respect localized XDG desktop directories; don't invent ~/Desktop."""
    if shutil.which('xdg-user-dir'):
        result = subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True, text=True, check=True)
        folder = Path(result.stdout.strip())
    else:
        folder = Path.home() / 'Desktop'
    if not folder.is_absolute() or folder == Path.home() or not folder.is_dir():
        raise ValueError('No desktop directory configured; the applications-menu entry is still available without --desktop')
    return folder


def locations():
    data = xdg_home('XDG_DATA_HOME', '.local/share')
    return (Path.home() / '.local/bin' / APP_ID,
            data / 'applications' / (APP_ID + '.desktop'),
            data / APP_ID / 'icons' / (APP_ID + '.png'))


def install(root, *, icon=None, apk=None, game=None, desktop=None):
    root = Path(root).resolve()
    launcher, entry, installed_icon = locations()
    required = (root / 're4pc.sh', root / '.venv/bin/python',
                root / 'build/libre4audio.so', root / 'build/libre4fast.so')
    if not all(path.is_file() for path in required):
        raise ValueError('Run ./setup.sh first to create the Python environment and native helpers')
    if not os.access(required[0], os.X_OK) or not os.access(required[1], os.X_OK):
        raise ValueError('The project launcher and Python interpreter must be executable')
    if icon is not None:
        data = Path(icon).read_bytes()
    elif apk is not None:
        data = apk_icon(apk)
    elif installed_icon.is_file():
        data = installed_icon.read_bytes()
    else:
        raise ValueError('Choose an icon with --apk /path/to/game.apk or --icon /path/to/icon.png')
    inspect_icon(data)
    game = Path(game).resolve() if game is not None else game_dir()
    log_file = logs_dir() / 'desktop.log'
    # All inputs and optional destinations are checked before installing files.
    if desktop is not None and not Path(desktop).is_dir():
        raise ValueError('Desktop destination must be an existing directory')
    wrapper = '#!/bin/sh\n' + 'exec ' + shlex.join([
        str(root / 're4pc.sh'), 'run', '--game', str(game), '--log-file', str(log_file)
    ]) + ' "$@"\n'
    contents = '\n'.join([
        '[Desktop Entry]', 'Version=1.0', 'Type=Application',
        'Name=Resident Evil 4 Mobile',
        'Comment=Play Resident Evil 4 Mobile with mouse and keyboard on Linux',
        'Exec=' + exec_value(launcher), 'TryExec=' + entry_value(launcher),
        'Icon=' + entry_value(installed_icon), 'Terminal=true',
        'Categories=Game;', 'Keywords=Resident Evil;RE4;Mobile;',
        'StartupNotify=false', '',
    ])
    for path in (launcher, entry, installed_icon):
        path.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    installed_icon.write_bytes(data)
    launcher.write_text(wrapper, encoding='utf-8')
    launcher.chmod(0o755)
    entry.write_text(contents, encoding='utf-8')
    entry.chmod(0o644)
    if desktop is not None:
        shortcut = Path(desktop) / entry.name
        shortcut.write_text(contents, encoding='utf-8')
        shortcut.chmod(0o755)
    return launcher, entry, installed_icon


def uninstall(desktop=None):
    paths = list(locations())
    if desktop is not None:
        paths.append(Path(desktop) / (APP_ID + '.desktop'))
    for path in paths:
        path.unlink(missing_ok=True)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    icons = parser.add_mutually_exclusive_group()
    icons.add_argument('--icon', type=Path, help='Use an existing PNG, such as the supplied cover image')
    icons.add_argument('--apk', type=Path, help='Read the largest conventional launcher icon from your APK')
    parser.add_argument('--game', type=Path, help='Use game data imported into a custom directory')
    parser.add_argument('--desktop', action='store_true', help='Also create/remove a shortcut in your XDG desktop directory')
    parser.add_argument('--uninstall', action='store_true', help='Remove launchers and local icon; preserve checkout, game and saves')
    args = parser.parse_args()
    try:
        folder = desktop_folder() if args.desktop else None
        if args.uninstall:
            for path in uninstall(folder):
                print('Removed:', path)
        else:
            root = Path(__file__).resolve().parent.parent
            for path in install(root, icon=args.icon, apk=args.apk, game=args.game, desktop=folder):
                print('Installed:', path)
            if folder is not None:
                print('Desktop shortcut:', folder / (APP_ID + '.desktop'))
                print('If your desktop asks, choose Allow Launching / Trust this launcher.')
            print('Launch Resident Evil 4 Mobile from your applications menu, or ~/.local/bin/re4mepc.')
    except (ValueError, RuntimeError, OSError, zipfile.BadZipFile,
            Image.DecompressionBombError, subprocess.CalledProcessError) as error:
        print('Desktop setup:', error, file=sys.stderr)
        return 1
    return 0
