"""Batch accounting for GL state imports executed directly in the native host."""
import ctypes as C
from .paths import native_library


class GLBridge:
    NAMES = ('glEnable', 'glDisable', 'glBindTexture', 'glActiveTexture', 'glClientActiveTexture',
             'glEnableClientState', 'glDisableClientState', 'glVertexPointer', 'glColorPointer',
             'glTexCoordPointer', 'glNormalPointer', 'glMatrixMode', 'glLoadMatrixf', 'glMultMatrixf',
             'glColor4f', 'glBlendFunc', 'glTexEnvf', 'glTexEnvfv', 'glMaterialf', 'glMaterialfv',
             'glLightf', 'glLightfv', 'glLightModelf', 'glLightModelfv', 'glFogf', 'glFogfv',
             'glDepthFunc', 'glDepthMask', 'glColorMask', 'glAlphaFunc', 'glCullFace', 'glFrontFace',
             'glShadeModel', 'glPolygonOffset', 'glViewport', 'glScissor', 'glStencilFunc',
             'glStencilOp', 'glHint', 'glTexParameterf')

    def __init__(self, arm):
        self.arm = arm
        self.lib = C.CDLL(str(native_library('libre4fast.so')))
        self.lib.re4_gl_open.argtypes = (C.c_void_p, C.c_size_t, C.c_size_t, C.c_size_t, C.c_int)
        self.lib.re4_gl_open.restype = C.c_void_p
        self.lib.re4_gl_error.argtypes = (C.c_void_p,)
        self.lib.re4_gl_error.restype = C.c_char_p
        self.lib.re4_gl_measure.argtypes = (C.c_void_p, C.c_uint)
        self.lib.re4_gl_measure.restype = C.c_uint64
        self.lib.re4_gl_close.argtypes = (C.c_void_p,)
        start = arm.base+13*1024*1024
        self.handle = self.lib.re4_gl_open(arm.uc._uch, arm.base, arm.SIZE, start, bool(arm.diagnostics))
        if not self.handle:
            raise RuntimeError('Cannot initialize native graphics import bridge')
        self._calls = self._nanoseconds = 0
        self._operations = [0]*len(self.NAMES)
        self.original_imports = {name: arm.imports[name] for name in self.NAMES}
        for i, name in enumerate(self.NAMES):
            address = start+i*4
            arm.write(address, b'\x1e\xff\x2f\xe1')
            arm.imports[name] = address

    def collect(self):
        error = self.lib.re4_gl_error(self.handle)
        if error:
            raise RuntimeError(error.decode())
        calls = self.lib.re4_gl_measure(self.handle, 0)
        if calls == self._calls:
            return
        for i, name in enumerate(self.NAMES):
            value = self.lib.re4_gl_measure(self.handle, i+3)
            self.arm.calls[name] += value-self._operations[i]
            self._operations[i] = value
        diagnostics = self.arm.diagnostics
        if diagnostics:
            nanoseconds = self.lib.re4_gl_measure(self.handle, 1)
            diagnostics.external_graphics((nanoseconds-self._nanoseconds)/1e9, calls-self._calls,
                                         self.lib.re4_gl_measure(self.handle, 2)/1e9)
            self._nanoseconds = nanoseconds
        self._calls = calls

    def metrics(self):
        return {'enabled': True, 'calls': self.lib.re4_gl_measure(self.handle, 0)}

    def close(self):
        if self.handle:
            self.lib.re4_gl_close(self.handle)
            self.handle = None
