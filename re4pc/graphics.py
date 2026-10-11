"""SDL desktop window and GLES1-to-desktop OpenGL import bridge."""
import ctypes as C
from .runtime_log import log
import struct
from .bionic import float_in, signed
from .textures import palette_texture

# i = signed int, u = unsigned int, f = ARM soft-float float, p = guest pointer.
SIGNATURES = {
 'glFlush':'', 'glFinish':'', 'glVertexPointer':'iiip', 'glEnableClientState':'u',
 'glNormalPointer':'uip', 'glDisableClientState':'u', 'glColorPointer':'iuip',
 'glTexCoordPointer':'iuip', 'glClear':'u', 'glColorMask':'uuuu', 'glDepthMask':'u',
 'glClearColor':'ffff', 'glDrawArrays':'uii', 'glDrawElements':'uiup',
 'glGenTextures':'ip', 'glGetError':'', 'glBindTexture':'uu',
 'glCompressedTexImage2D':'uiuiiiip', 'glTexImage2D':'uiiiiiuup',
 'glDeleteTextures':'ip', 'glTexSubImage2D':'uiiiiiuup',
 'glClientActiveTexture':'u', 'glActiveTexture':'u', 'glEnable':'u', 'glDisable':'u',
 'glCullFace':'u', 'glViewport':'iiii', 'glScissor':'iiii', 'glPixelStorei':'ui',
 'glCopyTexImage2D':'uiuiiiii', 'glTexParameterf':'uuf', 'glTexEnvf':'uuf',
 'glTexEnvfv':'uup', 'glMaterialf':'uuf', 'glColor4f':'ffff', 'glMaterialfv':'uup',
 'glBlendFunc':'uu', 'glShadeModel':'u', 'glLightModelf':'uf', 'glHint':'uu',
 'glPolygonOffset':'ff', 'glAlphaFunc':'uf', 'glFogf':'uf', 'glFogfv':'up',
 'glLightModelfv':'up', 'glMatrixMode':'u', 'glLoadMatrixf':'p', 'glLightfv':'uup',
 'glLightf':'uuf', 'glMultMatrixf':'p', 'glGetIntegerv':'up', 'glGetString':'u',
 'glReadPixels':'iiiiuup', 'glDepthFunc':'u', 'glFrontFace':'u',
 'glStencilFunc':'uiu', 'glStencilOp':'uuu', 'glClearStencil':'i',
}
TYPES = {'i': C.c_int, 'u': C.c_uint, 'f': C.c_float, 'p': C.c_void_p}

