"""Display quality: supersampling, MSAA, texture filters, widescreen and filters."""
import ctypes as C
import os
import struct
import unittest
from unittest.mock import patch

from re4pc.__main__ import argument_parser
from re4pc.arm import ArmRuntime
from re4pc.bionic import float_out
from re4pc.display import Display, surface_width
from re4pc.graphics import Graphics
from re4pc.postprocess import FRAGMENTS, PostProcess
from re4pc.settings import validate

ORTHO = (2/800, 0, 0, 0, 0, 2/480, 0, 0, 0, 0, -1, 0, -1, -1, 0, 1)
PERSPECTIVE = (1.45, 0, 0, 0, 0, 2.414, 0, 0, 0, 0, -1.001, -1, 0, 0, -2.001, 0)


class DisplayMappingTests(unittest.TestCase):
    def test_surface_widths_and_settings(self):
        self.assertEqual(surface_width('original'), 800)
        self.assertEqual(surface_width('16:9'), 854)
        self.assertEqual(surface_width('21:9'), 1120)
        defaults = validate({})
        self.assertEqual((defaults['render_scale'], defaults['msaa'], defaults['texture_filtering'],
                          defaults['display_filter'], defaults['aspect_ratio']),
                         (1, 0, 'original', 'bilinear', 'original'))
        for name, value in (('render_scale', 5), ('render_scale', True), ('msaa', 3), ('texture_filtering', 'x'),
                            ('display_filter', 'blur'), ('aspect_ratio', '4:3')):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                validate({name: value})

    def test_cli_overrides(self):
        args = argument_parser().parse_args(['run', '--render-scale', '3', '--msaa', '8', '--texture-filtering',
                                             'anisotropic', '--display-filter', 'crt', '--aspect-ratio', '21:9'])
        self.assertEqual((args.render_scale, args.msaa, args.texture_filtering, args.display_filter, args.aspect_ratio),
                         (3, 8, 'anisotropic', 'crt', '21:9'))
        self.assertIsNone(argument_parser().parse_args(['run']).render_scale)

    def test_launcher_labels_roundtrip_to_saved_values(self):
        from re4pc.launcher_ui import GRAPHICS_CHOICES, collect_settings
        values = validate({})
        for key, labels in GRAPHICS_CHOICES.items():
            for value, label in labels.items():
                with self.subTest(key=key, value=value):
                    self.assertEqual(collect_settings(values, {key: label}, {}, None)[key], value)

    def test_rectangles_scale_and_only_full_width_ones_widen(self):
        display = Display({'render_scale': 2, 'aspect_ratio': '16:9'})
        self.assertEqual(display.map((0, 0, 800, 480)), (54, 0, 1600, 960))
        self.assertEqual(display.map((0, 0, 800, 480), wide=True), (0, 0, 1708, 960))
        self.assertEqual(display.map((0, 0, 799, 480), wide=True), (0, 0, 1706, 960))
        self.assertEqual(display.map((10, 20, 100, 50), wide=True), (74, 40, 200, 100))
        self.assertEqual(Display().map((3, 4, 5, 6), wide=True), (3, 4, 5, 6))

    def test_widescreen_corrects_only_perspective_projections(self):
        display = Display({'aspect_ratio': '16:9'})
        perspective, matrix = display.projection(PERSPECTIVE)
        self.assertTrue(perspective)
        self.assertAlmostEqual(matrix[0], 1.45*800/854, places=5)
        self.assertEqual(matrix[1:], tuple(C.c_float(v).value for v in PERSPECTIVE[1:]))
        perspective, matrix = display.projection(ORTHO)
        self.assertFalse(perspective)
        self.assertEqual(matrix, tuple(C.c_float(v).value for v in ORTHO))
        self.assertEqual(Display().projection(PERSPECTIVE)[1][0], C.c_float(1.45).value)


class SurfaceTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SDL_VIDEODRIVER': 'offscreen', 'SDL_AUDIODRIVER': 'dummy'})
        self.env.start()
        self.arm = ArmRuntime()
        self.graphics = None

    def tearDown(self):
        if self.graphics:
            self.graphics.close()
        self.arm.close()
        self.env.stop()

    def open(self, **settings):
        display = Display(settings)
        self.graphics = Graphics(self.arm, 800, 480, hidden=True, logical_size=(800, 480), display=display)
        self.graphics.begin_frame()
        return self.graphics

    def matrix(self, values):
        pointer = self.arm.alloc(64)
        self.arm.write(pointer, struct.pack('<16f', *values))
        return pointer

    def triangle(self, mode, color, vertices, projection=ORTHO):
        """Submit an untextured triangle through the engine's GL imports."""
        call, imports = self.arm.call, self.arm.imports
        identity = self.matrix((1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1))
        call(imports['glMatrixMode'], 0x1701)
        call(imports['glLoadMatrixf'], self.matrix(projection))
        call(imports['glMatrixMode'], 0x1700)
        call(imports['glLoadMatrixf'], identity)
        data = self.arm.alloc(len(vertices)*4)
        self.arm.write(data, struct.pack(f'<{len(vertices)}f', *vertices))
        call(imports['glDisable'], 0x0de1)
        call(imports['glDisable'], 0x0b71)
        call(imports['glEnableClientState'], 0x8074)
        call(imports['glVertexPointer'], 3, 0x1406, 0, data)
        call(imports['glColor4f'], *(float_out(v) for v in color))
        call(imports['glDrawArrays'], mode, 0, len(vertices)//3)

    def test_scaled_msaa_surface_renders_engine_coordinates(self):
        graphics = self.open(render_scale=2, msaa=4)
        self.assertEqual(graphics.render_size, (1600, 960))
        self.assertGreaterEqual(graphics.samples, 2)
        viewport = (C.c_int*4)()
        graphics.gl.glGetIntegerv(0x0ba2, viewport)
        self.assertEqual(list(viewport), [0, 0, 1600, 960])
        self.arm.call(self.arm.imports['glScissor'], 0, 0, 400, 240)
        graphics.gl.glGetIntegerv(0x0c10, viewport)
        self.assertEqual(list(viewport), [0, 0, 800, 480])
        self.arm.call(self.arm.imports['glScissor'], 0, 0, 800, 480)
        graphics.gl.glClearColor(0, 0, 0, 1)
        graphics.gl.glClear(0x4100)
        self.triangle(4, (1, 1, 1, 1), (0, 0, 0, 800, 0, 0, 0, 480, 0))
        image = graphics.capture_image()
        self.assertEqual(image.size, (1600, 960))
        self.assertEqual(image.getpixel((40, 920)), (255, 255, 255))
        self.assertEqual(image.getpixel((1560, 40)), (0, 0, 0))
        # Multisampling blends coverage along the diagonal edge.
        edge = {image.getpixel((x, round(x*960/1600))) for x in range(200, 1400, 7)}
        self.assertTrue(any(0 < value[0] < 255 for value in edge), edge)
        self.assertEqual(graphics.gl.glGetError(), 0)
        data = bytes((10, 200, 30))*800*480
        graphics.draw_video(data)
        image = graphics.capture_image()
        self.assertEqual(image.getpixel((0, 0)), (10, 200, 30))
        self.assertEqual(image.getpixel((1599, 959)), (10, 200, 30))

    def test_widescreen_margins_cover_and_input_mapping(self):
        graphics = self.open(aspect_ratio='16:9')
        self.assertEqual(graphics.render_size, (854, 480))
        graphics.gl.glClearColor(0, 0, 0, 1)
        graphics.gl.glClear(0x4100)
        # A 3D perspective draw fills the widened viewport into both margins.
        self.triangle(5, (0, 1, 0, 1), (-50, -50, -2, 50, -50, -2, -50, 50, -2, 50, 50, -2), PERSPECTIVE)
        image = graphics.capture_image()
        self.assertEqual(image.getpixel((2, 240)), (0, 255, 0))
        self.assertEqual(image.getpixel((851, 240)), (0, 255, 0))
        # A textured-off full-screen ortho quad (a fade) covers the margins too...
        self.triangle(5, (1, 0, 0, 1), (0, 0, 0, 800, 0, 0, 0, 480, 0, 800, 480, 0))
        image = graphics.capture_image()
        self.assertEqual(image.getpixel((2, 240)), (255, 0, 0))
        # ...but a smaller HUD quad keeps logical coordinates inside the 5:3 area.
        self.triangle(5, (0, 0, 1, 1), (0, 0, 0, 100, 0, 0, 0, 100, 0, 100, 100, 0))
        image = graphics.capture_image()
        self.assertEqual(image.getpixel((28, 478)), (0, 0, 255))
        self.assertEqual(image.getpixel((25, 478)), (255, 0, 0))
        self.assertEqual(graphics.capture_image(engine_area=True).size, (800, 480))
        graphics.window_size = graphics.drawable_size = (854, 480)
        graphics.viewport = Graphics.viewport_for((graphics.surface_width, 480), graphics.drawable_size)
        self.assertEqual(graphics.map_point(27, 10), (0, 10))
        self.assertIsNone(graphics.map_point(10, 10))
        self.assertEqual(graphics.map_point(10, 10, clamp=True), (0, 10))
        self.assertEqual(graphics.gl.glGetError(), 0)

    def test_texture_filtering_generates_complete_mipmaps(self):
        graphics = self.open(texture_filtering='anisotropic')
        gl = graphics.gl
        texture = C.c_uint()
        gl.glGenTextures(1, C.byref(texture))
        gl.glBindTexture(0x0de1, texture.value)
        pixels = self.arm.alloc(16*16*4)
        self.arm.write(pixels, bytes(range(256))*4)
        self.arm.call(self.arm.imports['glTexImage2D'], 0x0de1, 0, 0x1908, 16, 16, 0, 0x1908, 0x1401, pixels)
        self.arm.call(self.arm.imports['glTexParameterf'], 0x0de1, 0x2801, float_out(0x2600))
        self.arm.call(self.arm.imports['glTexParameterf'], 0x0de1, 0x2800, float_out(0x2600))
        value = C.c_int()
        gl.glGetTexParameteriv(0x0de1, 0x2801, C.byref(value))
        self.assertEqual(value.value, 0x2703)  # LINEAR_MIPMAP_LINEAR
        gl.glGetTexParameteriv(0x0de1, 0x2800, C.byref(value))
        self.assertEqual(value.value, 0x2601)
        gl.glGetTexLevelParameteriv(0x0de1, 4, 0x1000, C.byref(value))  # 1x1 level exists
        self.assertEqual(value.value, 1)
        self.assertEqual(gl.glGetError(), 0)

    def test_original_filters_pass_through(self):
        graphics = self.open()
        texture = C.c_uint()
        graphics.gl.glGenTextures(1, C.byref(texture))
        graphics.gl.glBindTexture(0x0de1, texture.value)
        self.arm.call(self.arm.imports['glTexParameterf'], 0x0de1, 0x2801, float_out(0x2600))
        value = C.c_int()
        graphics.gl.glGetTexParameteriv(0x0de1, 0x2801, C.byref(value))
        self.assertEqual(value.value, 0x2600)

    def test_every_display_filter_compiles_and_draws(self):
        graphics = self.open()
        gl = graphics.gl
        width, height = 64, 32
        source = C.c_uint()
        gl.glGenTextures(1, C.byref(source))
        gl.glBindTexture(0x0de1, source.value)
        # Left half dark, right half light: a hard vertical edge.
        rows = (bytes((40, 40, 40, 255))*(width//2) + bytes((220, 220, 220, 255))*(width//2))*height
        buffer = C.create_string_buffer(rows)
        gl.glTexImage2D(0x0de1, 0, 0x8058, width, height, 0, 0x1908, 0x1401, C.addressof(buffer))
        for parameter, value in ((0x2801, 0x2601), (0x2800, 0x2601), (0x2802, 0x812f), (0x2803, 0x812f)):
            gl.glTexParameteri(0x0de1, parameter, value)
        out = {}
        for name in FRAGMENTS:
            with self.subTest(filter=name):
                post = PostProcess(gl, name)
                gl.glBindFramebuffer(0x8d40, graphics.resolve_framebuffer)
                post.draw(source.value, (width, height), (0, 0, width*2, height*2), (width, height))
                pixels = C.create_string_buffer(width*2*height*2*3)
                gl.glReadPixels(0, 0, width*2, height*2, 0x1907, 0x1401, C.addressof(pixels))
                out[name] = [pixels.raw[(y*width*2+x)*3] for y in (10,) for x in range(width*2)] + \
                            [pixels.raw[(y*width*2+10)*3] for y in range(height*2)]
                self.assertEqual(gl.glGetError(), 0)
                post.close()
        row = lambda name: out[name][:width*2]
        column = lambda name: out[name][width*2:]
        self.assertLess(min(row('sharpen')[:64]), 40)  # undershoot beside the edge
        self.assertGreater(max(row('sharpen')[64:]), 220)
        self.assertEqual(row('sharpen')[0], 40)  # flat areas are unchanged
        self.assertEqual(set(row('pixel')[:60]), {40})
        self.assertEqual((row('fxaa')[0], row('fxaa')[-1]), (40, 220))
        self.assertLess(min(column('crt')), 0.8*max(column('crt')))  # alternating scanlines


if __name__ == '__main__':
    unittest.main()
