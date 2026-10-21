"""Exercise movie compositing against a real offscreen OpenGL context."""
import ctypes as C
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from re4pc.arm import ArmRuntime
from re4pc.graphics import Graphics


class VideoOverlayTests(unittest.TestCase):
    def test_real_sdl_capture_centers_hides_and_routes_clicks_without_touch(self):
        import struct
        arm = ArmRuntime()
        graphics = None
        # CI supplies X11 via Xvfb: SDL 2's offscreen driver cannot capture
        # relative mouse input, even when its OpenGL rendering works.
        driver = os.environ.get('SDL_VIDEODRIVER', 'offscreen')
        try:
            with patch.dict('os.environ', {'SDL_VIDEODRIVER': driver,
                                          'SDL_AUDIODRIVER': 'dummy'}):
                graphics = Graphics(arm, 1000, 700, hidden=driver == 'offscreen',
                                    logical_size=(800, 480))
            graphics.signature('SDL_GetRelativeMouseMode', C.c_int)
            graphics.signature('SDL_GetMouseState', C.c_uint, C.POINTER(C.c_int), C.POINTER(C.c_int))
            graphics.signature('SDL_PushEvent', C.c_int, C.c_void_p)
            list(graphics.events())
            try:
                graphics.capture_mouse(True)
            except RuntimeError as error:
                if driver == 'offscreen' and 'No relative mode implementation available' in str(error):
                    self.skipTest('SDL offscreen driver lacks relative mouse support; run under Xvfb with SDL_VIDEODRIVER=x11')
                raise
            self.assertEqual(graphics.sdl.SDL_GetRelativeMouseMode(), 1)
            self.assertEqual(graphics.sdl.SDL_ShowCursor(-1), 0)
            x, y = C.c_int(), C.c_int()
            graphics.sdl.SDL_GetMouseState(C.byref(x), C.byref(y))
            self.assertEqual((x.value, y.value), (500, 350))
            list(graphics.events())  # Discard SDL's zero-motion warp notification.
            for kind in (0x401, 0x400, 0x402):
                event = C.create_string_buffer(64)
                struct.pack_into('<I', event, 0, kind)
                if kind != 0x400: event[16] = b'\x01'
                struct.pack_into('<iiii', event, 20, -200, 2000, 14, -9)
                self.assertEqual(graphics.sdl.SDL_PushEvent(event), 1)
            mouse = [event for event in graphics.events()
                     if event[0] in ('touch', 'motion', 'mouse_button', 'mouse_delta')]
            self.assertEqual(mouse, [('mouse_button', True, 1),
                                    ('mouse_delta', 14, -9), ('mouse_button', False, 1)])
            graphics.capture_mouse(False)
            self.assertEqual(graphics.sdl.SDL_GetRelativeMouseMode(), 0)
            self.assertEqual(graphics.sdl.SDL_ShowCursor(-1), 1)
        finally:
            if graphics: graphics.close()
            arm.close()

    def test_movie_covers_frame_and_restores_engine_state(self):
        arm = ArmRuntime()
        graphics = None
        try:
            with patch.dict('os.environ', {'SDL_VIDEODRIVER': 'offscreen',
                                          'SDL_AUDIODRIVER': 'dummy'}):
                try:
                    graphics = Graphics(arm, 321, 240, hidden=True)
                except RuntimeError as error:
                    if 'No available video device' in str(error):
                        self.skipTest('SDL offscreen video driver unavailable')
                    raise
            gl = graphics.gl
            gl.glClearColor(0.0, 0.0, 0.0, 1.0)
            gl.glClear(0x4000)
            # Menu texturing on another unit used to silently modulate host
            # overlays. The overlay must disable every unit and restore them.
            textures = (C.c_uint * 2)()
            gl.glGenTextures(2, textures)
            red = C.create_string_buffer(bytes((255, 0, 0, 255)))
            for unit in range(2):
                gl.glActiveTexture(0x84c0 + unit)
                gl.glBindTexture(0x0de1, textures[unit])
                gl.glTexImage2D(0x0de1, 0, 0x1908, 1, 1, 0, 0x1908, 0x1401, C.addressof(red))
                gl.glTexParameterf(0x0de1, 0x2801, 0x2600)
                gl.glTexParameterf(0x0de1, 0x2800, 0x2600)
                gl.glEnable(0x0de1)
            gl.glActiveTexture(0x84c0)
            # Simulate state left by a menu/fade and a texture upload.
            gl.glColorMask(0, 0, 0, 0)
            gl.glDrawBuffer.argtypes = (C.c_uint,)
            gl.glDrawBuffer(0x404)  # GL_FRONT
            for parameter, value in ((0x0cf5, 8), (0x0cf2, 337),
                                     (0x0cf3, 2), (0x0cf4, 3)):
                gl.glPixelStorei(parameter, value)
            gl.glMatrixMode(0x1700)
            # Different rows detect inversion and missing boundary pixels.
            top, bottom = (20, 180, 40), (180, 40, 20)
            data = (bytes(top) * graphics.width * 120 +
                    bytes(bottom) * graphics.width * 120)
            graphics.draw_video(data)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'movie.png'
                graphics.screenshot(path)
                with Image.open(path) as picture:
                    for x in (0, 160, 320):
                        for y, expected in ((0, top), (119, top),
                                            (120, bottom), (239, bottom)):
                            self.assertEqual(picture.getpixel((x, y)), expected)
            mask = (C.c_int * 4)()
            gl.glGetIntegerv(0x0c23, C.byref(mask))
            self.assertEqual(list(mask), [0, 0, 0, 0])
            for parameter, expected in ((0x0c01, 0x404), (0x0ba0, 0x1700),
                                        (0x0cf5, 8), (0x0cf2, 337),
                                        (0x0cf3, 2), (0x0cf4, 3)):
                value = C.c_int()
                gl.glGetIntegerv(parameter, C.byref(value))
                self.assertEqual(value.value, expected)
            self.assertEqual(gl.glGetError(), 0)
            gl.glIsEnabled.argtypes, gl.glIsEnabled.restype = (C.c_uint,), C.c_uint
            for unit in range(2):
                gl.glActiveTexture(0x84c0 + unit)
                self.assertTrue(gl.glIsEnabled(0x0de1))
        finally:
            if graphics:
                graphics.close()
            arm.close()


