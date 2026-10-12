#!/usr/bin/env python3
"""Build Ubuntu 22.04-baseline portable/AppImage releases from the same stage.

The Docker builder owns toolchain installation. No engine data is copied. Runtime
is Python/Tk plus pinned Python wheels, SDL2/FFmpeg and their non-driver libraries.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from re4pc.packaging import APPLICATION_ASSETS, APPLICATION_FILES, APPLICATION_MODULES, NATIVE_INPUTS, write_manifest, verify_manifest

# Driver loaders and glibc always come from the host. Bundling old libstdc++ also
# prevents modern host Mesa drivers from loading, so use the desktop host copy.
HOST_LIBS = {'libc.so.6', 'libm.so.6', 'libdl.so.2', 'libpthread.so.0', 'librt.so.1',
             'libresolv.so.2', 'libutil.so.1', 'libanl.so.1', 'ld-linux-x86-64.so.2',
             'libGL.so.1', 'libEGL.so.1', 'libGLX.so.0', 'libGLdispatch.so.0',
             'libOpenGL.so.0', 'libGLESv2.so.2', 'libglapi.so.0',
             'libdrm.so.2', 'libdrm_amdgpu.so.1', 'libdrm_intel.so.1',
             'libdrm_nouveau.so.2', 'libdrm_radeon.so.1', 'libgbm.so.1',
             'libstdc++.so.6', 'libgcc_s.so.1'}
APPIMAGE_TOOL = 'https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage'
APPIMAGE_TOOL_SHA256 = '95cbe7cce9717fce90c484e34052ee7c7f1d7635b33c12525b4776826a7d29b6'
APPIMAGE_RUNTIME = 'https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64'
APPIMAGE_RUNTIME_SHA256 = '156f4bdbde9c52d01814600013e0a273f0118dc2de98975f3c8c63427ec79074'
# Expected digests are independently published release-asset digests from GitHub.
# The continuous URLs may advance: fail closed rather than silently changing tools.


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def elf(path):
    try:
        with path.open('rb') as stream:
            return stream.read(4) == b'\x7fELF'
    except OSError:
        return False


def collect_libraries(stage):
    directory = stage / 'usr/lib/runtime'
    directory.mkdir(parents=True)
    pending = [p for p in stage.rglob('*') if p.is_file() and elf(p)]
    # Auditwheel dependencies may inherit RPATH from their parent extension;
    # ldd on each dependency separately needs all staged library directories.
    search = ':'.join(sorted({str(p.parent) for p in pending} | {str(directory)}))
    environment = {**os.environ, 'LD_LIBRARY_PATH': search}
    seen = set()
    while pending:
        path = pending.pop()
        if str(path) in seen:
            continue
        seen.add(str(path))
        result = subprocess.run(['ldd', str(path)], text=True, capture_output=True, env=environment)
        if 'not found' in result.stdout:
            raise RuntimeError('Missing staged dependency:\n' + result.stdout)
        for line in result.stdout.splitlines():
            words = line.split()
            source = next((Path(word) for word in words if word.startswith('/')), None)
            if source is None or source.name in HOST_LIBS:
                continue
            target = directory / source.name
            if not target.exists():
                shutil.copy2(source.resolve(), target)
                pending.append(target)
    return sorted(p.name for p in directory.iterdir())


def copy_application(source, application):
    """Copy only declared application code and generated launcher artwork."""
    source, application = Path(source), Path(application)
    (application / 're4pc/ui_assets').mkdir(parents=True, exist_ok=True)
    for name in APPLICATION_MODULES:
        shutil.copy2(source / 're4pc' / name, application / 're4pc' / name)
    for name in APPLICATION_ASSETS:
        shutil.copy2(source / 're4pc/ui_assets' / name, application / 're4pc/ui_assets' / name)
    for name in APPLICATION_FILES:
        shutil.copy2(source / name, application / name)


def stage_release(source, output):
    source, output = Path(source), Path(output)
    stage = output / 're4mepc.AppDir'
    if stage.exists():
        shutil.rmtree(stage)
    application = stage / 'usr/lib/re4mepc'
    application.mkdir(parents=True)
    copy_application(source, application)
    (application / 'native').mkdir()
    for name in NATIVE_INPUTS:
        shutil.copy2(source / 'native' / name, application / 'native' / name)
    (application / 'tools').mkdir()
    shutil.copy2(source / 'tools/build_native.py', application / 'tools/build_native.py')
    run([sys.executable, str(application / 'tools/build_native.py')])
    # Compiler inputs and build scripts are not required by the runtime.
    shutil.rmtree(application / 'native')
    shutil.rmtree(application / 'tools')
    binary = stage / 'usr/bin'
    binary.mkdir(parents=True)
    shutil.copy2('/usr/bin/python3.10', binary / 'python3')
    shutil.copy2('/usr/bin/ffmpeg', binary / 'ffmpeg')
    shutil.copy2('/usr/bin/ffprobe', binary / 'ffprobe')
    stdlib = stage / 'usr/lib/python3.10'
    shutil.copytree('/usr/lib/python3.10', stdlib, ignore=shutil.ignore_patterns('__pycache__', 'test', 'tests', 'idlelib', 'ensurepip', 'dist-packages'))
    # Debian's extension modules live under lib-dynload in this directory.
    shutil.copytree('/opt/re4venv/lib/python3.10/site-packages', stdlib / 'site-packages',
                    ignore=shutil.ignore_patterns('__pycache__', 'pip', 'pip-*', 'setuptools', 'setuptools-*', 'pkg_resources', '_distutils_hack', 'distutils-precedence.pth'))
    tk = stage / 'usr/share/tcltk'
    shutil.copytree('/usr/share/tcltk', tk)
    fonts = stage / 'usr/share/fonts/truetype/dejavu'
    fonts.mkdir(parents=True)
    for name in ('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSansMono.ttf', 'DejaVuSansMono-Bold.ttf',
                 'DejaVuSerif.ttf', 'DejaVuSerif-Bold.ttf'):
        shutil.copy2('/usr/share/fonts/truetype/dejavu/' + name, fonts / name)
    fontconfig = stage / 'usr/share/fontconfig'
    fontconfig.mkdir(parents=True)
    # Keep the bundled Fontconfig parser away from newer host configuration
    # syntax while permitting host fonts and bundling a legible fallback.
    (fontconfig / 'fonts.conf').write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir prefix="relative">../fonts</dir><dir>/usr/share/fonts</dir><dir>/usr/local/share/fonts</dir><dir prefix="xdg">fonts</dir><cachedir prefix="xdg">fontconfig</cachedir></fontconfig>\n')
    libraries = collect_libraries(stage)
    # Generated application artwork, never extracted game assets.
    shutil.copy2(application / 're4pc/ui_assets/icon.png', stage / 're4mepc.png')
    (stage / '.DirIcon').symlink_to('re4mepc.png')
    (stage / 're4mepc.desktop').write_text('[Desktop Entry]\nType=Application\nName=Resident Evil 4 Mobile\nExec=AppRun\nIcon=re4mepc\nCategories=Game;\nTerminal=false\n')
    (stage / 'AppRun').write_text('''#!/bin/sh
set -eu
RE4PC_APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONHOME="$RE4PC_APPDIR/usr"
export PYTHONPATH="$RE4PC_APPDIR/usr/lib/re4mepc:$RE4PC_APPDIR/usr/lib/python3.10/site-packages"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH="$RE4PC_APPDIR/usr/lib/runtime${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export TCL_LIBRARY="$RE4PC_APPDIR/usr/share/tcltk/tcl8.6"
export TK_LIBRARY="$RE4PC_APPDIR/usr/share/tcltk/tk8.6"
export FONTCONFIG_FILE="$RE4PC_APPDIR/usr/share/fontconfig/fonts.conf"
export PATH="$RE4PC_APPDIR/usr/bin:$PATH"
if [ "$#" -eq 0 ]; then set -- launcher; fi
exec "$RE4PC_APPDIR/usr/bin/python3" -u -m re4pc "$@"
''')
    (stage / 'AppRun').chmod(0o755)
    dpkg = subprocess.check_output(['dpkg-query', '-W', '-f=${Package}\t${Version}\t${License}\n'], text=True)
    (stage / 'DEPENDENCIES.txt').write_text('Runtime built on Ubuntu 22.04 x86_64. Python wheels pinned in requirements.txt.\nHost graphics drivers/loaders (including DRM and GBM), glibc, libstdc++ and libgcc are intentionally external.\n\nBuilder Debian packages (versions; full notices under usr/share/doc):\n' + dpkg + '\nBundled dependency libraries:\n' + '\n'.join(libraries) + '\n')
    notices = stage / 'usr/share/doc'
    shutil.copytree('/usr/share/doc', notices, ignore_dangling_symlinks=True, ignore=shutil.ignore_patterns('examples', 'html', '*.pdf'))
    tool = output / 'appimagetool-x86_64.AppImage'
    runtime = output / 'runtime-x86_64'
    for url, target, expected in ((APPIMAGE_TOOL, tool, APPIMAGE_TOOL_SHA256), (APPIMAGE_RUNTIME, runtime, APPIMAGE_RUNTIME_SHA256)):
        if not target.exists():
            urllib.request.urlretrieve(url, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Release tool checksum mismatch: ' + str(target))
        target.chmod(0o755)
    info = {'version': 1, 'baseline': 'Ubuntu 22.04 x86_64',
            'python': sys.version, 'appimagetool_url': APPIMAGE_TOOL,
            'appimagetool_sha256': APPIMAGE_TOOL_SHA256, 'runtime_sha256': APPIMAGE_RUNTIME_SHA256,
            'requirements_sha256': hashlib.sha256((source / 'requirements.txt').read_bytes()).hexdigest(),
            'engine_included': False}
    (stage / 'BUILD.json').write_text(json.dumps(info, indent=2) + '\n')
    write_manifest(stage)
    run([str(stage / 'AppRun'), '--help'])
    # Validate Tk import and all libraries using the staged Python in isolation.
    env = os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONHOME=str(stage / 'usr'), PYTHONPATH=str(application) + ':' + str(stdlib / 'site-packages'),
               LD_LIBRARY_PATH=str(stage / 'usr/lib/runtime'), TCL_LIBRARY=str(tk / 'tcl8.6'), TK_LIBRARY=str(tk / 'tk8.6'))
    run([str(binary / 'python3'), '-c', 'import tkinter,unicorn,capstone,PIL,elftools,ctypes; tkinter.Tcl().eval("info patchlevel"); ctypes.CDLL("libSDL2-2.0.so.0"); print("STAGED_RUNTIME_PASS")'], env=env)
    package_stage(stage, output)


def package_stage(stage, output):
    """Publish both formats from one verified stage, without rebuilding its runtime."""
    stage, output = Path(stage).resolve(), Path(output).resolve()
    verify_manifest(stage)
    tool, runtime = output/'appimagetool-x86_64.AppImage', output/'runtime-x86_64'
    for target, expected in ((tool, APPIMAGE_TOOL_SHA256), (runtime, APPIMAGE_RUNTIME_SHA256)):
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Release tool checksum mismatch: ' + str(target))
    portable = output / 're4mepc-linux-x86_64.tar.gz'
    temporary_portable = output / (portable.name + '.tmp')
    try:
        with tarfile.open(temporary_portable, 'w:gz') as archive:
            archive.add(stage, arcname='re4mepc', recursive=True)
        os.replace(temporary_portable, portable)
    finally:
        temporary_portable.unlink(missing_ok=True)
    # Extract the tool rather than requiring FUSE inside a builder container.
    with tempfile.TemporaryDirectory(prefix='appimagetool-') as temporary:
        run([str(tool), '--appimage-extract'], cwd=temporary, stdout=subprocess.DEVNULL)
        executable = Path(temporary) / 'squashfs-root/AppRun'
        appimage = output / 're4mepc-linux-x86_64.AppImage'
        temporary_appimage = output / (appimage.name + '.tmp')
        try:
            run([str(executable), '--runtime-file', str(runtime), str(stage), str(temporary_appimage)], env={**os.environ, 'ARCH': 'x86_64'})
            os.replace(temporary_appimage, appimage)
        finally:
            temporary_appimage.unlink(missing_ok=True)
    verify_manifest(stage)
    checksums = output / 'SHA256SUMS'
    temporary_checksums = output / '.SHA256SUMS.tmp'
    temporary_checksums.write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n' for path in (portable, appimage)))
    os.replace(temporary_checksums, checksums)
    print('PACKAGE_BUILD_PASS', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--stage', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--source', type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument('--builder', default='re4mepc-release-builder:ubuntu22.04')
    parser.add_argument('--repack', action='store_true', help='Publish an existing audited AppDir using cached release tools; does not refresh code or dependencies')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.repack:
        package_stage(output/'re4mepc.AppDir', output)
        return 0
    if args.stage:
        stage_release(args.source, output)
        return 0
    if sys.platform != 'linux' or os.uname().machine != 'x86_64':
        parser.error('Release builds require Linux x86_64 and Docker')
    if shutil.which('docker') is None:
        parser.error('Install Docker to build the Ubuntu 22.04 baseline runtime')
    with tempfile.TemporaryDirectory(prefix='re4-package-') as temporary:
        context = Path(temporary)
        shutil.copy2(ROOT / 'requirements.txt', context / 'requirements.txt')
        (context / 'Dockerfile').write_text('''FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends python3.10 python3.10-venv python3-tk python3-pip gcc pkg-config libsdl2-dev ffmpeg ca-certificates file desktop-file-utils libfuse2 && rm -rf /var/lib/apt/lists/*
RUN python3.10 -m venv /opt/re4venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/re4venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
''')
        run(['docker', 'build', '-t', args.builder, str(context)])
    # Mount the checkout read-only; writes are confined to declared output.
    run(['docker', 'run', '--rm', '--user', str(os.getuid()) + ':' + str(os.getgid()),
         '-v', str(ROOT) + ':/source:ro', '-v', str(output) + ':/output', args.builder,
         '/opt/re4venv/bin/python', '/source/tools/package.py', '--stage', '--source', '/source', '--output', '/output'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
