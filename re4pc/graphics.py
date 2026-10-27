"""SDL desktop window and GLES1-to-desktop OpenGL import bridge."""
import ctypes as C
from contextlib import nullcontext
from .controllers import ControllerInput
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
    def __init__(self, arm, width=800, height=480, hidden=False, logical_size=None):
        self.arm = arm
        self.width, self.height = logical_size or (width, height)
        self.logical_surface = logical_size is not None
        self.framebuffer = self.surface_texture = self.surface_depth = 0
        self.fullscreen = False
        self.diagnostics = self.texture_cache = None
        self.laser = None
        self.render_stream = None
        self._mouse_touch = False
        self.mouse_captured = False
        self._fullscreen_enter = False
        self.window_size = (width, height)
        self.drawable_size = (width, height)
        self.sdl = C.CDLL('libSDL2-2.0.so.0')
        self.gl = C.CDLL('libGL.so.1')
        self.window = None
        self.context = None
        self.draws = 0
        self.textures = 0
        self.presentations = 0
        self.debug_messages = set()
        self.gl_errors = {}
        self.signature('SDL_Init', C.c_int, C.c_uint)
        self.signature('SDL_GetError', C.c_char_p)
        self.signature('SDL_GetWindowID', C.c_uint, C.c_void_p)
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
        self.signature('SDL_SetWindowGrab',None,C.c_void_p,C.c_int)
        self.signature('SDL_ShowCursor',C.c_int,C.c_int)
        self.signature('SDL_WarpMouseInWindow',None,C.c_void_p,C.c_int,C.c_int)
        self.signature('SDL_GetWindowSize',None,C.c_void_p,C.POINTER(C.c_int),C.POINTER(C.c_int))
        self.signature('SDL_GL_GetDrawableSize',None,C.c_void_p,C.POINTER(C.c_int),C.POINTER(C.c_int))
        self.signature('SDL_SetWindowFullscreen',C.c_int,C.c_void_p,C.c_uint)
        if self.sdl.SDL_Init(0x20 | 0x10 | 0x2000):
            raise RuntimeError(self.sdl.SDL_GetError().decode())
        for attribute, value in ((17, 2), (18, 1), (21, 2), (5, 1), (6, 24), (7, 8)):
            self.sdl.SDL_GL_SetAttribute(attribute, value)
        flags = 2 | 0x20 | 0x2000 | (8 if hidden else 4)
        self.window = self.sdl.SDL_CreateWindow(b'Resident Evil 4 Mobile',
                0x2fff0000, 0x2fff0000, width, height, flags)
        if not self.window:
            raise RuntimeError(self.sdl.SDL_GetError().decode())
        self.window_id = self.sdl.SDL_GetWindowID(self.window)
        self.context = self.sdl.SDL_GL_CreateContext(self.window)
        if not self.context:
            raise RuntimeError(self.sdl.SDL_GetError().decode())
        self.sdl.SDL_GL_SetSwapInterval(0)
        for name, signature in SIGNATURES.items():
            function = getattr(self.gl, name)
            function.argtypes = tuple(TYPES[kind] for kind in signature)
            function.restype = C.c_void_p if name == 'glGetString' else C.c_uint if name == 'glGetError' else None
            arm.register(name, self.forward(name, signature, function))
        self.version = C.string_at(self.gl.glGetString(0x1f02)).decode()
        self.renderer = C.string_at(self.gl.glGetString(0x1f01)).decode()
        log.info('OpenGL version: %s', self.version)
        log.info('Renderer: %s', self.renderer)
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

        try:
            self.controller = ControllerInput(self.sdl)
            if self.logical_surface:
                self._create_surface()
            self.update_drawable()
            self.begin_frame()
        except BaseException:
            self.close()
            raise

    def _phase(self, name, operation=None):
        return self.diagnostics.phase(name, operation) if self.diagnostics else nullcontext()

    def _create_surface(self):
        gl = self.gl
        for name, args in {'glGenFramebuffers':(C.c_int,C.c_void_p),
                           'glBindFramebuffer':(C.c_uint,C.c_uint),
                           'glFramebufferTexture2D':(C.c_uint,C.c_uint,C.c_uint,C.c_uint,C.c_int),
                           'glGenRenderbuffers':(C.c_int,C.c_void_p),
                           'glBindRenderbuffer':(C.c_uint,C.c_uint),
                           'glRenderbufferStorage':(C.c_uint,C.c_uint,C.c_int,C.c_int),
                           'glFramebufferRenderbuffer':(C.c_uint,C.c_uint,C.c_uint,C.c_uint),
                           'glCheckFramebufferStatus':(C.c_uint,),
                           'glBlitFramebuffer':(C.c_int,)*8+(C.c_uint,C.c_uint),
                           'glDeleteFramebuffers':(C.c_int,C.c_void_p),
                           'glDeleteRenderbuffers':(C.c_int,C.c_void_p),
                           'glDrawBuffer':(C.c_uint,), 'glReadBuffer':(C.c_uint,)}.items():
            function = getattr(gl, name)
            function.argtypes = args
            function.restype = C.c_uint if name == 'glCheckFramebufferStatus' else None
        texture, framebuffer, depth = C.c_uint(), C.c_uint(), C.c_uint()
        gl.glGenTextures(1,C.byref(texture))
        gl.glBindTexture(0x0de1,texture.value)
        gl.glTexImage2D(0x0de1,0,0x8058,self.width,self.height,0,0x1908,0x1401,None)
        gl.glGenFramebuffers(1,C.byref(framebuffer))
        gl.glBindFramebuffer(0x8d40,framebuffer.value)
        gl.glFramebufferTexture2D(0x8d40,0x8ce0,0x0de1,texture.value,0)
        gl.glGenRenderbuffers(1,C.byref(depth))
        gl.glBindRenderbuffer(0x8d41,depth.value)
        gl.glRenderbufferStorage(0x8d41,0x88f0,self.width,self.height)
        gl.glFramebufferRenderbuffer(0x8d40,0x821a,0x8d41,depth.value)
        self.surface_texture, self.framebuffer, self.surface_depth = texture.value, framebuffer.value, depth.value
        if gl.glCheckFramebufferStatus(0x8d40) != 0x8cd5:
            raise RuntimeError('Logical render surface framebuffer is incomplete')
        gl.glBindTexture(0x0de1,0)
        gl.glBindRenderbuffer(0x8d41,0)
        gl.glDrawBuffer(0x8ce0)
        gl.glReadBuffer(0x8ce0)

    @staticmethod
    def viewport_for(logical, drawable):
        width, height = drawable
        if width <= 0 or height <= 0:
            return (0,0,0,0)
        scale = min(width / logical[0], height / logical[1])
        w, h = max(1, round(logical[0]*scale)), max(1, round(logical[1]*scale))
        return ((width-w)//2,(height-h)//2,w,h)

    def update_drawable(self):
        w,h,dw,dh = C.c_int(),C.c_int(),C.c_int(),C.c_int()
        self.sdl.SDL_GetWindowSize(self.window,C.byref(w),C.byref(h))
        self.sdl.SDL_GL_GetDrawableSize(self.window,C.byref(dw),C.byref(dh))
        self.window_size = (w.value,h.value)
        self.drawable_size = (dw.value,dh.value)
        self.viewport = self.viewport_for((self.width,self.height),self.drawable_size)

    def map_point(self, x, y, clamp=False):
        ww,wh = self.window_size
        dw,dh = self.drawable_size
        vx,vy,vw,vh = self.viewport
        if min(ww,wh,vw,vh) <= 0:
            return None
        px,py = x*dw/ww,y*dh/wh
        top = dh-vy-vh
        if not clamp and not (vx <= px < vx+vw and top <= py < top+vh):
            return None
        lx,ly = (px-vx)*self.width/vw,(py-top)*self.height/vh
        return (max(0,min(self.width-1,round(lx))),max(0,min(self.height-1,round(ly))))

    def capture_mouse(self, capture):
        """Confine and hide the gameplay pointer; never turn it into a touch."""
        if capture:
            # SDL takes window coordinates, not HiDPI drawable coordinates.
            # The letterboxed game viewport shares the window's center.
            self.sdl.SDL_WarpMouseInWindow(self.window, self.window_size[0]//2,
                                          self.window_size[1]//2)
        if self.sdl.SDL_SetRelativeMouseMode(int(capture)):
            raise RuntimeError('Cannot capture mouse: '+self.sdl.SDL_GetError().decode())
        self.sdl.SDL_SetWindowGrab(self.window, int(capture))
        self.sdl.SDL_ShowCursor(0 if capture else 1)
        self.mouse_captured = capture
        self._mouse_touch = False

    def begin_frame(self):
        if self.framebuffer:
            self.gl.glBindFramebuffer(0x8d40,self.framebuffer)
        self.gl.glViewport(0,0,self.width,self.height)

    def toggle_fullscreen(self):
        requested = not self.fullscreen
        with self._phase('window_mode', 'SDL_SetWindowFullscreen'):
            if self.sdl.SDL_SetWindowFullscreen(self.window,0x1001 if requested else 0):
                raise RuntimeError(self.sdl.SDL_GetError().decode())
            self.fullscreen = requested
            self.update_drawable()
        return requested

    def signature(self, name, result, *args):
        function = getattr(self.sdl, name)
        function.restype, function.argtypes = result, args

    def forward(self, name, signature, function):
        draw = name in ('glDrawArrays', 'glDrawElements')
        resource = name in ('glTexImage2D', 'glTexSubImage2D', 'glCompressedTexImage2D',
                            'glCopyTexImage2D', 'glDeleteTextures')
        def invoke(*unused):
            values = self.arm.args(len(signature))
            for i, kind in enumerate(signature):
                if kind == 'f':
                    values[i] = float_in(values[i])
                elif kind == 'i':
                    values[i] = signed(values[i])
                elif kind == 'p' and values[i]:
                    self.arm.check(values[i])
            stream = self.render_stream
            if stream and resource:
                stream.dirty()
            if stream and name == 'glClear':
                stream.clear(values[0])
            if name == 'glCompressedTexImage2D' and 0x8b90 <= values[2] <= 0x8b99:
                target,level,fmt,width,height,border,length,pointer = values
                with self._phase('texture_conversion'):
                    data = self.arm.read(pointer,length)
                    images = self.texture_cache.convert(fmt,width,height,level,data) if self.texture_cache else palette_texture(fmt,width,height,level,data)
                upload = self.gl.glTexImage2D
                for mip,w,h,pixels in images:
                    buffer = C.create_string_buffer(pixels)
                    with self._phase('graphics_upload'):
                        upload(target,mip,0x1908,w,h,border,0x1908,0x1401,C.addressof(buffer))
                result = 0
            else:
                # ArmRuntime's import scope already attributes submission and
                # upload, including argument marshaling. Avoid a second scope
                # for every GL import; compressed conversion still nests above.
                if draw and stream and stream.recording:
                    def submit(*arguments):
                        stream.draw(name, arguments)
                        return function(*arguments)
                else:
                    submit = function
                if draw and self.laser and self.laser.stage:
                    result = self.laser.draw(submit, values)
                else:
                    result = submit(*values)
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
            if kind in (0x200,0x300,0x301,0x400,0x401,0x402) and getattr(self,'window_id',None):
                if struct.unpack_from('<I',data,8)[0] != self.window_id:
                    continue
            if kind == 0x100:
                yield ('quit',)
            elif kind == 0x200:
                if data[12] == 13:
                    self._mouse_touch = False
                    yield ('focus_lost',)
                elif data[12] in (5,6):
                    self.update_drawable()
                    yield ('resize', *self.window_size)
            elif kind in (0x300, 0x301):
                key = struct.unpack_from('<i', data, 20)[0]
                repeat = data[13]
                modifiers = struct.unpack_from('<H',data,24)[0]
                if key == 13 and (modifiers & 0x300 or self._fullscreen_enter):
                    if kind == 0x300 and not repeat:
                        self._fullscreen_enter = True
                        self.toggle_fullscreen()
                    elif kind == 0x301:
                        self._fullscreen_enter = False
                    continue
                if not repeat:
                    yield ('key', kind == 0x300, key)
            elif kind in (0x401, 0x402):
                x, y = struct.unpack_from('<ii', data, 20)
                down,button = kind == 0x401,data[16]
                if button == 1 and not self.mouse_captured:
                    point = self.map_point(x,y,clamp=self._mouse_touch)
                    if point is not None:
                        self._mouse_touch = down
                        yield ('touch', down, *point)
                else:
                    yield ('mouse_button',down,button)
            elif kind == 0x400:
                x,y = struct.unpack_from('<ii',data,20)
                dx,dy = struct.unpack_from('<ii',data,28)
                yield ('mouse_delta',dx,dy)
                if self._mouse_touch and not self.mouse_captured:
                    point = self.map_point(x,y,clamp=True)
                    if point is not None:
                        yield ('motion',*point)
            elif kind == 0x650:
                instance = struct.unpack_from('<i',data,8)[0]
                value = struct.unpack_from('<h',data,16)[0]
                yield ('controller_axis',instance,data[12],value)
            elif kind in (0x651,0x652):
                yield ('controller_button',kind == 0x651,struct.unpack_from('<i',data,8)[0],data[12])
            elif kind in (0x653,0x654):
                yield ('controller_added' if kind == 0x653 else 'controller_removed',struct.unpack_from('<i',data,8)[0])

    def present(self):
        self.update_drawable()
        if self.framebuffer:
            gl = self.gl
            gl.glPushAttrib.argtypes = (C.c_uint,)
            gl.glPushAttrib(0xfffff)
            read_binding,draw_binding = C.c_int(),C.c_int()
            gl.glGetIntegerv(0x8caa,C.byref(read_binding))
            gl.glGetIntegerv(0x8ca6,C.byref(draw_binding))
            gl.glBindFramebuffer(0x8ca8,self.framebuffer)
            gl.glBindFramebuffer(0x8ca9,0)
            gl.glReadBuffer(0x8ce0)
            gl.glDrawBuffer(0x405)
            gl.glDisable(0x0c11)
            gl.glColorMask(1,1,1,1)
            gl.glClearColor(0,0,0,1)
            gl.glClear(0x4000)
            x,y,w,h = self.viewport
            if w and h:
                gl.glBlitFramebuffer(0,0,self.width,self.height,x,y,x+w,y+h,0x4000,0x2601)
            gl.glBindFramebuffer(0x8ca8,read_binding.value)
            gl.glBindFramebuffer(0x8ca9,draw_binding.value)
            gl.glPopAttrib()
        self.sdl.SDL_GL_SwapWindow(self.window)
        self.presentations += 1

    def swap(self):
        self.present()

    def capture_image(self):
        gl = self.gl
        gl.glReadBuffer.argtypes = (C.c_uint,)
        gl.glPushAttrib.argtypes = (C.c_uint,)
        gl.glPushClientAttrib.argtypes = (C.c_uint,)
        gl.glPushAttrib(0xfffff)
        gl.glPushClientAttrib(1)
        gl.glReadBuffer(0x8ce0 if self.framebuffer else 0x405)
        gl.glPixelStorei(0x0d05,1)
        for parameter in (0x0d02,0x0d03,0x0d04):
            gl.glPixelStorei(parameter,0)
        buffer = C.create_string_buffer(self.width*self.height*3)
        gl.glReadPixels(0,0,self.width,self.height,0x1907,0x1401,C.addressof(buffer))
        gl.glPopClientAttrib()
        gl.glPopAttrib()
        from PIL import Image
        image = Image.frombytes('RGB',(self.width,self.height),buffer.raw)
        return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    def screenshot(self, path):
        self.capture_image().save(path)

    def draw_overlay(self, lines, graph=()):
        from PIL import Image, ImageDraw
        panel = Image.new('RGBA',(self.width,self.height))
        draw = ImageDraw.Draw(panel)
        text = '\n'.join(str(line) for line in lines)
        height = min(self.height, 16*len(lines)+75)
        draw.rectangle((5,5,min(self.width-5,650),height),fill=(0,0,0,210))
        draw.multiline_text((12,12),text,fill=(255,255,255,255),spacing=4)
        values = list(graph)[-120:]
        if len(values)>1:
            top = height-55
            points = [(12+i*4,top+45-min(45,max(0,value)*0.45)) for i,value in enumerate(values)]
            draw.line(points,fill=(80,220,130,255),width=2)
        self._draw_pixels(panel.tobytes(),rgba=True)

    def draw_menu_focus(self, rect):
        """Outline the focused menu control in blood red, round for icon buttons."""
        x, y, w, h = rect
        round_icon = abs(w - h) <= 4 and w <= 110
        key = (w, h, round_icon)
        if getattr(self, '_focus_sprite', (None,))[0] != key:
            from PIL import Image, ImageDraw
            pad = 4
            sprite = Image.new('RGBA', (w + 2*pad, h + 2*pad))
            draw = ImageDraw.Draw(sprite)
            shape = draw.ellipse if round_icon else draw.rectangle
            shape((0, 0, w + 2*pad - 1, h + 2*pad - 1), outline=(0, 0, 0, 200), width=1)
            shape((1, 1, w + 2*pad - 2, h + 2*pad - 2), outline=(178, 16, 12, 255), width=3)
            shape((4, 4, w + 2*pad - 5, h + 2*pad - 5), outline=(0, 0, 0, 140), width=1)
            self._focus_sprite = (key, sprite.tobytes(), sprite.size, pad)
        _, data, size, pad = self._focus_sprite
        self._draw_pixels(data, rgba=True, size=size, position=(x - pad, y - pad))

    def _draw_pixels(self, data, rgba=False, size=None, position=(0,0)):
        gl = self.gl
        # Preserve the engine's fixed-function state around the video overlay.
        gl.glPushAttrib.argtypes = (C.c_uint,)
        gl.glPushAttrib(0xfffff)
        # Pixel-store state belongs to the client stack, not glPushAttrib.
        gl.glPushClientAttrib.argtypes = (C.c_uint,)
        gl.glPushClientAttrib(0x00000001)  # GL_CLIENT_PIXEL_STORE_BIT
        for cap in (0x0b71,0x0b50,0x0be2,0x0b60,0x0b90,0x0de1,0x0bc0,0x0c11): gl.glDisable(cap)
        # Rasterized pixels still pass through fixed-function texturing. The
        # engine can leave several units enabled, which modulates UI pixels
        # with a native texture even after disabling the current unit.
        active, units = C.c_int(), C.c_int()
        gl.glGetIntegerv(0x84e0, C.byref(active))
        gl.glGetIntegerv(0x84e2, C.byref(units))
        for unit in range(max(1, units.value)):
            gl.glActiveTexture(0x84c0 + unit)
            gl.glDisable(0x0de1)
        gl.glActiveTexture(active.value)
        # A menu/fade pass can leave writes masked off. Movies are an opaque
        # desktop overlay and must not inherit that engine state.
        gl.glColorMask(1,1,1,1)
        gl.glDrawBuffer.argtypes = (C.c_uint,)
        gl.glDrawBuffer(0x8ce0 if self.framebuffer else 0x405)
        gl.glViewport(0,0,self.width,self.height)
        gl.glMatrixMode(0x1701); gl.glPushMatrix(); gl.glLoadIdentity()
        gl.glMatrixMode(0x1700); gl.glPushMatrix(); gl.glLoadIdentity()
        gl.glWindowPos2i.argtypes = (C.c_int,C.c_int)
        gl.glWindowPos2i(position[0],self.height-position[1])
        gl.glPixelZoom.argtypes = (C.c_float,C.c_float)
        gl.glPixelZoom(1.0,-1.0)
        gl.glPixelStorei(0x0cf5,1)
        for parameter in (0x0cf2,0x0cf3,0x0cf4):
            gl.glPixelStorei(parameter,0)  # unpack row length / skipped rows / pixels
        gl.glDrawPixels.argtypes = (C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_void_p)
        buffer=C.create_string_buffer(data)
        if rgba:
            gl.glEnable(0x0be2)
            gl.glBlendFunc(0x0302,0x0303)
        gl.glDrawPixels(*(size or (self.width,self.height)),0x1908 if rgba else 0x1907,0x1401,buffer)
        gl.glPopMatrix(); gl.glMatrixMode(0x1701); gl.glPopMatrix()
        gl.glPopClientAttrib(); gl.glPopAttrib()

    def draw_video(self, data):
        if len(data) != self.width*self.height*3:
            raise ValueError('Movie frame does not match the logical surface')
        self._draw_pixels(data)

    def close(self):
        if getattr(self, 'render_stream', None):
            self.render_stream.close()
            self.render_stream = None
        if getattr(self, 'laser', None):
            self.laser.close()
        if getattr(self,'controller',None):
            self.controller.close()
        if self.context and self.framebuffer:
            for name,value in (('glDeleteFramebuffers',self.framebuffer),('glDeleteRenderbuffers',self.surface_depth),('glDeleteTextures',self.surface_texture)):
                identifier = C.c_uint(value)
                getattr(self.gl,name)(1,C.byref(identifier))
            self.framebuffer = 0
        if self.context:
            self.sdl.SDL_GL_DeleteContext(self.context)
            self.context = None
        if self.window:
            self.sdl.SDL_DestroyWindow(self.window)
            self.window = None
        self.sdl.SDL_Quit()
