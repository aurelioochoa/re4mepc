"""Real GL snapshots: intermediate motion, pointer ownership and state isolation."""
import ctypes as C
import os
import struct
import time
import unittest
from unittest.mock import patch

from re4pc.arm import ArmRuntime
from re4pc.graphics import Graphics
from re4pc.render_stream import RenderStream


class RenderStreamTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'SDL_VIDEODRIVER': 'offscreen', 'SDL_AUDIODRIVER': 'dummy'})
        self.environment.start()
        self.arm = ArmRuntime()
        self.graphics = Graphics(self.arm, 320, 240, hidden=True, logical_size=(320, 240))
        self.stream = self.graphics.render_stream = RenderStream()
        self.gl = self.graphics.gl
        self.vertices = (C.c_float*9)(-.15, -.2, 0, .15, -.2, 0, 0, .2, 0)
        self.indices = (C.c_ushort*3)(0, 1, 2)
        self.matrix = (C.c_float*16)(1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1)
        self.gl.glMatrixMode(0x1701)
        self.gl.glLoadMatrixf(C.addressof(self.matrix))
        for cap in (0x0b50, 0x0b60, 0x0b71, 0x0be2, 0x0bc0, 0x0c11):
            self.gl.glDisable(cap)
        self.gl.glEnableClientState(0x8074)
        self.gl.glVertexPointer(3, 0x1406, 0, C.addressof(self.vertices))
        self.gl.glColor4f(1, 0, 0, 1)

    def tearDown(self):
        self.graphics.close()
        self.arm.close()
        self.environment.stop()

    def capture(self, x=0):
        self.stream.begin()
        self.gl.glClearColor(0, 0, 0, 1)
        self.stream.clear(0x4100)
        self.gl.glClear(0x4100)
        self.matrix[12] = x
        self.gl.glMatrixMode(0x1700)
        self.gl.glLoadMatrixf(C.addressof(self.matrix))
        self.stream.draw('glDrawElements', (4, 3, 0x1403, C.addressof(self.indices)))
        self.gl.glDrawElements(4, 3, 0x1403, C.addressof(self.indices))
        self.stream.end()
        return self.graphics.capture_image()

    @staticmethod
    def center(image):
        points = [(x, y) for y in range(image.height) for x in range(image.width)
                  if image.getpixel((x,y))[0] > 200]
        return sum(x for x,y in points)/len(points)

    def test_geometry_moves_at_intermediate_time_and_owned_arrays_survive_mutation(self):
        before = self.capture(-.5)
        after = self.capture(.5)
        original = bytes(self.vertices)
        # A native stack or streaming buffer can already hold next tick's data.
        self.vertices[0] = 100
        self.indices[0] = 2
        self.assertEqual(self.stream.render(.5), 2)
        middle = self.graphics.capture_image()
        self.assertAlmostEqual(self.center(middle), (self.center(before)+self.center(after))/2, delta=1)
        self.assertNotEqual(middle.tobytes(), before.tobytes())
        self.assertNotEqual(middle.tobytes(), after.tobytes())
        self.assertEqual(self.vertices[0], 100)
        self.assertNotEqual(bytes(self.vertices), original)
        self.assertEqual(self.stream.render(1), 2)
        self.assertEqual(self.graphics.capture_image().tobytes(), after.tobytes())
        self.assertEqual(self.gl.glGetError(), 0)

    def test_projection_texture_lifecycle_and_topology_changes_snap(self):
        self.capture(-.5)
        self.indices[0] = 1
        self.capture(.5)
        self.assertEqual(self.stream.render(.5), 1)
        self.stream.dirty()
        self.assertEqual(self.stream.render(.5), 0)
        self.capture()
        self.assertEqual(self.stream.render(.5), 1)

    def test_skinning_vertices_interpolate_without_changing_driver_or_guest_state(self):
        self.capture()
        for i in range(0, 9, 3): self.vertices[i] += .5
        current = self.capture()
        self.gl.glColorMask(0, 1, 0, 0)
        self.gl.glMatrixMode(0x1701)
        self.gl.glClientActiveTexture(0x84c1)
        self.gl.glActiveTexture(0x84c1)
        self.gl.glPixelStorei(0x0d05, 8)
        guest = self.arm.read(self.arm.base, 4096)
        self.assertEqual(self.stream.render(.5), 2)
        self.assertLess(self.center(self.graphics.capture_image()), self.center(current))
        mask = (C.c_int*4)()
        self.gl.glGetIntegerv(0x0c23, mask)
        self.assertEqual(list(mask), [0, 1, 0, 0])
        for enum, expected in ((0x0ba0,0x1701),(0x84e0,0x84c1),(0x84e1,0x84c1),(0x0d05,8)):
            value=C.c_int(); self.gl.glGetIntegerv(enum,C.byref(value)); self.assertEqual(value.value,expected)
        self.assertEqual(self.arm.read(self.arm.base,4096),guest)
        self.assertEqual(self.gl.glGetError(), 0)

    def test_oversized_draw_is_rejected_and_never_copies_arbitrary_memory(self):
        self.stream.begin()
        self.stream.clear(0x4100)
        self.stream.draw('glDrawArrays', (4, 0, 1000000000))
        self.stream.end()
        self.assertEqual(self.stream.render(), 0)
        self.assertEqual(self.stream.metrics()['rejected_draws'], 1)

    def scene(self, draws, mask=0x4100):
        """Draw independent objects; the red object is the motion oracle."""
        self.stream.begin()
        self.gl.glClearColor(0, 0, 0, 1)
        self.stream.clear(mask)
        self.gl.glClear(mask)
        for vertices, x, red in draws:
            self.matrix[12] = x
            self.gl.glMatrixMode(0x1700)
            self.gl.glLoadMatrixf(C.addressof(self.matrix))
            self.gl.glVertexPointer(3, 0x1406, 0, C.addressof(vertices))
            self.gl.glColor4f(red, 1-red, 0, 1)
            self.stream.draw('glDrawElements', (4, 3, 0x1403, C.addressof(self.indices)))
            self.gl.glDrawElements(4, 3, 0x1403, C.addressof(self.indices))
        self.stream.end()
        return self.graphics.capture_image()

    def test_visibility_changes_and_reordering_preserve_surviving_object_motion(self):
        a, b = (C.c_float*9)(*self.vertices), (C.c_float*9)(*self.vertices)
        for old, new in (
                ([(self.vertices, -.5, 1)], [(a, 2, 0), (self.vertices, .5, 1)]),
                ([(a, 2, 0), (self.vertices, -.5, 1)], [(self.vertices, .5, 1)]),
                ([(a, 2, 0), (self.vertices, -.5, 1), (b, 2, 0)],
                 [(b, 2, 0), (a, 2, 0), (self.vertices, .5, 1)])):
            with self.subTest(draw_counts=(len(old), len(new))):
                self.stream.reset()
                before, after = self.scene(old), self.scene(new)
                self.assertEqual(self.stream.render(.5), 2)
                middle = self.graphics.capture_image()
                self.assertAlmostEqual(self.center(middle), (self.center(before)+self.center(after))/2, delta=1)
                metrics = self.stream.metrics()
                for alpha in (.1, .5, 1): self.stream.render(alpha)
                self.assertEqual(self.stream.metrics()['matched_draws'], metrics['matched_draws'])
                self.assertEqual(self.graphics.capture_image().tobytes(), after.tobytes())
                self.assertEqual(self.gl.glGetError(), 0)
        self.assertGreaterEqual(self.stream.metrics()['changed_sequences'], 2)

    def test_reused_geometry_with_ambiguous_instances_snaps(self):
        for old, new in (
                ([(self.vertices, -.5, 1), (self.vertices, -.25, 1)], [(self.vertices, .5, 1)]),
                ([(self.vertices, -.5, 1)], [(self.vertices, .25, 1), (self.vertices, .5, 1)])):
            self.stream.reset()
            self.scene(old)
            expected = self.scene(new)
            self.assertEqual(self.stream.render(.5), 1)
            self.assertEqual(self.graphics.capture_image().tobytes(), expected.tobytes())

    def test_engine_draws_after_replay_and_snapshot_release_use_restored_arrays(self):
        self.gl.glIsEnabled.argtypes, self.gl.glIsEnabled.restype = (C.c_uint,), C.c_ubyte
        for enabled in (True, False):
            with self.subTest(vertex_array_enabled=enabled):
                expected = self.capture(.5)
                self.assertIsNotNone(expected.getchannel('R').getbbox())
                if not enabled:
                    self.gl.glDisableClientState(0x8074)
                self.stream.render(1)
                self.assertEqual(bool(self.gl.glIsEnabled(0x8074)), enabled)
                self.stream.reset()  # Free the replay's copied client arrays.
                self.gl.glEnableClientState(0x8074)
                # The engine keeps its original pointer across presentation.
                self.assertEqual(self.capture(.5).tobytes(), expected.tobytes())

    def instance_scene(self, draws, *, skinned=False, camera=0):
        """Instances reuse one mesh or overwrite one skinning scratch buffer."""
        original = list(self.vertices)
        self.stream.begin()
        self.gl.glClearColor(0, 0, 0, 1)
        self.stream.clear(0x4100)
        self.gl.glClear(0x4100)
        for source, x, red in draws:
            self.stream.source, self.stream.part = source, 0
            for i, value in enumerate(original):
                self.vertices[i] = value + (x if skinned and i % 3 == 0 else 0)
            self.matrix[12] = camera + (0 if skinned else x)
            self.gl.glMatrixMode(0x1700)
            self.gl.glLoadMatrixf(C.addressof(self.matrix))
            self.gl.glVertexPointer(3, 0x1406, 0, C.addressof(self.vertices))
            self.gl.glColor4f(red, 1-red, 0, 1)
            self.stream.draw('glDrawElements', (4, 3, 0x1403, C.addressof(self.indices)))
            self.gl.glDrawElements(4, 3, 0x1403, C.addressof(self.indices))
        self.stream.end()
        image = self.graphics.capture_image()
        self.vertices[:] = original
        return image

    def assert_instance_motion(self, skinned):
        before = self.instance_scene([(11, -.5, 1), (22, .55, 0)], skinned=skinned)
        # Reorder shared instances while camera and object both move.
        after = self.instance_scene([(22, .45, 0), (11, .1, 1)], skinned=skinned, camera=.1)
        self.assertEqual(self.stream.render(.5), 2)
        middle = self.graphics.capture_image()
        self.assertAlmostEqual(self.center(middle), (self.center(before)+self.center(after))/2, delta=1)
        self.assertEqual(self.stream.render(0), 2)
        self.assertEqual(self.graphics.capture_image().tobytes(), before.tobytes())
        self.stream.render(1)
        self.assertEqual(self.graphics.capture_image().tobytes(), after.tobytes())
        self.assertEqual(self.gl.glGetError(), 0)

    def test_instance_identity_keeps_shared_meshes_smooth(self):
        self.assert_instance_motion(False)

    def test_instance_identity_keeps_shared_skinning_buffers_smooth(self):
        self.assert_instance_motion(True)

    def test_instance_visibility_and_lifetime_never_blend_different_objects(self):
        self.instance_scene([(11, -.5, 1), (22, .5, 0)])
        after = self.instance_scene([(11, .1, 1)])
        self.assertEqual(self.stream.render(.5), 2)
        self.assertLess(self.center(self.graphics.capture_image()), self.center(after))
        # Same pointer/topology, but a new lifetime token after destruction.
        replacement = self.instance_scene([(33, .5, 1)])
        self.assertEqual(self.stream.render(.5), 1)
        self.assertEqual(self.graphics.capture_image().tobytes(), replacement.tobytes())

    def test_engine_model_scopes_retire_lifetimes_and_restore_after_return(self):
        def code(name, words):
            pointer = self.arm.alloc(len(words)*4)
            self.arm.write(pointer, struct.pack('<'+'I'*len(words), *words))
            self.arm.symbols[name] = pointer
            self.arm.symbol_sizes[name] = len(words)*4
            return pointer

        for name in ('_ZN16GM_Element_Model4InitEv', '_ZN16GM_Element_Model4TermEv',
                     '_ZN16GM_Element_ModelD1Ev'):
            code(name, [0xe12fff1e])  # bx lr
        observed = []
        draw = self.arm.register('observe_source', lambda *_: observed.append(self.stream.source) or 0)
        model_draw = code('_ZN16GM_Element_Model4DrawEv',
                          [0xe92d4000, 0xe59fc004, 0xe12fff3c, 0xe8bd8000, draw])
        direct_draw = code('_ZN16GM_Element_Model11Direct_DrawEP12tagTransform',
                           [0xe92d4000, 0xe59fc004, 0xe12fff3c, 0xe8bd8000, draw])
        code('model_caller', [0xe92d4000, 0xe59fc004, 0xe12fff3c, 0xe8bd8000, model_draw])
        code('direct_caller', [0xe92d4000, 0xe59fc004, 0xe12fff3c, 0xe8bd8000, direct_draw])
        model = self.arm.alloc(16)
        self.stream.arm = self.arm
        self.stream._install_sources()

        def submit():
            self.stream.begin()
            self.arm.call('model_caller', model)
            self.assertEqual(self.stream.source, 0, 'Source leaked beyond model return')

        submit()
        self.assertGreater(observed[-1], 0)
        submit()
        self.assertEqual(observed[-1], observed[-2])
        self.arm.call('direct_caller', model)
        self.assertEqual(observed[-1], observed[-2], 'Direct draw lost model identity')
        self.assertEqual(self.stream.source, 0)
        self.arm.call('_ZN16GM_Element_Model4TermEv', model)
        submit()
        self.assertNotEqual(observed[-1], observed[-2], 'Reused allocation retained destroyed model history')

    def test_history_does_not_cross_clear_boundaries_or_camera_cuts(self):
        self.scene([(self.vertices, -.5, 1)])
        self.scene([(self.vertices, .5, 1)], mask=0x4000)
        self.assertEqual(self.stream.render(.5), 1)
        self.capture(-.5)
        self.stream.begin()
        self.stream.clear(0x4100)
        self.stream.clear(0x0100)
        self.matrix[12] = .5
        self.gl.glMatrixMode(0x1700)
        self.gl.glLoadMatrixf(C.addressof(self.matrix))
        self.stream.draw('glDrawElements', (4, 3, 0x1403, C.addressof(self.indices)))
        self.stream.end()
        self.assertEqual(self.stream.render(.5), 1)
        self.capture(300)
        self.capture(-300)
        self.assertEqual(self.stream.render(.5), 1)
        self.capture(0)
        self.matrix[0] = 2
        self.gl.glMatrixMode(0x1701)
        self.gl.glLoadMatrixf(C.addressof(self.matrix))
        self.capture(0)
        self.assertEqual(self.stream.render(.5), 1)

    def test_shared_context_presents_while_native_thread_is_busy_and_stops_cleanly(self):
        from re4pc.presentation import PresentationWorker
        self.capture(-.5)
        expected = self.capture(.5)
        guest = self.arm.read(self.arm.base,4096)
        worker = PresentationWorker(self.graphics,self.stream,120)
        try:
            worker.start()
            # Context readiness precedes Mesa's first replay/shader warm-up.
            deadline = time.monotonic()+5
            while not worker.frames and time.monotonic()<deadline:
                time.sleep(.01)
                worker.check()
            self.assertGreater(worker.frames, 0)
            frames = worker.frames
            time.sleep(.15)
            worker.check()
            self.assertGreaterEqual(worker.frames-frames,8)
            self.assertEqual(self.graphics.capture_image().tobytes(),expected.tobytes())
            self.assertEqual(self.arm.read(self.arm.base,4096),guest)
            self.stream.dirty()
            frames = worker.frames
            time.sleep(.03)
            self.assertEqual(worker.frames,frames)
        finally:
            worker.close()
        self.assertEqual(self.gl.glGetError(),0)

    def test_shared_context_can_present_complete_menu_and_movie_surfaces(self):
        from re4pc.presentation import PresentationWorker
        expected = self.capture(.5)
        self.stream.reset()
        self.stream.publish(self.graphics.width,self.graphics.height)
        worker = PresentationWorker(self.graphics,self.stream,60)
        captured = []
        worker.on_present = lambda: captured.append(worker.surface.capture_image()) if not captured else None
        try:
            worker.start()
            deadline = time.monotonic()+2
            while not captured and time.monotonic()<deadline:
                time.sleep(.01)
                worker.check()
            self.assertTrue(captured)
            self.assertEqual(captured[0].tobytes(),expected.tobytes())
        finally:
            worker.close()
        self.assertEqual(self.gl.glGetError(),0)
