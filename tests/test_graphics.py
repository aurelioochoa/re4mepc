"""Exercise movie compositing against a real offscreen OpenGL context."""
import ctypes as C
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from re4pc.arm import ArmRuntime
from re4pc.graphics import Graphics


class VideoOverlayTests(unittest.TestCase):
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
                           'instance':(8,'i'),'axis':(12,'B'),'value':(16,'h')}[key]
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