class CoordinateTests(unittest.TestCase):
    def test_hidpi_letterbox_uses_actual_drawable_and_same_touch_transform(self):
        graphics=Graphics.__new__(Graphics)
        graphics.width,graphics.height=800,480
        graphics.window_size=(1000,700)
        graphics.drawable_size=(2000,1400)
        graphics.viewport=Graphics.viewport_for((800,480),graphics.drawable_size)
        self.assertEqual(graphics.viewport,(0,100,2000,1200))
        self.assertEqual(graphics.map_point(500,350),(400,240))
        self.assertEqual(graphics.map_point(0,50),(0,0))
        self.assertIsNone(graphics.map_point(500,20))
        self.assertEqual(graphics.map_point(500,20,clamp=True),(400,0))
        self.assertEqual(graphics.map_point(1200,800,clamp=True),(799,479))

    def test_vertical_letterbox_and_minimized_window(self):
        graphics=Graphics.__new__(Graphics)
        graphics.width,graphics.height=800,480
        graphics.window_size=graphics.drawable_size=(1200,480)
        graphics.viewport=Graphics.viewport_for((800,480),graphics.drawable_size)
        self.assertEqual(graphics.viewport,(200,0,800,480))
        self.assertEqual(graphics.map_point(600,240),(400,240))
        self.assertIsNone(graphics.map_point(100,240))
        graphics.window_size=(0,0)
        self.assertIsNone(graphics.map_point(100,100,clamp=True))


class LogicalSurfaceTests(unittest.TestCase):
    def test_movie_screenshot_and_letterbox_present_preserve_gl_state(self):
        arm=ArmRuntime()
        graphics=None
        try:
            with patch.dict('os.environ',{'SDL_VIDEODRIVER':'offscreen','SDL_AUDIODRIVER':'dummy'}):
                graphics=Graphics(arm,1000,700,hidden=True,logical_size=(800,480))
            gl=graphics.gl
            top,bottom=(20,180,40),(180,40,20)
            data=bytes(top)*800*240+bytes(bottom)*800*240
            gl.glPixelStorei(0x0d05,8)
            gl.glPixelStorei(0x0d02,810)
            gl.glPixelStorei(0x0d03,2)
            gl.glPixelStorei(0x0d04,3)
            gl.glColorMask(0,0,0,0)
            graphics.draw_video(data)
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'frame.png'
                graphics.screenshot(path)
                with Image.open(path) as image:
                    self.assertEqual(image.size,(800,480))
                    self.assertEqual(image.getpixel((0,0)),top)
                    self.assertEqual(image.getpixel((799,479)),bottom)
            for parameter,expected in ((0x0d05,8),(0x0d02,810),(0x0d03,2),(0x0d04,3)):
                value=C.c_int()
                gl.glGetIntegerv(parameter,C.byref(value))
                self.assertEqual(value.value,expected)
            # Inspect the drawable before swap, because the back-buffer's
            # contents after swap are undefined by OpenGL.
            with patch.object(graphics.sdl,'SDL_GL_SwapWindow',return_value=None):
                graphics.present()
            binding=C.c_int()
            gl.glGetIntegerv(0x8ca6,C.byref(binding))
            self.assertEqual(binding.value,graphics.framebuffer)
            mask=(C.c_int*4)()
            gl.glGetIntegerv(0x0c23,C.byref(mask))
            self.assertEqual(list(mask),[0,0,0,0])
            gl.glBindFramebuffer(0x8d40,0)
            gl.glReadBuffer(0x405)
            gl.glPixelStorei(0x0d05,1)
            for parameter in (0x0d02,0x0d03,0x0d04):gl.glPixelStorei(parameter,0)
            def pixel(x,y):
                buffer=C.create_string_buffer(3)
                gl.glReadPixels(x,y,1,1,0x1907,0x1401,C.addressof(buffer))
                return tuple(buffer.raw)
            self.assertEqual(pixel(500,20),(0,0,0))
            self.assertEqual(pixel(500,680),(0,0,0))
            self.assertEqual(pixel(500,600),top)
            self.assertEqual(pixel(500,100),bottom)
            graphics.begin_frame()
            self.assertEqual(gl.glGetError(),0)
        finally:
            if graphics:graphics.close()
            arm.close()


