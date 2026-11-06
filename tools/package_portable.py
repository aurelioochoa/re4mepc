#!/usr/bin/env python3
"""Build the portable Windows x64 and macOS releases on their own hosts.

Run on the target OS with a relocatable CPython (python-build-standalone, e.g.
from `uv python install`). The archive bundles that Python, the pinned wheels,
the allowlisted application, the native helpers, SDL2 and FFmpeg. No engine
data is included: users import their own APK exactly as on Linux.

  Windows:  re4mepc-<version>-windows-x64.zip
            re4mepc/re4mepc.exe (launcher), re4mepc/re4mepc-cli.exe (CLI)
  macOS:    re4mepc-<version>-macos-<arch>.zip
            Resident Evil 4 Mobile.app (ad-hoc signed, not notarized)
"""
import argparse
import hashlib
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from re4pc.packaging import (APPLICATION_ASSETS, APPLICATION_FILES, APPLICATION_MODULES,  # noqa: E402
                             FORBIDDEN_DIGESTS, FORBIDDEN_SUFFIXES)
from re4pc.paths import platform_library  # noqa: E402

APP_NAME = 'Resident Evil 4 Mobile'
BUNDLE_ID = 'io.github.aurelioochoa.re4mepc'
HELPERS = ('libre4audio.so', 'libre4fast.so', 'libre4math.so')
SMOKE = ('import tkinter, unicorn, keystone, capstone, PIL, elftools; '
         'tkinter.Tcl().eval("info patchlevel"); '
         'from re4pc import native_libs; from re4pc.arm import ArmRuntime; '
         'native_libs.sdl(); native_libs.fast(); native_libs.math(); native_libs.audio(); '
         'arm = ArmRuntime(); print("guest", hex(arm.base), "translated", arm.memory.translated); arm.close(); '
         'print("STAGED_RUNTIME_PASS")')


def run(command, **kwargs):
    print('+', ' '.join(map(str, command)), flush=True)
    return subprocess.run(command, check=True, **kwargs)


def python_home(executable):
    executable = Path(executable).resolve()
    return executable.parent if sys.platform == 'win32' else executable.parent.parent


def copy_python(home, target):
    ignore = shutil.ignore_patterns('__pycache__', 'test', 'tests', 'idlelib', 'turtledemo', '*.pdb',
                                    'EXTERNALLY-MANAGED')
    shutil.copytree(home, target, ignore=ignore, symlinks=True)
    return target / ('python.exe' if sys.platform == 'win32' else 'bin/python3')


def copy_application(app):
    (app / 're4pc/ui_assets').mkdir(parents=True)
    for name in APPLICATION_MODULES:
        shutil.copy2(ROOT / 're4pc' / name, app / 're4pc' / name)
    for name in APPLICATION_ASSETS:
        shutil.copy2(ROOT / 're4pc/ui_assets' / name, app / 're4pc/ui_assets' / name)
    for name in APPLICATION_FILES:
        shutil.copy2(ROOT / name, app / name)
    build = app / 'build'
    build.mkdir()
    for name in HELPERS:
        shutil.copy2(ROOT / 'build' / platform_library(name), build / platform_library(name))
    sdl = 'SDL2.dll' if sys.platform == 'win32' else 'libSDL2-2.0.0.dylib'
    if not (ROOT / 'build' / sdl).is_file():
        raise SystemExit(f'build/{sdl} is missing: build with RE4PC_SDL2_INCLUDE/RE4PC_SDL2_LIBRARY set')
    shutil.copy2(ROOT / 'build' / sdl, build / sdl)
    return build


def audit(stage):
    """Reject game data the same way the Linux package audit does."""
    records = {}
    for path in sorted(stage.rglob('*')):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(stage).as_posix()
        if path.suffix.lower() in FORBIDDEN_SUFFIXES and 'python' not in Path(relative).parts:
            raise SystemExit('Forbidden release content: ' + relative)
        if path.name in ('libbio4af.so', 'libmc_eruption_for_android_jni.so', 'import.json'):
            raise SystemExit('Imported game content in release: ' + relative)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in FORBIDDEN_DIGESTS:
            raise SystemExit('Imported engine bytes in release: ' + relative)
        records[relative] = {'bytes': path.stat().st_size, 'sha256': digest}
    return records


