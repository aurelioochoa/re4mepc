"""Real GL snapshots: intermediate motion, pointer ownership and state isolation."""
import ctypes as C
import os
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

    def test_shared_context_presents_while_native_thread_is_busy_and_stops_cleanly(self):
        from re4pc.presentation import PresentationWorker
        self.capture(-.5)
        expected = self.capture(.5)
        guest = self.arm.read(self.arm.base,4096)
        worker = PresentationWorker(self.graphics,self.stream,120)
        try:
            worker.start()
            time.sleep(.15)
            worker.check()
            self.assertGreaterEqual(worker.frames,8)
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
