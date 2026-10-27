"""Present host snapshots while the emulator works, in a shared GL context.

The worker never polls SDL input, enters ARM, advances media or reads saves.
Texture uploads invalidate snapshots before mutation; GPU fences publish complete
resources. Each context owns its framebuffer, matrices and client-array state.
"""
from collections import deque
import ctypes as C
import threading
import time

from .graphics import Graphics
from .timing import PresentationClock


class PresentationWorker:
    def __init__(self, graphics, stream, rate, on_present=None):
        self.graphics, self.stream, self.rate = graphics, stream, rate
        self.on_present = on_present
        self.lock = threading.RLock()
        self.stopped = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.thread = None
        self.timestamps = deque(maxlen=240)
        self.frames = 0
        self.render_seconds = 0.0
        self.overlay = None
        self.surface = surface = Graphics.__new__(Graphics)
        surface.sdl, surface.gl, surface.window = graphics.sdl, graphics.gl, graphics.window
        surface.width, surface.height = graphics.width, graphics.height
        surface.framebuffer = surface.surface_texture = surface.surface_depth = 0
        surface.presentations = 0
        surface.controller = graphics.controller
        surface.diagnostics = None
        surface.window_size, surface.drawable_size = graphics.window_size, graphics.drawable_size
        # Same scaled surface, filter and margins; only the engine context maps imports.
        surface.display, surface.display_engine = graphics.display, False
        surface.scale, surface.margin = graphics.scale, graphics.margin
        surface.samples, surface.display_filter = graphics.samples, graphics.display_filter
        surface.resolve_framebuffer = surface.surface_color = 0
        surface.post = None
        surface.viewport = graphics.viewport
        surface._mouse_touch = surface._fullscreen_enter = surface.mouse_captured = False
        surface.signature('SDL_GL_MakeCurrent', C.c_int, C.c_void_p, C.c_void_p)
        self.context = None
        self.native_window = None
        self.read_framebuffer = C.c_uint()
        try:
            self.native_window = surface.sdl.SDL_CreateWindow(b'Re4 engine surface',0,0,surface.width,surface.height,2|8)
            if not self.native_window:
                raise RuntimeError(surface.sdl.SDL_GetError().decode())
            if surface.sdl.SDL_GL_MakeCurrent(self.native_window, graphics.context):
                raise RuntimeError(surface.sdl.SDL_GetError().decode())
            if surface.sdl.SDL_GL_SetAttribute(22, 1):  # SHARE_WITH_CURRENT_CONTEXT
                raise RuntimeError(surface.sdl.SDL_GetError().decode())
            self.context = surface.sdl.SDL_GL_CreateContext(surface.window)
            if not self.context:
                raise RuntimeError(surface.sdl.SDL_GetError().decode())
            extensions = C.string_at(surface.gl.glGetString(0x1f03)).split()
            if b'GL_KHR_debug' in extensions:
                surface.gl.glEnable(0x92e0)
                surface.gl.glDebugMessageCallback(graphics.debug_callback,None)
            surface.sdl.SDL_GL_SetSwapInterval(0)
            surface._create_surface()
            surface.gl.glGenFramebuffers(1,C.byref(self.read_framebuffer))
        except BaseException:
            self._delete_surface()
            if self.context:
                surface.sdl.SDL_GL_MakeCurrent(self.native_window or graphics.window,graphics.context)
                surface.sdl.SDL_GL_DeleteContext(self.context)
                self.context = None
            if self.native_window:
                surface.sdl.SDL_GL_MakeCurrent(graphics.window,graphics.context)
                surface.sdl.SDL_DestroyWindow(self.native_window)
                self.native_window = None
            raise
        finally:
            surface.sdl.SDL_GL_SetAttribute(22, 0)
            if surface.sdl.SDL_GL_MakeCurrent(self.native_window or graphics.window, graphics.context):
                raise RuntimeError(surface.sdl.SDL_GetError().decode())
        stream.presentation_lock = self.lock

    def start(self):
        self.thread = threading.Thread(target=self._run, name='re4-presentation', daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            self.close()
            raise RuntimeError('Presentation context did not start')
        self.check()

    def _run(self):
        surface = self.surface
        try:
            if surface.sdl.SDL_GL_MakeCurrent(surface.window, self.context):
                raise RuntimeError(surface.sdl.SDL_GetError().decode())
            surface.gl.glMatrixMode(0x1700)
            self.ready.set()
            clock = PresentationClock(self.rate)
            while not self.stopped.is_set():
                rendered = False
                with self.lock:
                    began = time.monotonic()
                    surface.begin_frame()
                    geometry = self.stream.available and self.stream.render()
                    if not geometry:
                        # Published frames are already resolved and complete.
                        surface.target_resolved()
                    if geometry or self.stream.blit(self.read_framebuffer.value):
                        if geometry and self.overlay:
                            surface.draw_overlay(*self.overlay)
                        surface.present()
                        error = surface.gl.glGetError()
                        if error:
                            raise RuntimeError(f'Presentation GL error 0x{error:x}')
                        now = time.monotonic()
                        self.timestamps.append(now)
                        self.frames += 1
                        self.render_seconds += now-began
                        if self.on_present:
                            self.on_present()
                        rendered = True
                now = time.monotonic()
                if rendered:
                    clock.presented()
                else:
                    clock.reset()
                    clock.deadline += .002
                self.stopped.wait(max(0, clock.deadline-now))
        except BaseException as error:
            self.error = error
            self.ready.set()
        finally:
            surface.sdl.SDL_GL_MakeCurrent(surface.window, None)

    def check(self):
        if self.error:
            raise RuntimeError('Presentation worker failed: '+str(self.error)) from self.error

    def metrics(self):
        timestamps = tuple(self.timestamps)
        fps = (len(timestamps)-1)/(timestamps[-1]-timestamps[0]) if len(timestamps)>1 else 0
        return {'threaded':True, 'frames':self.frames, 'recent_fps':round(fps,2),
                'mean_render_and_swap_ms':round(self.render_seconds/max(self.frames,1)*1000,3)}

    def _delete_surface(self):
        self.surface._delete_surface()

    def close(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                raise RuntimeError('Presentation worker did not stop')
            self.thread = None
        if self.context:
            if self.surface.sdl.SDL_GL_MakeCurrent(self.surface.window, self.context):
                raise RuntimeError(self.surface.sdl.SDL_GetError().decode())
            self._delete_surface()
            if self.read_framebuffer.value:
                self.surface.gl.glDeleteFramebuffers(1,C.byref(self.read_framebuffer))
                self.read_framebuffer.value = 0
            self.surface.sdl.SDL_GL_MakeCurrent(self.surface.window, self.graphics.context)
            self.surface.sdl.SDL_GL_DeleteContext(self.context)
            self.context = None
        if self.native_window:
            self.surface.sdl.SDL_DestroyWindow(self.native_window)
            self.native_window = None
        self.stream.presentation_lock = None