def install_requirements(python):
    environment = {**os.environ, 'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'CMAKE_POLICY_VERSION_MINIMUM': '3.5'}
    run([str(python), '-m', 'pip', 'install', '--no-cache-dir', '--no-warn-script-location',
         '--break-system-packages', '-r', str(ROOT / 'requirements.txt')], env=environment)


def smoke(python, app):
    environment = {**os.environ, 'PYTHONPATH': str(app), 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    environment.pop('PYTHONHOME', None)
    run([str(python), '-c', SMOKE], env=environment, cwd=tempfile.gettempdir())
    run([str(python), '-m', 're4pc', '--help'], env=environment, cwd=tempfile.gettempdir(),
        stdout=subprocess.DEVNULL)


def compile_bytecode(python, *folders):
    # Read-only installs (Program Files, /Applications) still start quickly.
    run([str(python), '-m', 'compileall', '-q', '-j', '0', *map(str, folders)])


def write_notes(folder, version, target):
    readme = f'''Resident Evil 4 Mobile PC Port (re4mepc) {version} — {target}

Experimental build. It contains no game data: import your own compatible APK
from the launcher (Import APK). Full campaign playability is unverified.

Windows: run re4mepc.exe for the launcher. re4mepc-cli.exe accepts the same
commands as the Linux CLI, e.g.  re4mepc-cli.exe import "C:\\path\\game.apk"
macOS: open "{APP_NAME}.app". The build is ad-hoc signed and not notarized:
the first time, right-click the app and choose Open, or run
  xattr -dr com.apple.quarantine "{APP_NAME}.app"
CLI:  "{APP_NAME}.app/Contents/MacOS/re4mepc" --help

Bundled: CPython (PSF license), unicorn, capstone, keystone-engine, pyelftools,
Pillow (see their licenses in the Python site-packages), SDL2 (zlib license)
and FFmpeg (GPL build from imageio-ffmpeg). Project license: LICENSE.
Source: https://github.com/aurelioochoa/re4mepc
'''
    (folder / 'README.txt').write_text(readme, encoding='utf-8')


def build_windows_launchers(stage, work):
    from PIL import Image
    icon = work / 're4mepc.ico'
    with Image.open(ROOT / 're4pc/ui_assets/icon.png') as source:
        source.convert('RGBA').save(icon, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    resource = work / 'launcher.rc'
    resource.write_text(f'1 ICON "{icon.as_posix()}"\n', encoding='utf-8')
    compiled = work / 'launcher.res.o'
    run(['windres', str(resource), '-O', 'coff', '-o', str(compiled)])
    common = ['gcc', '-O2', '-Wall', '-Wextra', '-Werror', '-municode', '-static', str(ROOT / 'native/launcher_win.c'),
              str(compiled)]
    run([*common, '-mwindows', '-o', str(stage / 're4mepc.exe')])
    run([*common, '-DRE4_CONSOLE=1', '-o', str(stage / 're4mepc-cli.exe')])


def package_windows(args, work):
    stage = work / 're4mepc'
    runtime = stage / 'runtime'
    python = copy_python(python_home(args.python), runtime / 'python')
    install_requirements(python)
    app = runtime / 'app'
    build = copy_application(app)
    shutil.copy2(args.ffmpeg, build / 'ffmpeg.exe')
    smoke(python, app)
    compile_bytecode(python, app, runtime / 'python/Lib')
    build_windows_launchers(stage, work)
    run([str(stage / 're4mepc-cli.exe'), '--help'], stdout=subprocess.DEVNULL)
    write_notes(stage, args.version, 'Windows x64')
    return stage, f're4mepc-{args.version}-windows-x64.zip'


def macho(path):
    with path.open('rb') as stream:
        return stream.read(4) in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe')


def make_icns(png, target, work):
    iconset = work / 're4mepc.iconset'
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            name = f'icon_{size}x{size}{"@2x" if scale == 2 else ""}.png'
            run(['sips', '-z', str(size*scale), str(size*scale), str(png), '--out', str(iconset / name)],
                stdout=subprocess.DEVNULL)
    run(['iconutil', '-c', 'icns', str(iconset), '-o', str(target)])


def package_macos(args, work):
    bundle = work / f'{APP_NAME}.app'
    contents = bundle / 'Contents'
    resources = contents / 'Resources'
    (contents / 'MacOS').mkdir(parents=True)
    resources.mkdir()
    python = copy_python(python_home(args.python), resources / 'python')
    install_requirements(python)
    keystone = os.environ.get('RE4PC_KEYSTONE_LIBRARY')
    if keystone:  # see the arm64 note in .github/workflows/portable.yml
        for package in resources.glob('python/lib/python3*/site-packages/keystone'):
            shutil.copy2(keystone, package / 'libkeystone.dylib')
            (package / 'libkeystone.dylib').chmod(0o755)
    app = resources / 'app'
    build = copy_application(app)
    shutil.copy2(args.ffmpeg, build / 'ffmpeg')
    (build / 'ffmpeg').chmod(0o755)
    smoke(python, app)
    compile_bytecode(python, app, *resources.glob('python/lib/python3*'))
    launcher = contents / 'MacOS/re4mepc'
    launcher.write_text('''#!/bin/sh
# Runs the bundled Python on the bundled application; arguments pass through.
RESOURCES=$(CDPATH= cd -- "$(dirname -- "$0")/../Resources" && pwd)
export PYTHONPATH="$RESOURCES/app"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONHOME
# Finder may append a process serial number on older macOS releases.
if [ "$#" -gt 0 ] && [ "${1#-psn_}" != "$1" ]; then shift; fi
if [ "$#" -eq 0 ]; then set -- launcher; fi
exec "$RESOURCES/python/bin/python3" -u -m re4pc "$@"
''')
    launcher.chmod(0o755)
    make_icns(ROOT / 're4pc/ui_assets/icon.png', resources / 're4mepc.icns', work)
    with (contents / 'Info.plist').open('wb') as stream:
        plistlib.dump({'CFBundleName': APP_NAME, 'CFBundleDisplayName': APP_NAME,
                       'CFBundleIdentifier': BUNDLE_ID, 'CFBundleExecutable': 're4mepc',
                       'CFBundleIconFile': 're4mepc', 'CFBundlePackageType': 'APPL',
                       'CFBundleShortVersionString': args.version.split('-')[0].lstrip('v'),
                       'CFBundleVersion': args.version, 'LSMinimumSystemVersion': '11.0',
                       'NSHighResolutionCapable': True, 'LSApplicationCategoryType': 'public.app-category.games'},
                      stream)
    run([str(launcher), '--help'], stdout=subprocess.DEVNULL)
    # Every arm64 Mach-O must carry a valid signature; install_name_tool and
    # some pip-built extensions invalidate or lack one. codesign --deep does
    # not reach code under Resources, so sign each binary, then the bundle.
    for path in sorted(bundle.rglob('*')):
        if path.is_file() and not path.is_symlink() and macho(path):
            run(['codesign', '--force', '--sign', '-', str(path)], stdout=subprocess.DEVNULL)
    run(['codesign', '--force', '--sign', '-', str(bundle)])
    run(['codesign', '--verify', '--deep', '--strict', str(bundle)])
    folder = work / 'release'
    folder.mkdir()
    shutil.move(str(bundle), folder / bundle.name)
    write_notes(folder, args.version, f'macOS {args.arch}')
    return folder, f're4mepc-{args.version}-macos-{args.arch}.zip'


def archive(stage, name, output):
    output.mkdir(parents=True, exist_ok=True)
    target = output / name
    if sys.platform == 'darwin':
        # ditto keeps symlinks, permissions and code signatures intact.
        run(['ditto', '-c', '-k', '--sequesterRsrc', str(stage), str(target)])
    else:
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for path in sorted(stage.rglob('*')):
                if path.is_file():
                    bundle.write(path, Path(stage.name) / path.relative_to(stage))
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--python', required=True, help='Relocatable CPython executable to bundle')
    parser.add_argument('--ffmpeg', required=True, help='Static FFmpeg executable to bundle')
    parser.add_argument('--version', required=True)
    parser.add_argument('--arch', default=platform.machine().lower().replace('x86_64', 'x64').replace('amd64', 'x64'))
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    if sys.platform not in ('win32', 'darwin'):
        parser.error('Use tools/package.py (make package) for Linux releases')
    with tempfile.TemporaryDirectory(prefix='re4mepc-package-') as temporary:
        work = Path(temporary)
        stage, name = (package_windows if sys.platform == 'win32' else package_macos)(args, work)
        records = audit(stage)
        info = {'version': args.version, 'target': name, 'python': subprocess.check_output(
                    [str(args.python), '-c', 'import sys; print(sys.version)'], text=True).strip(),
                'requirements_sha256': hashlib.sha256((ROOT / 'requirements.txt').read_bytes()).hexdigest(),
                'engine_included': False, 'files': len(records)}
        (stage / 'BUILD.json').write_text(json.dumps(info, indent=2) + '\n')
        target = archive(stage, name, args.output)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f'{digest}  {target.name}')
    print('PORTABLE_PACKAGE_PASS', target)


if __name__ == '__main__':
    main()
