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
