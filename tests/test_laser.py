"""Sight settings and procedural visuals, using synthetic fixtures only."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from re4pc.laser import sight_image
from re4pc.settings import Settings, validate
from re4pc.launcher_ui import collect_settings, FieldError


class LaserSettingsTests(unittest.TestCase):
    def test_old_settings_default_to_unchanged_native_sight(self):
        values = validate({'sensitivity': 2})
        self.assertEqual((values['laser_shape'], values['laser_color'], values['laser_size']),
                         ('original', '#ff0000', 1.0))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'settings.json'
            for shape in ('original', 'circle', 'predator', 'black_matter'):
                saved = Settings.save({'laser_shape': shape, 'laser_color': '#12ABef', 'laser_size': 2.5}, path)
                self.assertEqual(Settings.load(path), saved)
                self.assertEqual(saved['laser_color'], '#12abef')

    def test_malformed_settings_rejected(self):
        for key, invalid in (
                ('laser_color', ['red', '#123', '#1234567', '#gg0000', '', None, [], 123]),
                ('laser_shape', ['alien', '', None, [], True]),
                ('laser_size', [0, .49, 3.01, True, float('nan'), float('inf'), '2'])):
            for value in invalid:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate({key: value})

    def test_launcher_parse_and_inline_errors(self):
        values = validate({})
        bindings = {(device, action): '' for device in values['bindings'] for action in values['bindings'][device]}
        result = collect_settings(values, {'laser_shape': 'Black Matter', 'laser_color': '#FF00AA',
                                           'laser_size': '1.5'}, bindings, Mock())
        self.assertEqual((result['laser_shape'], result['laser_color'], result['laser_size']),
                         ('black_matter', '#ff00aa', 1.5))
        for key, value in (('laser_color', 'red'), ('laser_size', 'nan'), ('laser_shape', 'alien')):
            with self.assertRaises(FieldError) as error:
                collect_settings(values, {key: value}, bindings, Mock())
            self.assertEqual(error.exception.field, key)


class SightImageTests(unittest.TestCase):
    def test_predator_has_three_separate_opaque_dots_centered_on_aim(self):
        image = sight_image('predator', '#00ff00', 100)
        # Flood-fill solid pixels. Glow must not join the three emitters.
        pixels = {(x, y) for y in range(100) for x in range(100) if image.getpixel((x, y))[3] == 255}
        groups = []
        while pixels:
            seed = pixels.pop()
            group, stack = {seed}, [seed]
            while stack:
                x, y = stack.pop()
                for neighbor in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                    if neighbor in pixels:
                        pixels.remove(neighbor)
                        stack.append(neighbor)
                        group.add(neighbor)
            groups.append(group)
        self.assertEqual(len(groups), 3)
        self.assertEqual(image.getpixel((50, 50))[3], 0)
        for x, y in ((50, 25), (28, 64), (72, 64)):
            r, g, b, a = image.getpixel((x, y))
            self.assertEqual((g, a), (255, 255))
            self.assertLess(r, g)
            self.assertLess(b, g)

    def test_black_matter_animates_and_color_changes_accents(self):
        first = sight_image('black_matter', '#00ff00', 64, 0)
        second = sight_image('black_matter', '#00ff00', 64, .25)
        tinted = sight_image('black_matter', '#ff0000', 64, 0)
        self.assertNotEqual(first.tobytes(), second.tobytes())
        self.assertNotEqual(first.tobytes(), tinted.tobytes())
        self.assertEqual(first.getpixel((32, 32)), (9, 3, 18, 255))
        self.assertEqual(first.getpixel((0, 0))[3], 0)
        self.assertEqual(first.tobytes(), sight_image('black_matter', '#00ff00', 64, 1).tobytes())

    def test_circle_uses_picked_color_and_transparent_corners(self):
        image = sight_image('circle', '#1267ef', 64)
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        self.assertEqual(image.getpixel((32, 32))[3], 255)
        self.assertGreater(image.getpixel((32, 32))[2], image.getpixel((32, 32))[0])


class LaserGLTests(unittest.TestCase):
    def setUp(self):
        import ctypes as C
        import struct
        from unittest.mock import patch
        from re4pc.arm import ArmRuntime
        from re4pc.graphics import Graphics
        from re4pc.laser import LaserSight
        self.arm = ArmRuntime()
        self.addCleanup(self.arm.close)
        with patch.dict('os.environ', {'SDL_VIDEODRIVER': 'offscreen', 'SDL_AUDIODRIVER': 'dummy'}):
            self.graphics = Graphics(self.arm, 800, 480, hidden=True)
        self.addCleanup(self.graphics.close)
        self.gl = self.graphics.gl
        self.sight = self.graphics.laser = LaserSight(self.graphics, {})
        self.vertices = self.arm.alloc(48)
        self.indices = self.arm.alloc(12)
        self.arm.write(self.vertices, struct.pack('<12f', -.5, .5, 0, .5, -.5, 0,
                                                 .5, .5, 0, -.5, -.5, 0))
        self.arm.write(self.indices, struct.pack('<6H', 0, 1, 2, 0, 3, 1))
        self.values = [4, 6, 0x1403, self.indices]
        self.gl.glVertexPointer(3, 0x1406, 0, self.vertices)
        self.gl.glEnableClientState(0x8074)
        self.gl.glDisableClientState(0x8076)
        self.gl.glDisableClientState(0x8078)
        self.gl.glDisable(0x0de1)
        self.gl.glEnable(0x0be2)
        self.gl.glBlendFunc(0x0302, 0x0303)
        self.gl.glEnable(0x0b71)
        self.gl.glDepthFunc(0x0203)
        self.gl.glClearDepth.argtypes = (C.c_double,)
        self.gl.glClearDepth(1)
        self.gl.glClearColor(0, 0, 0, 1)
        projection = (C.c_float*16)(1.448528, 0, 0, 0, 0, 2.414214, 0, 0,
                                    0, 0, -2001/1999, -1, 0, 0, -4000/1999, 0)
        self.gl.glMatrixMode(0x1701)
        self.gl.glLoadMatrixf(C.addressof(projection))
        self.gl.glMatrixMode(0x1700)

    def render(self, shape, depth=30, scale=1, intensity=1, alpha=1, moment=0):
        import ctypes as C
        from unittest.mock import patch
        from PIL import ImageChops
        self.sight.configure({'laser_shape': shape, 'laser_size': scale})
        self.sight.stage = 'dot'
        view = (C.c_float*16)(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, -depth, 1)
        self.gl.glMatrixMode(0x1700)
        self.gl.glLoadMatrixf(C.addressof(view))
        self.gl.glColor4f(intensity, intensity, intensity, alpha)
        self.gl.glClear(0x4000 | 0x0100)
        before = self.graphics.capture_image()
        with patch('time.monotonic', return_value=moment):
            if self.sight.custom:
                self.sight.draw(self.gl.glDrawElements, self.values)
            else:
                self.gl.glDrawElements(*self.values)
        image = self.graphics.capture_image()
        self.assertEqual(self.gl.glGetError(), 0)
        return image, ImageChops.difference(before, image).getbbox()

    def test_custom_artwork_inherits_native_geometry_and_perspective(self):
        import ctypes as C
        native_widths = []
        for depth in (30, 60, 120):
            _, bounds = self.render('original', depth)
            native_widths.append(bounds[2]-bounds[0])
        for shape in ('circle', 'predator', 'black_matter'):
            widths = []
            for index, depth in enumerate((30, 60, 120)):
                _, bounds = self.render(shape, depth)
                self.assertIsNotNone(bounds, (shape, depth))
                widths.append(bounds[2]-bounds[0])
                # All artwork is bounded by the actual native sight quad.
                self.assertLessEqual(widths[-1], native_widths[index])
                pointer = C.c_void_p()
                self.gl.glGetPointerv(0x808e, C.byref(pointer))
                self.assertEqual(pointer.value, self.vertices)
            self.assertGreater(widths[0], widths[1], (shape, widths))
            self.assertGreater(widths[1], widths[2], (shape, widths))
            _, scaled = self.render(shape, 120, 2)
            self.assertEqual(scaled[2]-scaled[0], widths[1])

    def test_native_fading_depth_and_alpha_are_preserved(self):
        for shape in ('circle', 'predator', 'black_matter'):
            full, _ = self.render(shape)
            for parameters in ({'alpha': .25}, {'intensity': .25}):
                faint, bounds = self.render(shape, **parameters)
                self.assertIsNotNone(bounds)
                light = lambda image: sum(sum(pixel) for pixel in image.getdata())
                self.assertGreater(light(faint), light(full)*.20)
                self.assertLess(light(faint), light(full)*.30)
            _, bounds = self.render(shape, alpha=0)
            self.assertIsNone(bounds)
            self.gl.glClearDepth(.25)
            _, bounds = self.render(shape)
            self.assertIsNone(bounds)
            self.gl.glClearDepth(1)

    def test_native_state_is_restored_and_animation_reaches_the_gpu(self):
        import ctypes as C
        self.gl.glMatrixMode(0x1702)
        texture = (C.c_float*16)(2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1, 0, .3, .2, 0, 1)
        self.gl.glLoadMatrixf(C.addressof(texture))
        self.gl.glActiveTexture(0x84c1)
        self.gl.glClientActiveTexture(0x84c1)
        for parameter, value in ((0x0cf5, 8), (0x0cf2, 109), (0x0cf3, 2), (0x0cf4, 3)):
            self.gl.glPixelStorei(parameter, value)
        self.render('predator', intensity=.5, alpha=.75)
        for parameter, expected in ((0x84e0, 0x84c1), (0x84e1, 0x84c1),
                                     (0x0ba0, 0x1700), (0x0b72, 1), (0x0b74, 0x0203),
                                     (0x0cf5, 8), (0x0cf2, 109), (0x0cf3, 2), (0x0cf4, 3)):
            value = C.c_int()
            self.gl.glGetIntegerv(parameter, C.byref(value))
            self.assertEqual(value.value, expected, hex(parameter))
        self.gl.glActiveTexture(0x84c0)
        restored = (C.c_float*16)()
        self.gl.glGetFloatv.argtypes = (C.c_uint, C.c_void_p)
        self.gl.glGetFloatv(0x0ba8, restored)
        self.assertEqual(list(restored), list(texture))
        color = (C.c_float*4)()
        self.gl.glGetFloatv(0x0b00, color)
        self.assertEqual(list(color), [.5, .5, .5, .75])
        first, _ = self.render('black_matter', moment=0)
        second, _ = self.render('black_matter', moment=.5)
        self.assertNotEqual(first.tobytes(), second.tobytes())
        self.assertEqual(len(self.sight.textures), 20)

    def test_scope_exit_never_adds_a_pointer_draw(self):
        from unittest.mock import Mock, patch
        self.sight.configure({'laser_shape': 'predator'})
        with patch.object(self.sight, '_draw_marker') as draw:
            self.sight._begin(None, 0, 0, None)
            self.sight._dot(None, 0, 0, None)
            self.sight._end(None, 0, 0, None)
        draw.assert_not_called()
        self.assertIsNone(self.sight.stage)
        self.sight.stage = 'dot'
        submit = Mock()
        with patch.object(self.sight, '_draw_marker') as draw:
            self.sight.draw(submit, [4, 0, 0x1403, 0])
        submit.assert_called_once_with(4, 0, 0x1403, 0)
        draw.assert_not_called()


from tests.test_launcher import LauncherGuiFixture


class LaserLauncherTests(LauncherGuiFixture):
    def open_view(self):
        from unittest.mock import patch
        with patch('re4pc.settings.Settings.load', return_value=validate({})):
            view = self.app.settings()
        view.select('Laser sight')
        self.window.update()
        return view

    def test_picker_cancel_reset_preview_and_saving(self):
        from unittest.mock import patch
        view = self.open_view()
        original = view.laser_photo
        with patch('tkinter.colorchooser.askcolor', return_value=((18, 52, 86), '#123456')):
            view.choose_laser_color()
        self.assertEqual(view.editors['laser_color'].get(), '#123456')
        self.assertIsNot(view.laser_photo, original)
        with patch('tkinter.colorchooser.askcolor', return_value=(None, None)):
            view.choose_laser_color()
        self.assertEqual(view.editors['laser_color'].get(), '#123456')
        view.editors['laser_shape'].set('Black Matter')
        view.editors['laser_size'].set('2.5')
        with patch('re4pc.settings.Settings.load', return_value=validate({})), patch('re4pc.settings.Settings.save') as save:
            view.save()
        saved = save.call_args.args[0]
        self.assertEqual((saved['laser_shape'], saved['laser_color'], saved['laser_size']),
                         ('black_matter', '#123456', 2.5))
        self.assertIsNone(view.laser_job)
        view = self.open_view()
        view.editors['laser_shape'].set('Predator')
        view.editors['laser_color'].set('#00ff00')
        view.reset_laser()
        self.assertEqual((view.editors['laser_shape'].get(), view.editors['laser_color'].get(),
                          view.editors['laser_size'].get()), ('Original', '#ff0000', '1.0'))
        view.window.destroy()

    def test_color_size_errors_stay_inline_and_buttons_do_not_overlap_fields(self):
        from unittest.mock import patch
        view = self.open_view()
        for geometry in ('1280x720', '640x520'):
            view.window.geometry(geometry)
            self.window.update()
            canvas = view.panes['Laser sight'].content
            def bounds(widget):
                item = next(item for item in canvas.find_all()
                            if canvas.type(item) == 'window' and canvas.itemcget(item, 'window') == str(widget))
                return canvas.bbox(item)
            size = bounds(view.fields['laser_size'][1])
            picker = bounds(view.laser_picker)
            self.assertGreaterEqual(picker[1], size[3])
            self.assertGreaterEqual(bounds(view.laser_preview)[1], picker[3])
        for key, invalid in (('laser_color', 'not-a-color'), ('laser_size', 'nan')):
            view.editors[key].set(invalid)
            with patch('re4pc.settings.Settings.save') as save:
                view.save()
            save.assert_not_called()
            self.assertTrue(view.fields[key][2].cget('text'))
            self.assertEqual(view.section, 'Laser sight')
            view.editors[key].set(validate({})[key])
        view.window.destroy()
