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
    def __init__(self, arm=None):
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
        self.source = self.part = 0
        self.arm = arm
        self.hooks = []
        self.sources = {}
        self.next_source = 1
        self.scopes = []
        self.returns = set()
        self.set_source = getattr(self.lib, 're4_render_source', None)
        if self.set_source:
            self.set_source.restype = None
            self.set_source.argtypes = (C.c_void_p, C.c_uint64, C.c_uint)
        if arm:
            self._install_sources()

    def _install_sources(self):
        """Observe model instances, whose Draw/Direct_Draw flush synchronously.

        GM_Element_Model::Draw copies its transform to the stack and calls
        mceGraphics3D_drawFigure, which flushes before returning. The model's
        `this` pointer identifies an instance; figures, meshes and the temporary
        transform can all be shared. Retire host tokens on model lifecycle calls
        so a recycled object address never inherits a destroyed model's history.
        """
        from unicorn import UC_HOOK_CODE
        from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_LR, UC_ARM_REG_SP

        def guarded(callback):
            def observe(uc, address, size, context):
                try:
                    callback(uc, address, size, context)
                except BaseException as error:
                    self.arm.pending_error = error
                    uc.emu_stop()
            return observe

        def leave(uc, address, size, context):
            if self.scopes and self.scopes[-1][:2] == (address, uc.reg_read(UC_ARM_REG_SP)):
                _, _, source, part = self.scopes.pop()
                self.part = max(part, self.part) if source == self.source else part
                self.source = source

        returned = guarded(leave)

        def enter(uc, address, size, context):
            model = uc.reg_read(UC_ARM_REG_R0)
            if model not in self.sources:
                self.sources[model] = self.next_source
                self.next_source += 1
            address = uc.reg_read(UC_ARM_REG_LR) & ~1
            self.scopes.append((address, uc.reg_read(UC_ARM_REG_SP), self.source, self.part))
            source = self.sources[model]
            self.part = self.part if source == self.source else 0
            self.source = source
            if address not in self.returns:
                self.returns.add(address)
                self.hooks.append(self.arm.uc.hook_add(UC_HOOK_CODE, returned, begin=address, end=address))
                self.arm.uc.ctl_remove_cache(address, address + 4)

        def retire(uc, address, size, context):
            self.sources.pop(uc.reg_read(UC_ARM_REG_R0), None)

        for name, callback in (
                ('_ZN16GM_Element_Model4DrawEv', enter),
                ('_ZN16GM_Element_Model11Direct_DrawEP12tagTransform', enter),
                ('_ZN16GM_Element_Model4InitEv', retire),
                ('_ZN16GM_Element_Model4TermEv', retire),
                ('_ZN16GM_Element_ModelD1Ev', retire)):
            address = self.arm.symbols[name] & ~1
            self.hooks.append(self.arm.uc.hook_add(UC_HOOK_CODE, guarded(callback), begin=address, end=address))
            self.arm.uc.ctl_remove_cache(address, address + self.arm.symbol_sizes[name])

    @property
    def available(self):
        return bool(self.lib.re4_render_measure(self.handle, 6))

    def begin(self):
        self.source = self.part = 0
        self.scopes.clear()
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
            if self.set_source:
                self.set_source(self.handle, self.source, self.part)
            self.part += 1
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
        result.update(zip(('matched_instance_draws', 'unmatched_instance_draws'),
                          (self.lib.re4_render_measure(self.handle, i) for i in (10, 11))))
        return result

    def close(self):
        for hook in self.hooks:
            self.arm.uc.hook_del(hook)
        self.hooks.clear()
        if self.handle:
            self.lib.re4_render_close(self.handle)
            self.handle = None