class Graphics:
    def __init__(self, arm, width=800, height=480, hidden=False):
        self.arm, self.width, self.height = arm, width, height
        self.sdl = C.CDLL('libSDL2-2.0.so.0')
        self.gl = C.CDLL('libGL.so.1')
        self.window = None
        self.context = None
        self.draws = 0
        self.textures = 0
        self.debug_messages = set()
        self.gl_errors = {}
        self.signature('SDL_Init', C.c_int, C.c_uint)
        self.signature('SDL_GetError', C.c_char_p)
        self.signature('SDL_GL_SetAttribute', C.c_int, C.c_int, C.c_int)
        self.signature('SDL_CreateWindow', C.c_void_p, C.c_char_p, C.c_int, C.c_int, C.c_int, C.c_int, C.c_uint)
        self.signature('SDL_GL_CreateContext', C.c_void_p, C.c_void_p)
        self.signature('SDL_GL_SwapWindow', None, C.c_void_p)
        self.signature('SDL_PollEvent', C.c_int, C.c_void_p)
        self.signature('SDL_GL_DeleteContext', None, C.c_void_p)
        self.signature('SDL_DestroyWindow', None, C.c_void_p)
        self.signature('SDL_Quit', None)
        self.signature('SDL_GL_SetSwapInterval', C.c_int, C.c_int)
        self.signature('SDL_SetWindowTitle',None,C.c_void_p,C.c_char_p)
        self.signature('SDL_SetRelativeMouseMode',C.c_int,C.c_int)
        if self.sdl.SDL_Init(0x20 | 0x10):
            raise RuntimeError(self.sdl.SDL_GetError().decode())
        for attribute, value in ((17, 2), (18, 1), (21, 2), (5, 1), (6, 24), (7, 8)):
            self.sdl.SDL_GL_SetAttribute(attribute, value)
        flags = 2 | (8 if hidden else 4)
        self.window = self.sdl.SDL_CreateWindow(b'Resident Evil 4 Mobile - Linux host',
                0x2fff0000, 0x2fff0000, width, height, flags)
        if not self.window:
            raise RuntimeError(self.sdl.SDL_GetError().decode())
        self.context = self.sdl.SDL_GL_CreateContext(self.window)
        if not self.context:
            raise RuntimeError(self.sdl.SDL_GetError().decode())
        self.sdl.SDL_GL_SetSwapInterval(0)
        for name, signature in SIGNATURES.items():
            function = getattr(self.gl, name)
            function.argtypes = tuple(TYPES[kind] for kind in signature)
            function.restype = C.c_void_p if name == 'glGetString' else C.c_uint if name == 'glGetError' else None
            arm.register(name, self.forward(name, signature, function))
        log.info('OpenGL version: %s', C.string_at(self.gl.glGetString(0x1f02)).decode())
        log.info('Renderer: %s', C.string_at(self.gl.glGetString(0x1f01)).decode())
        callback_type=C.CFUNCTYPE(None,C.c_uint,C.c_uint,C.c_uint,C.c_uint,C.c_int,C.c_char_p,C.c_void_p)
        def debug(source,kind,identifier,severity,length,message,user):
            text=message.decode(errors='replace')
            if severity != 0x826b and text not in self.debug_messages and len(self.debug_messages)<30:
                self.debug_messages.add(text)
                log.warning('[GL] %s',text)
        self.debug_callback=callback_type(debug)
        extensions=C.string_at(self.gl.glGetString(0x1f03)).split()
        if b'GL_KHR_debug' in extensions:
            self.gl.glDebugMessageCallback.argtypes=(callback_type,C.c_void_p)
            self.gl.glEnable(0x92e0)
            self.gl.glDebugMessageCallback(self.debug_callback,None)

    def signature(self, name, result, *args):
        function = getattr(self.sdl, name)
        function.restype, function.argtypes = result, args

    def forward(self, name, signature, function):
        def invoke(*unused):
            values = self.arm.args(len(signature))
            for i, kind in enumerate(signature):
                if kind == 'f':
                    values[i] = float_in(values[i])
                elif kind == 'i':
                    values[i] = signed(values[i])
                elif kind == 'p' and values[i]:
                    self.arm.check(values[i])
            if name == 'glCompressedTexImage2D' and 0x8b90 <= values[2] <= 0x8b99:
                target,level,fmt,width,height,border,length,pointer = values
                images = palette_texture(fmt,width,height,level,self.arm.read(pointer,length))
                upload = self.gl.glTexImage2D
                for mip,w,h,pixels in images:
                    buffer = C.create_string_buffer(pixels)
                    upload(target,mip,0x1908,w,h,border,0x1908,0x1401,C.addressof(buffer))
                result = 0
            else:
                result = function(*values)
            if name == 'glGetString':
                return self.arm.cstring(C.string_at(result)) if result else 0
            if name in ('glDrawArrays', 'glDrawElements'):
                self.draws += 1
            if name in ('glTexImage2D', 'glCompressedTexImage2D'):
                self.textures += 1
            return result or 0
        return invoke

    def events(self):
        event = C.create_string_buffer(64)
        while self.sdl.SDL_PollEvent(event):
            data = event.raw
            kind = struct.unpack_from('<I', data)[0]
            if kind == 0x100:
                yield ('quit',)
            elif kind == 0x200 and data[12] == 13:
                yield ('focus_lost',)
            elif kind in (0x300, 0x301):
                key = struct.unpack_from('<i', data, 20)[0]
                repeat = data[13]
                if not repeat:
                    yield ('key', kind == 0x300, key)
            elif kind in (0x401, 0x402):
                x, y = struct.unpack_from('<ii', data, 20)
                if data[16] == 1:
                    yield ('touch', kind == 0x401, x, y)
                elif data[16] == 3:
                    yield ('mouse_button',kind == 0x401,3)
            elif kind == 0x400:
                buttons = struct.unpack_from('<I', data, 16)[0]
                x, y = struct.unpack_from('<ii', data, 20)
                dx,dy=struct.unpack_from('<ii',data,28)
                yield ('mouse_delta',dx,dy)
                if buttons & 1:
                    yield ('motion', x, y)

    def swap(self):
        self.sdl.SDL_GL_SwapWindow(self.window)

    def screenshot(self, path):
        self.gl.glReadBuffer.argtypes = (C.c_uint,)
        self.gl.glReadBuffer(0x405)  # GL_BACK; capture before swapping.
        self.gl.glPixelStorei(0x0d05, 1)
        buffer = C.create_string_buffer(self.width * self.height * 3)
        self.gl.glReadPixels(0, 0, self.width, self.height, 0x1907, 0x1401, C.addressof(buffer))
        from PIL import Image
        image = Image.frombytes('RGB', (self.width, self.height), buffer.raw)
        image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(path)

    def draw_video(self, data):
        gl = self.gl
        # Preserve the engine's fixed-function state around the video overlay.
        gl.glPushAttrib.argtypes = (C.c_uint,)
        gl.glPushAttrib(0xfffff)
        # Pixel-store state belongs to the client stack, not glPushAttrib.
        gl.glPushClientAttrib.argtypes = (C.c_uint,)
        gl.glPushClientAttrib(0x00000001)  # GL_CLIENT_PIXEL_STORE_BIT
        for cap in (0x0b71,0x0b50,0x0be2,0x0b60,0x0b90,0x0de1,0x0bc0,0x0c11): gl.glDisable(cap)
        # A menu/fade pass can leave writes masked off. Movies are an opaque
        # desktop overlay and must not inherit that engine state.
        gl.glColorMask(1,1,1,1)
        gl.glDrawBuffer.argtypes = (C.c_uint,)
        gl.glDrawBuffer(0x405)  # GL_BACK
        gl.glViewport(0,0,self.width,self.height)
        gl.glMatrixMode(0x1701); gl.glPushMatrix(); gl.glLoadIdentity()
        gl.glMatrixMode(0x1700); gl.glPushMatrix(); gl.glLoadIdentity()
        gl.glWindowPos2i.argtypes = (C.c_int,C.c_int)
        gl.glWindowPos2i(0,self.height)
        gl.glPixelZoom.argtypes = (C.c_float,C.c_float)
        gl.glPixelZoom(1.0,-1.0)
        gl.glPixelStorei(0x0cf5,1)
        for parameter in (0x0cf2,0x0cf3,0x0cf4):
            gl.glPixelStorei(parameter,0)  # unpack row length / skipped rows / pixels
        gl.glDrawPixels.argtypes = (C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_void_p)
        buffer=C.create_string_buffer(data)
        gl.glDrawPixels(self.width,self.height,0x1907,0x1401,buffer)
        gl.glPopMatrix(); gl.glMatrixMode(0x1701); gl.glPopMatrix()
        gl.glPopClientAttrib(); gl.glPopAttrib()

    def close(self):
        if self.context:
            self.sdl.SDL_GL_DeleteContext(self.context)
            self.context = None
        if self.window:
            self.sdl.SDL_DestroyWindow(self.window)
            self.window = None
        self.sdl.SDL_Quit()
