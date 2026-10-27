"""Native GL imports preserve the Python bridge's GLES1 calling convention."""
import ctypes as C
import os
import struct
import unittest
from unittest.mock import patch

from re4pc.arm import ArmRuntime
from re4pc.bionic import float_out
from re4pc.diagnostics import Diagnostics
from re4pc.gl_bridge import GLBridge
from re4pc.graphics import Graphics


class GLBridgeTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SDL_VIDEODRIVER':'offscreen','SDL_AUDIODRIVER':'dummy'})
        self.env.start()
        self.arm = ArmRuntime(diagnostics=Diagnostics())
        self.graphics = Graphics(self.arm, 320, 240, hidden=True, logical_size=(320,240))
        self.bridge = self.arm.graphics_bridge = GLBridge(self.arm)
        self.identity = self.arm.alloc(64)
        self.arm.write(self.identity,struct.pack('<16f',1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1))
        self.vector = self.arm.alloc(16)
        self.arm.write(self.vector,struct.pack('<4f',1,1,1,1))
        self.vertex = self.arm.alloc(36)
        self.arm.write(self.vertex,struct.pack('<9f',-.5,-.5,0,.5,-.5,0,0,.5,0))
        self.color = self.arm.alloc(12)
        self.arm.write(self.color,bytes([255,0,0,255]*3))
        self.uv = self.arm.alloc(24)
        self.arm.write(self.uv,struct.pack('<6f',0,0,1,0,.5,1))

    def tearDown(self):
        self.graphics.close()
        self.arm.close()
        self.env.stop()

    def commands(self):
        f = float_out
        return [
            ('glEnable',(0x0b71,)), ('glDisable',(0x0b71,)), ('glBindTexture',(0x0de1,0)),
            ('glActiveTexture',(0x84c0,)), ('glClientActiveTexture',(0x84c0,)),
            ('glEnableClientState',(0x8074,)), ('glDisableClientState',(0x8076,)),
            ('glVertexPointer',(3,0x1406,0,self.vertex)), ('glColorPointer',(4,0x1401,0,self.color)),
            ('glTexCoordPointer',(2,0x1406,0,self.uv)), ('glNormalPointer',(0x1406,0,self.vertex)),
            ('glMatrixMode',(0x1701,)), ('glLoadMatrixf',(self.identity,)),
            ('glMultMatrixf',(self.identity,)), ('glMatrixMode',(0x1700,)), ('glLoadMatrixf',(self.identity,)),
            ('glColor4f',(f(1),f(.25),f(.5),f(1))), ('glBlendFunc',(0x302,0x303)),
            ('glTexEnvf',(0x2300,0x2200,f(0x2100))), ('glTexEnvfv',(0x2300,0x2201,self.vector)),
            ('glMaterialf',(0x408,0x1601,f(16))), ('glMaterialfv',(0x408,0x1200,self.vector)),
            ('glLightf',(0x4000,0x1207,f(1))), ('glLightfv',(0x4000,0x1201,self.vector)),
            ('glLightModelf',(0xb52,f(0))), ('glLightModelfv',(0xb53,self.vector)),
            ('glFogf',(0xb63,f(1))), ('glFogfv',(0xb66,self.vector)),
            ('glDepthFunc',(0x201,)), ('glDepthMask',(1,)), ('glColorMask',(1,1,1,1)),
            ('glAlphaFunc',(0x204,f(.1))), ('glCullFace',(0x405,)), ('glFrontFace',(0x901,)),
            ('glShadeModel',(0x1d01,)), ('glPolygonOffset',(f(1),f(1))),
            ('glViewport',(0,0,320,240)), ('glScissor',(0,0,320,240)),
            ('glStencilFunc',(0x207,0,255)), ('glStencilOp',(0x1e00,0x1e00,0x1e00)),
            ('glHint',(0xc50,0x1101)), ('glTexParameterf',(0xde1,0x2801,f(0x2601))),
        ]

    def test_all_native_submissions_match_python_pixels_and_accounting(self):
        images = []
        for fast in (False,True):
            self.graphics.gl.glClearColor(0,0,0,1)
            self.graphics.gl.glClear(0x4100)
            for name,args in self.commands():
                self.arm.call(self.arm.imports[name] if fast else self.bridge.original_imports[name],*args)
            self.arm.call(self.arm.imports['glDrawArrays'],4,0,3)
            images.append(self.graphics.capture_image().tobytes())
            self.assertEqual(self.graphics.gl.glGetError(),0)
        self.assertEqual(images[0],images[1])
        self.assertGreater(len(set(images[1])),1)
        self.assertEqual(self.bridge.metrics()['calls'],len(self.commands()))
        phases = self.arm.diagnostics.metrics()['phases']
        self.assertGreater(phases['graphics_submission']['seconds'],0)
        self.assertGreaterEqual(phases['graphics_submission']['calls'],2*len(self.commands()))

    def test_invalid_matrix_pointer_stops_emulation(self):
        with self.assertRaisesRegex(RuntimeError,'graphics pointer'):
            self.arm.call(self.arm.imports['glLoadMatrixf'],self.arm.base-1)

    def test_null_client_pointer_is_valid_until_a_draw(self):
        self.arm.call(self.arm.imports['glVertexPointer'],3,0x1406,0,0)
        self.assertEqual(self.graphics.gl.glGetError(),0)
