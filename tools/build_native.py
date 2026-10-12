"""Build native desktop helpers against the installed SDL and Unicorn headers."""
import shlex
import shutil
import subprocess
from pathlib import Path
import unicorn

root=Path(__file__).resolve().parent.parent
out=root/'build';out.mkdir(exist_ok=True)
flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','sdl2'],text=True))
subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',str(root/'native/audio.c'),'-o',str(out/'libre4audio.so'),*flags],check=True)
package=Path(unicorn.__file__).parent
subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',str(root/'native/fast.c'),
    '-o',str(out/'libre4fast.so'),'-I'+str(package/'include'),'-L'+str(package/'lib'),
    '-l:libunicorn.so.2','-Wl,-rpath,$ORIGIN'],check=True)
shutil.copy2(package/'lib/libunicorn.so.2',out/'libunicorn.so.2')
print('Built native audio and ARM import helpers')