class DesktopEventTests(unittest.TestCase):
    def make_graphics(self, data):
        from unittest.mock import Mock
        graphics=Graphics.__new__(Graphics)
        graphics.width,graphics.height=800,480
        graphics.window_size=graphics.drawable_size=(1000,700)
        graphics.viewport=Graphics.viewport_for((800,480),graphics.drawable_size)
        graphics._mouse_touch=graphics._fullscreen_enter=False
        graphics.mouse_captured=False
        graphics.update_drawable=Mock()
        graphics.toggle_fullscreen=Mock()
        graphics.sdl=Mock()
        queued=list(data)
        def poll(buffer):
            if not queued:return 0
            C.memmove(buffer,queued.pop(0),64)
            return 1
        graphics.sdl.SDL_PollEvent.side_effect=poll
        return graphics

    def data(self,kind,**values):
        buffer=bytearray(64)
        struct=__import__('struct')
        struct.pack_into('<I',buffer,0,kind)
        for key,value in values.items():
            offset,format={'key':(20,'i'),'modifiers':(24,'H'),'button':(16,'B'),
                           'x':(20,'i'),'y':(24,'i'),'window_event':(12,'B'),
                           'instance':(8,'i'),'axis':(12,'B'),'value':(16,'h'),
                           'dx':(28,'i'),'dy':(32,'i')}[key]
            struct.pack_into('<'+format,buffer,offset,value)
        return bytes(buffer)

    def test_alt_enter_consumes_keyup_even_after_alt_released(self):
        graphics=self.make_graphics([self.data(0x300,key=13,modifiers=0x100),
                                     self.data(0x301,key=13,modifiers=0)])
        self.assertEqual(list(graphics.events()),[])
        graphics.toggle_fullscreen.assert_called_once_with()
        self.assertFalse(graphics._fullscreen_enter)

    def test_mouse_hit_targets_resize_and_drag_release_outside_letterbox(self):
        graphics=self.make_graphics([self.data(0x401,button=1,x=500,y=10),
                                     self.data(0x200,window_event=6),
                                     self.data(0x401,button=1,x=500,y=350),
                                     self.data(0x402,button=1,x=500,y=10)])
        self.assertEqual(list(graphics.events()),[('resize',1000,700),
                         ('touch',True,400,240),('touch',False,400,0)])
        graphics.update_drawable.assert_called_once_with()

    def test_controller_axis_sdl_payload(self):
        graphics=self.make_graphics([self.data(0x650,instance=7,axis=4,value=20000)])
        self.assertEqual(list(graphics.events()),[('controller_axis',7,4,20000)])

    def test_captured_clicks_ignore_absolute_position_and_never_drag_touch(self):
        graphics=self.make_graphics([self.data(0x401,button=1,x=-200,y=2000),
                                     self.data(0x400,x=-300,y=2100,dx=-100,dy=100),
                                     self.data(0x402,button=1,x=-300,y=2100)])
        graphics.mouse_captured=True
        graphics._mouse_touch=True  # A drag started before capture.
        self.assertEqual(list(graphics.events()),[('mouse_button',True,1),
                         ('mouse_delta',-100,100),('mouse_button',False,1)])

    def test_capture_centers_hidpi_pointer_hides_and_grabs_then_restores(self):
        from unittest.mock import call
        graphics=self.make_graphics([])
        graphics.window=123
        graphics.drawable_size=(2000,1400)
        graphics.sdl.SDL_SetRelativeMouseMode.return_value=0
        graphics._mouse_touch=True
        graphics.capture_mouse(True)
        self.assertTrue(graphics.mouse_captured)
        self.assertFalse(graphics._mouse_touch)
        self.assertEqual(graphics.sdl.mock_calls,[
            call.SDL_WarpMouseInWindow(123,500,350),
            call.SDL_SetRelativeMouseMode(1),call.SDL_SetWindowGrab(123,1),
            call.SDL_ShowCursor(0)])
        graphics.sdl.reset_mock()
        graphics.capture_mouse(False)
        self.assertFalse(graphics.mouse_captured)
        self.assertEqual(graphics.sdl.mock_calls,[call.SDL_SetRelativeMouseMode(0),
                         call.SDL_SetWindowGrab(123,0),call.SDL_ShowCursor(1)])
