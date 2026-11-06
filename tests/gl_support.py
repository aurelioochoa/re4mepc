"""Skip real-OpenGL tests on Windows/macOS hosts without an offscreen context.

Linux always runs them (CI provides Mesa), so a Linux regression can never be
hidden as a skip. Windows and macOS CI runners have no GPU and SDL's offscreen
driver needs EGL there, so the probe usually fails and the tests are skipped.
"""
import functools
import os
import subprocess
import sys
import unittest
from pathlib import Path

PROBE = r'''
import ctypes as C, sys
from re4pc import native_libs
sdl = native_libs.sdl()
sdl.SDL_GetError.restype = C.c_char_p
sdl.SDL_CreateWindow.restype = C.c_void_p
sdl.SDL_CreateWindow.argtypes = (C.c_char_p,) + (C.c_int,) * 4 + (C.c_uint,)
sdl.SDL_GL_CreateContext.restype = C.c_void_p
sdl.SDL_GL_CreateContext.argtypes = (C.c_void_p,)
if sdl.SDL_Init(0x20):
    sys.exit(sdl.SDL_GetError().decode())
for attribute, value in ((17, 2), (18, 1), (21, 2)):
    sdl.SDL_GL_SetAttribute(attribute, value)
window = sdl.SDL_CreateWindow(b'probe', 0, 0, 64, 64, 2 | 8)
if not window or not sdl.SDL_GL_CreateContext(window):
    sys.exit(sdl.SDL_GetError().decode())
'''


@functools.lru_cache(maxsize=None)
def offscreen_gl_error():
    if sys.platform.startswith('linux'):
        return None
    root = Path(__file__).resolve().parent.parent
    environment = {**os.environ, 'SDL_VIDEODRIVER': 'offscreen', 'SDL_AUDIODRIVER': 'dummy',
                   'PYTHONPATH': str(root)}
    try:
        result = subprocess.run([sys.executable, '-c', PROBE], env=environment, capture_output=True,
                                text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        return str(error)
    return None if result.returncode == 0 else (result.stderr.strip().splitlines() or ['unknown error'])[-1]


def requires_offscreen_gl(test):
    """Class or method decorator: skip when no offscreen OpenGL context exists."""
    error = offscreen_gl_error()
    return unittest.skipIf(error is not None, f'No offscreen OpenGL context on this host: {error}')(test)
