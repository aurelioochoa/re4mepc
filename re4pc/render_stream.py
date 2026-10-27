"""Independent presentation of host-owned native geometry snapshots.

Only driver state and copied arrays are replayed. Simulation, input sampling,
sound, timers, files and guest memory never advance during presentation.
"""
import ctypes as C
import time
from contextlib import nullcontext
from .paths import native_library
from .timing import ENGINE_HZ


class RenderStream:
    def __init__(self):
        self.lib = C.CDLL(str(native_library('libre4fast.so')))
        signatures = {
            'open': (C.c_void_p, ()), 'close': (None, (C.c_void_p,)),
            'begin': (None, (C.c_void_p,)), 'end': (None, (C.c_void_p, C.c_int)),
            'reset': (None, (C.c_void_p,)), 'dirty': (None, (C.c_void_p,)),
            'clear': (None, (C.c_void_p, C.c_uint)),
            'draw': (None, (C.c_void_p, C.c_uint, C.c_int, C.c_int, C.c_uint, C.c_void_p)),
            'present': (C.c_int, (C.c_void_p, C.c_float)),
            'publish': (None, (C.c_void_p, C.c_int, C.c_int)),
            'blit': (C.c_int, (C.c_void_p, C.c_uint)),
            'measure': (C.c_uint64, (C.c_void_p, C.c_uint)),
        }
        for name, (result, args) in signatures.items():
            function = getattr(self.lib, 're4_render_'+name)
            function.restype, function.argtypes = result, args
        self.handle = self.lib.re4_render_open()
        if not self.handle:
            raise RuntimeError('Cannot initialize fixed-function presentation snapshots')
        self.completed_at = time.monotonic()
        self.recording = False
        self.presentation_lock = None

    @property
    def available(self):
        return bool(self.lib.re4_render_measure(self.handle, 6))

    def begin(self):
        self.lib.re4_render_begin(self.handle)
        self.recording = True

    def end(self, eligible=True):
        with self.presentation_lock or nullcontext():
            self.lib.re4_render_end(self.handle, eligible)
            self.completed_at = time.monotonic()
            self.recording = False

    def dirty(self):
        with self.presentation_lock or nullcontext():
            self.lib.re4_render_dirty(self.handle)

    def reset(self):
        with self.presentation_lock or nullcontext():
            self.lib.re4_render_reset(self.handle)

    def clear(self, mask):
        if self.recording:
            self.lib.re4_render_clear(self.handle, mask)

    def draw(self, name, values):
        if self.recording:
            if name == 'glDrawElements':
                mode, count, kind, pointer = values
                self.lib.re4_render_draw(self.handle, mode, 0, count, kind, pointer)
            else:
                mode, first, count = values
                self.lib.re4_render_draw(self.handle, mode, first, count, 0, None)

    def render(self, alpha=None):
        if alpha is None:
            alpha = (time.monotonic()-self.completed_at)*ENGINE_HZ
        return self.lib.re4_render_present(self.handle, alpha)

    def publish(self, width, height):
        with self.presentation_lock or nullcontext():
            self.lib.re4_render_publish(self.handle, width, height)

    def blit(self, read_framebuffer):
        return self.lib.re4_render_blit(self.handle, read_framebuffer)

    def metrics(self):
        names = ('captured_draws', 'replayed_frames', 'interpolated_frames',
                 'history_resets', 'rejected_draws', 'snapshot_bytes')
        result = dict(zip(names, (self.lib.re4_render_measure(self.handle, i) for i in range(len(names)))))
        result.update(zip(('matched_draws', 'unmatched_draws', 'changed_sequences'),
                          (self.lib.re4_render_measure(self.handle, i) for i in (7, 8, 9))))
        return result

    def close(self):
        if self.handle:
            self.lib.re4_render_close(self.handle)
            self.handle = None
