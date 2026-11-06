"""Build and atomically publish desktop helpers without truncating live libraries.

Linux, macOS and Windows (MinGW-w64 gcc) produce the same three helpers with
the host's library naming (see re4pc.paths.platform_library). The helpers call
Unicorn through pointers bound at runtime (native/uc_api.h), so they never link
a second copy of it.

SDL2 comes from pkg-config, or from RE4PC_SDL2_INCLUDE (the directory holding
SDL.h) plus RE4PC_SDL2_LIBRARY (the .dll/.dylib to link). With the latter, the
library is copied beside the helpers so portable builds load one SDL2.
"""
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from re4pc.paths import platform_library  # noqa: E402

WARNINGS = ['-O2', '-Wall', '-Wextra', '-Werror']


def _sdl(stage, platform):
    """Compiler flags for SDL2 and the bundled library name, if any."""
    include, library = os.environ.get('RE4PC_SDL2_INCLUDE'), os.environ.get('RE4PC_SDL2_LIBRARY')
    if include and library:
        source = Path(library)
        if platform == 'win32':
            bundled = stage/'SDL2.dll'
            shutil.copy2(source, bundled)
            return ['-I'+include, '-DSDL_MAIN_HANDLED', str(bundled)], bundled.name
        bundled = stage/'libSDL2-2.0.0.dylib'
        shutil.copy2(source, bundled)
        os.chmod(bundled, 0o755)
        # Resolve beside the helper that loads it, wherever the bundle lives.
        subprocess.run(['install_name_tool', '-id', '@loader_path/libSDL2-2.0.0.dylib', str(bundled)], check=True)
        # install_name_tool invalidates the signature arm64 requires.
        subprocess.run(['codesign', '--force', '--sign', '-', str(bundled)], check=True)
        return ['-I'+include, str(bundled)], bundled.name
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'sdl2'], text=True))
    return flags + (['-DSDL_MAIN_HANDLED'] if platform == 'win32' else []), None


def build(root=None, package=None, platform=None):
    root = Path(root or ROOT)
    platform = platform or sys.platform
    del package  # Unicorn is no longer linked; kept for callers' signature.
    out = root/'build'
    out.mkdir(exist_ok=True)
    name = lambda helper: _name(helper, platform)
    compiler = os.environ.get('CC', 'gcc' if platform == 'win32' else 'cc')
    shared = ['-shared'] + ([] if platform == 'win32' else ['-fPIC'])
    if platform == 'win32':
        # Self-contained DLLs: no libgcc/winpthread runtime DLLs to ship.
        gl = ['-lopengl32', '-static-libgcc', '-Wl,-Bstatic', '-lwinpthread', '-Wl,-Bdynamic']
    elif platform == 'darwin':
        gl = ['-framework', 'OpenGL']
    else:
        gl = ['-lGL', '-lm', '-pthread']
    # A game may have these libraries mapped while make verify runs. Build all
    # candidates first, then replace directory entries; existing mappings keep
    # their original inode and never observe a truncated library.
    with tempfile.TemporaryDirectory(prefix='.native-', dir=out) as temporary:
        stage = Path(temporary)
        sdl, bundled = _sdl(stage, platform)
        rpath = ['-Wl,-rpath,@loader_path'] if platform == 'darwin' and bundled else []
        subprocess.run([compiler, *shared, *WARNINGS, str(root/'native/audio.c'),
                        '-o', str(stage/name('libre4audio.so')), *sdl, *rpath], check=True)
        subprocess.run([compiler, *shared, *WARNINGS,
                        str(root/'native/fast.c'), str(root/'native/render.c'), str(root/'native/gl.c'),
                        str(root/'native/display.c'), '-o', str(stage/name('libre4fast.so')), *gl], check=True)
        # Rust math helpers have no dependencies, so the build never needs a network.
        subprocess.run(['cargo', 'build', '--release', '--locked', '--offline', '--quiet',
                        '--manifest-path', str(root/'native/Cargo.toml'), '--target-dir', str(stage/'cargo')], check=True)
        shutil.copy2(stage/'cargo/release'/name('libre4math.so'), stage/name('libre4math.so'))
        names = [name(helper) for helper in ('libre4audio.so', 'libre4fast.so', 'libre4math.so')]
        if bundled:
            names.append(bundled)
        for item in names:
            with (stage/item).open('rb') as stream:
                os.fsync(stream.fileno())
            os.replace(stage/item, out/item)
    print('Built native audio, ARM import and math helpers')


def _name(helper, platform):
    if platform == sys.platform:
        return platform_library(helper)
    stem = helper[3:-3]
    return {'win32': stem + '.dll', 'darwin': 'lib' + stem + '.dylib'}.get(platform, helper)


if __name__ == '__main__':
    build()
