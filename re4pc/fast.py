"""Accelerate frequently called memory/string imports without Python transitions."""
import ctypes as C
from pathlib import Path

class Fast:
    NAMES=('memcpy','memmove','memset','memcmp','strlen','strcmp','strncmp','strcpy','strncpy','wcslen')
    def __init__(self,arm):
        self.arm=arm
        library=Path(__file__).resolve().parent.parent/'build/libre4fast.so'
        self.lib=C.CDLL(str(library))
        self.lib.re4_fast_open.argtypes=(C.c_void_p,C.c_size_t,C.c_size_t,C.c_size_t)
        self.lib.re4_fast_open.restype=C.c_void_p
        self.lib.re4_fast_error.argtypes=(C.c_void_p,)
        self.lib.re4_fast_error.restype=C.c_char_p
        self.lib.re4_fast_calls.argtypes=(C.c_void_p,)
        self.lib.re4_fast_calls.restype=C.c_uint64
        self.lib.re4_fast_close.argtypes=(C.c_void_p,)
        start=arm.base+12*1024*1024
        self.handle=self.lib.re4_fast_open(arm.uc._uch,arm.base,arm.SIZE,start)
        if not self.handle: raise RuntimeError('Cannot create native Unicorn import bridge')
        for i,name in enumerate(self.NAMES):
            address=start+4*i
            arm.write(address,b'\x1e\xff\x2f\xe1')
            arm.imports[name]=address
        arm.fast=self
    def check(self):
        error=self.lib.re4_fast_error(self.handle)
        if error: raise RuntimeError(error.decode())
    def calls(self): return self.lib.re4_fast_calls(self.handle)
    def close(self):
        if self.handle:self.lib.re4_fast_close(self.handle);self.handle=None
