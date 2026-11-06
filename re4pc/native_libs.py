"""Load SDL2, desktop OpenGL and the native helpers on Linux, Windows and macOS.

Portable Windows/macOS builds place SDL2 beside the helpers in ``build/``.
Loading that copy by full path first makes the helpers' own SDL2 dependency
resolve to the same instance, so audio, video and input share one SDL.
"""
import ctypes as C
import ctypes.util
import os
import sys
from functools import lru_cache
from pathlib import Path

from .paths import native_dir, native_library

WINDOWS = sys.platform == 'win32'
MACOS = sys.platform == 'darwin'


def _prepare_dll_search():
    if WINDOWS and native_dir().is_dir():
        os.add_dll_directory(str(native_dir()))


def _sdl_candidates():
    override = os.environ.get('RE4PC_SDL2')
    if override:
        yield override
    if WINDOWS:
        yield str(native_dir() / 'SDL2.dll')
        yield 'SDL2.dll'
    elif MACOS:
        yield str(native_dir() / 'libSDL2-2.0.0.dylib')
        found = ctypes.util.find_library('SDL2')
        if found:
            yield found
        for prefix in ('/opt/homebrew', '/usr/local', '/opt/local'):
            yield prefix + '/lib/libSDL2-2.0.0.dylib'
    else:
        yield 'libSDL2-2.0.so.0'
        yield 'libSDL2.so'


@lru_cache(maxsize=None)
def sdl():
    _prepare_dll_search()
    errors = []
    for candidate in _sdl_candidates():
        if os.path.isabs(candidate) and not Path(candidate).is_file():
            continue
        try:
            return C.CDLL(candidate)
        except OSError as error:
            errors.append(f'{candidate}: {error}')
    raise OSError('SDL2 runtime library not found. ' + '; '.join(errors[-3:]))


class GL:
    """Desktop OpenGL exports, falling back to SDL_GL_GetProcAddress.

    Windows' opengl32.dll only exports OpenGL 1.1, so newer entry points are
    resolved through the current context. Attributes are cached, so argtypes
    assigned by callers persist exactly as with a ctypes.CDLL.
    """

    def __init__(self, library, sdl_library):
        self._library = library
        self._sdl = sdl_library
        self._sdl.SDL_GL_GetProcAddress.argtypes = (C.c_char_p,)
        self._sdl.SDL_GL_GetProcAddress.restype = C.c_void_p

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        try:
            function = getattr(self._library, name)
        except AttributeError:
            address = self._sdl.SDL_GL_GetProcAddress(name.encode())
            if not address:
                raise AttributeError(f'OpenGL entry point unavailable: {name}') from None
            prototype = C.WINFUNCTYPE(C.c_int) if WINDOWS else C.CFUNCTYPE(C.c_int)
            function = prototype(address)
        setattr(self, name, function)
        return function


@lru_cache(maxsize=None)
def gl():
    if WINDOWS:
        library = C.WinDLL('opengl32')
    elif MACOS:
        library = C.CDLL('/System/Library/Frameworks/OpenGL.framework/OpenGL')
    else:
        library = C.CDLL('libGL.so.1')
    return GL(library, sdl())


@lru_cache(maxsize=None)
def fast():
    """libre4fast with Unicorn's own exports bound (see native/uc_api.h)."""
    from unicorn.unicorn_py3.unicorn import uclib
    _prepare_dll_search()
    library = C.CDLL(str(native_library('libre4fast.so')))
    def address(function):
        return C.cast(function, C.c_void_p).value
    library.re4_uc_bind.argtypes = (C.c_void_p,) * 5
    library.re4_uc_bind.restype = None
    library.re4_uc_bind(address(uclib.uc_hook_add), address(uclib.uc_hook_del),
                        address(uclib.uc_reg_read_batch), address(uclib.uc_reg_write),
                        address(uclib.uc_emu_stop))
    return library


@lru_cache(maxsize=None)
def audio():
    sdl()  # resolve libre4audio's SDL2 dependency to the shared instance
    return C.CDLL(str(native_library('libre4audio.so')))


@lru_cache(maxsize=None)
def math():
    return C.CDLL(str(native_library('libre4math.so')))
