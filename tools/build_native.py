"""Build and atomically publish desktop helpers without truncating live libraries."""
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
import unicorn


def build(root=None, package=None):
    root = Path(root or Path(__file__).resolve().parent.parent)
    package = Path(package or Path(unicorn.__file__).parent)
    out = root/'build'
    out.mkdir(exist_ok=True)
    flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','sdl2'],text=True))
    # A game may have these libraries mapped while make verify runs. Build all
    # candidates first, then replace directory entries; existing mappings keep
    # their original inode and never observe a truncated library.
    with tempfile.TemporaryDirectory(prefix='.native-', dir=out) as temporary:
        stage = Path(temporary)
        subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
                        str(root/'native/audio.c'),'-o',str(stage/'libre4audio.so'),*flags],check=True)
        subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
                        str(root/'native/fast.c'),str(root/'native/render.c'),str(root/'native/gl.c'),'-o',str(stage/'libre4fast.so'),
                        '-I'+str(package/'include'),'-L'+str(package/'lib'),
                        '-l:libunicorn.so.2','-lGL','-lm','-pthread','-Wl,-rpath,$ORIGIN'],check=True)
        # Rust math helpers have no dependencies, so the build never needs a network.
        subprocess.run(['cargo','build','--release','--locked','--offline','--quiet',
                        '--manifest-path',str(root/'native/Cargo.toml'),'--target-dir',str(stage/'cargo')],check=True)
        shutil.copy2(stage/'cargo/release/libre4math.so',stage/'libre4math.so')
        shutil.copy2(package/'lib/libunicorn.so.2',stage/'libunicorn.so.2')
        for name in ('libre4audio.so','libre4fast.so','libre4math.so','libunicorn.so.2'):
            with (stage/name).open('rb') as stream:
                os.fsync(stream.fileno())
            os.replace(stage/name, out/name)
    print('Built native audio, ARM import and math helpers')


if __name__ == '__main__':
    build()
