"""Original engine lifecycle and desktop input routing."""
import json
import time
from collections import deque
from pathlib import Path
from .arm import ArmRuntime
from .assets import validate
from .bionic import Bionic, float_out
from .eabi import install
from .graphics import Graphics
from .jni import JNI
from .media import Media
from .fast import Fast
from .native_unzip import NativeUnzip
from .input import DesktopInput
from .pc_controls import PCControls
from .runtime_log import log
from .timing import ENGINE_HZ, FramePacer
from .diagnostics import Diagnostics
from .texture_cache import TextureCache
from .backups import SaveStore
from .save_boundary import SaveBoundary
from .achievements import AchievementTracker
from .achievement_media import UnlockCapture
from .actions import key_map, MouseBindings
from .menu_controls import MenuControls

KEYS = {
    1073741906:19, 1073741905:20, 1073741904:21, 1073741903:22,
    ord('w'):19, ord('s'):20, ord('a'):21, ord('d'):22,
    ord('z'):8, ord('x'):9, ord('q'):29, ord('e'):47,
    ord('r'):12, ord('f'):11, 13:66, 32:23, 27:32,
}

class Game:
    def __init__(self, root, width=800, height=480, hidden=False, trace=False, skip_videos=False, language=None, controls='pc', *, settings=None, profile=None, native_profiles=(), cache=False, cache_dir=None, telemetry=None, diagnostics=True, import_profile=False):
        self.initialized = False
        self.telemetry = telemetry
        self.diagnostics = Diagnostics(profile=profile, native_hooks=bool(native_profiles), import_hooks=import_profile) if diagnostics else None
        if telemetry:
            telemetry.diagnostics = self.diagnostics
        self.overlay = False
        self.settings = settings or {}
        self.startup_started = time.monotonic()
        from contextlib import nullcontext
        self.phase = self.diagnostics.phase if self.diagnostics else lambda *args, **kwargs: nullcontext()
        try:
            with self.phase('startup_validation'):
                self.root = validate(root)
            self.save_store = SaveStore(self.root)
            self.save_store.acquire(running=True)
        except BaseException:
            self.close()
            raise
        try:
            # Native startup may migrate old save formats before normal Save.
            # Preserve the entire previous set before any initializer executes.
            with self.phase('save_backup', 'snapshot before native startup'):
                self.save_store.snapshot('before-startup')
            with self.phase('startup_host'):
                self.arm = ArmRuntime(diagnostics=self.diagnostics)
                self.bionic = Bionic(self.arm, self.root)
                self.graphics = Graphics(self.arm, width, height, hidden, logical_size=(800, 480))
                self.graphics.diagnostics = self.diagnostics
                self.graphics.controller.configure(self.settings)
                if self.settings.get('window_mode') == 'fullscreen':
                    self.graphics.toggle_fullscreen()
                self.graphics.texture_cache = TextureCache(cache_dir, enabled=cache, diagnostics=self.diagnostics)
                self.jni = JNI(self.arm, self.root, 800, 480, trace)
                self.media = Media(self.root, self.graphics.sdl, self.graphics)
                self.media.skip_videos = skip_videos
                self.jni.media = self.media
            self._initialize(language, controls, native_profiles)
        except BaseException:
            self.close()
            raise
        self.startup_seconds = time.monotonic() - self.startup_started

    def _initialize(self, language, controls, native_profiles):
        from .languages import GAME_LANGUAGES
        self.language = language if language is not None else self.settings.get('game_language', 'en')
        if self.language not in GAME_LANGUAGES:
            raise ValueError('Unsupported game language: ' + str(self.language))
        self.frames = 0
        self.input_events = 0
        self.touch_previous = (0, 0)
        self.native_touch_down = False
        self.key_sources = {}
        self.key_routes = {}
        self.keymap = key_map(self.settings)
        self.mouse_bindings = MouseBindings(self.settings)
        self.story_keys = set()
        self.desktop_input = DesktopInput(self.touch, self.key,lambda down,button:self.pc.button(down,button))
        self.skipping_touch = False
        self.recapture_click = False
        self.gameplay_click = False
        self.pc = PCControls(self.arm,controls=='pc')
        self.menu = MenuControls(self.arm, self.touch, enabled=controls=='pc',
                                 cursor=self.graphics.controller.cursor, settings=self.settings)
        self.graphics.controller.menu_actions = controls=='pc'
        self.pc.sensitivity = self.settings.get('sensitivity', 1.0)
        self.pc.invert_y = self.settings.get('invert_y', False)
        self.mouse_captured=False
        self.mouse_released=False
        self.save_verified = False
        self.engine_seconds = 0.0
        self.max_engine_seconds = 0.0
        self.frame_times = deque(maxlen=200)
        with self.phase('startup_linking'):
            log.info('Loading and linking original ARM libraries')
            mce = self.arm.load(self.root / 'lib/libmc_eruption_for_android_jni.so', 0)
            bio = self.arm.load(self.root / 'lib/libbio4af.so', 2 * 1024 * 1024)
            install(self.arm)
            self.fast=Fast(self.arm)
            self.unzip=NativeUnzip(self.arm)
            self.unzip.install()
            self.arm.relocate()
            self.pc.install()
            self.menu.install()
            from .laser import LaserSight
            self.graphics.laser = LaserSight(self.graphics, self.settings)
            self.graphics.laser.install()
            self.achievements = AchievementTracker(self.arm, self.root)
            self.unlock_capture = UnlockCapture(self.root, self.achievements.store, self.settings)
            self.save_boundary = SaveBoundary(self.arm, self.save_store, self.achievements.capture)
            if native_profiles:
                self.arm.enable_native_profiles(native_profiles)
            self.arm.initialize()
            for module in (mce,bio):
                target = module['base'] + next(s['st_value'] for s in module['symbols'].iter_symbols() if s.name=='JNI_OnLoad')
                version = self.arm.call(target, self.jni.vm, 0)
                if version != 0x10004:
                    raise RuntimeError(f'JNI_OnLoad returned {version:x}')
            self.jni.native('native_onCreate', self.jni.activity)
            self.jni.native('native_onStart')
            self.jni.native('native_onResume')
            self.jni.native('native_onSurfaceCreated', self.jni.activity, self.jni.activity, 800, 480, 0)
            self.jni.native('native_onSurfaceChanged', self.jni.activity, 800, 480)
            self.initialized = True
            log.info('Engine ready; %d FPS native cadence; WASD move, RMB aim, LMB fire, R reload, Tab cursor, F12 quit',ENGINE_HZ)

    def touch(self, action, x, y):
        # Only visible UI targets accept a released gameplay pointer. Hidden
        # combat controls and captured fire must never receive native touches.
        if action != 'up' and self.pc.enabled and self.pc.active and self.media.video is None:
            if not self.mouse_released or not (
                    getattr(self, 'native_touch_down', False) if action == 'move'
                    else self.pc.pointer_target(x, y)):
                return
        if action == 'up' and not getattr(self, 'native_touch_down', False):
            return
        methods = {'down':'native_onTouchBegan','move':'native_onTouchMoved','up':'native_onTouchEnded'}
        previous = (x, y) if action == 'down' else self.touch_previous
        self.jni.native(methods[action],self.jni.activity,float_out(x),float_out(y),float_out(previous[0]),float_out(previous[1]))
        self.touch_previous = (x, y)
        self.native_touch_down = action != 'up'
        self.input_events += 1

    def key(self, down, code):
        mapped = getattr(self, 'keymap', KEYS)[code]
        sources = self.key_sources.setdefault(mapped, set())
        if down:
            if sources:
                sources.add(code)
                return
            sources.add(code)
            # Keep the release on the same route even if a menu opens.
            menu = getattr(self, 'menu', None)
            self.key_routes[mapped] = ('menu' if menu and menu.routes(mapped) else
                self.pc.enabled and (self.pc.active or (mapped==23 and self.pc.item_active)))
        else:
            if code not in sources:
                return
            sources.discard(code)
            if sources:
                return
        if self.key_routes.get(mapped) == 'menu':
            self.menu.key(down, mapped)
        elif self.key_routes.get(mapped, False):
            self.pc.key(down, mapped)
        else:
            self.jni.native('native_onKeyDown' if down else 'native_onKeyUp',mapped,self.jni.activity)
        if not down:
            self.key_routes.pop(mapped, None)
        self.input_events += 1

    def event(self, event):
        kind = event[0]
        if kind=='quit':
            if getattr(self, 'menu', None): self.menu.cancel()
            return False
        controller = getattr(getattr(self, 'graphics', None), 'controller', None)
        if kind=='controller_look':
            if self.pc.active:
                self.pc.move(*event[1:], sensitivity=1.0)
            return True
        if kind.startswith('controller_') and controller:
            if kind == 'controller_removed' and getattr(self, 'menu', None):
                self.menu.cancel()
            controller.gameplay = self.pc.active
            controller.process(event)
            return True
        if kind=='fullscreen':
            self.graphics.toggle_fullscreen()
            return True
        if kind=='key':
            down,key = event[1:]
            mapped_code = getattr(self, 'keymap', KEYS).get(key)
            if key==1073741893 and down: return False  # F12
            if key==1073741884 and down:  # F3
                self.overlay = not self.overlay
                return True
            if key==9 and down:
                self.mouse_released=not self.mouse_released
                self.desktop_input.release()
                if controller: controller.release()
                if getattr(self, 'mouse_bindings', None): self.mouse_bindings.release()
                self.pc.release()
                self.update_mouse_capture()
                return True
            if self.media.video is not None and down and mapped_code in (66,32,23):
                self.media.end_video()
                return True
            story_keys = getattr(self, 'story_keys', set())
            if key in story_keys or (down and self.pc.story_active and mapped_code in (66,23) and not (
                    getattr(self, 'menu', None) and self.menu.routes(mapped_code)) and not (
                    mapped_code==23 and self.pc.enabled and (
                        self.pc.item_active or self.key_routes.get(23,False)))):
                if down: story_keys.add(key)
                else: story_keys.discard(key)
                self.story_keys = story_keys
                self.desktop_input.enqueue(('touch',down,742,416))
                return True
            if key in getattr(self, 'keymap', KEYS): self.desktop_input.enqueue(('key',down,key))
        elif kind in ('touch', 'mouse_button'):
            down = event[1]
            button = 1 if kind == 'touch' else event[2]
            # Consume the entire click that recaptures, even if a menu opens
            # before its release. It must neither fire nor activate a button.
            if button == 1 and getattr(self, 'recapture_click', False):
                if not down: self.recapture_click = False
                return True
            # Keep a UI press on the touch route through its release, even
            # when that press opens inventory or another native overlay.
            if button == 1 and getattr(self, 'gameplay_click', False):
                if kind == 'touch': self.desktop_input.enqueue(event)
                elif not down:
                    self.desktop_input.enqueue(('touch', False, *self.desktop_input.position))
                if not down: self.gameplay_click = False
                return True
            if self.pc.enabled and self.pc.active and self.media.video is None:
                if self.mouse_released:
                    if button == 1 and down:
                        if kind == 'touch' and self.pc.pointer_target(*event[2:]):
                            self.gameplay_click = True
                            self.desktop_input.enqueue(event)
                            return True
                        self.mouse_released = False
                        self.recapture_click = True
                        self.update_mouse_capture()
                    return True
                self.update_mouse_capture()
                mapped = self.mouse_bindings.event(down, button)
                if mapped: self.desktop_input.enqueue(mapped)
                return True
            if kind == 'mouse_button' or self.mouse_captured:
                return True
            if getattr(self, 'menu', None) and self.menu.active:
                self.menu.cancel()
                self.menu.cursor[:] = event[2:]
            down,x,y = event[1:]
            if down and self.media.video is not None:
                self.media.end_video()
                self.skipping_touch = True
            elif self.skipping_touch:
                if not down: self.skipping_touch = False
            else: self.desktop_input.enqueue(event)
        elif kind=='motion':
            if getattr(self, 'menu', None) and self.menu.active:
                self.menu.cursor[:] = event[1:]
            if not self.mouse_captured and not self.skipping_touch and (
                    getattr(self, 'gameplay_click', False) or not (self.pc.enabled and self.pc.active)):
                self.desktop_input.enqueue(event)
        elif kind=='mouse_delta':
            if self.mouse_captured and not self.mouse_released and self.pc.active:
                self.pc.move(*event[1:])
        elif kind=='focus_lost':
            if getattr(self, 'menu', None): self.menu.cancel()
            if controller: controller.release()
            if getattr(self, 'mouse_bindings', None): self.mouse_bindings.release()
            self.desktop_input.release()
            self.pc.release()
            self.mouse_released=True
            self.skipping_touch=False
            self.recapture_click=False
            self.gameplay_click=False
            self.update_mouse_capture()
        return True

    def update_mouse_capture(self):
        capture = (getattr(self.pc, 'enabled', False) and self.pc.active and
                   not self.mouse_released and self.media.video is None)
        if capture == getattr(self, 'mouse_captured', False):
            return
        self.gameplay_click = False
        self.desktop_input.release()
        self.mouse_bindings.release()
        controller = getattr(self.graphics, 'controller', None)
        if controller: controller.release()
        self.pc.release()
        with self.phase('input_capture', 'SDL_SetRelativeMouseMode'):
            self.graphics.capture_mouse(capture)
        self.mouse_captured = capture
        log.info('Mouse %s', 'captured for gameplay' if capture else 'released')

    def configure_controls(self, settings):
        """Release using the old bindings before applying a remap."""
        from .settings import validate as validate_settings
        settings = validate_settings(settings)
        self.graphics.controller.release()
        self.mouse_bindings.release()
        self.desktop_input.release()
        self.desktop_input.flush()
        self.pc.release()
        self.story_keys.clear()
        self.menu.cancel()
        self.menu.settings = settings
        self.keymap = key_map(settings)
        self.mouse_bindings.configure(settings)
        self.graphics.controller.configure(settings)
        self.pc.sensitivity = settings['sensitivity']
        self.pc.invert_y = settings['invert_y']
        self.graphics.laser.configure(settings)
        self.settings = settings

    def frame(self):
        start=time.monotonic()
        self.graphics.begin_frame()
        with self.phase('input'):
            controller = getattr(self.graphics, 'controller', None)
            if controller:
                for event in controller.tick(1 / ENGINE_HZ, gameplay=self.pc.active):
                    self.event(event)
            self.desktop_input.flush()
            self.menu.tick()
            self.pc.begin_frame()
        with self.phase('native_frame', 'native_onDrawFrame'):
            self.menu.begin_observation()
            result=self.jni.native('native_onDrawFrame',self.jni.activity)
            self.menu.end_observation()
            if result==1: self.jni.native('native_setStereoHard',self.jni.activity,0)
        with self.phase('media_audio'):
            self.media.update_audio()
        with self.phase('media_video'):
            self.media.update_video()
        unlocks = tuple(self.achievements.new_unlocks)
        self.achievements.new_unlocks.clear()
        self.unlock_capture.tick(self.graphics.capture_image, unlocks)
        self.graphics.draw_controller_cursor()
        if self.menu.active and self.media.video is None:
            self.graphics.draw_menu_hints(self.menu.hints(), self.menu.cursor)
        self.update_mouse_capture()
        self.frames += 1
        if self.frames == 3:
            from .languages import apply_game_language
            apply_game_language(self.arm, self.language)
        elapsed = time.monotonic()-start
        self.engine_seconds += elapsed
        self.max_engine_seconds = max(self.max_engine_seconds, elapsed)
        self.frame_times.append(elapsed)
        if self.diagnostics:
            self.diagnostics.frame(elapsed)
        if getattr(self,'telemetry',None): self.telemetry.sample(self)
        if self.overlay and self.diagnostics:
            with self.phase('diagnostics_overlay'):
                self.graphics.draw_overlay(self.diagnostics.overlay_lines(self), self.diagnostics.graph())

    def present(self):
        with self.phase('swap'):
            self.graphics.swap()
        if self.diagnostics:
            self.diagnostics.presentation()

    def present_video(self):
        """Show a due movie frame between engine ticks without simulating."""
        with self.phase('media_video'):
            self.graphics.begin_frame()
            self.media.update_video()
        if self.media.video is not None:
            self.present()

    def statistics(self, pacer=None, elapsed=None):
        """Legacy fields retain their meanings; new fields have a versioned schema."""
        stats = {'schema_version': 2,
                 'frames':self.frames,'presentations':self.graphics.presentations,
                 'draw_calls':self.graphics.draws,'texture_uploads':self.graphics.textures,
                 'input_events':self.input_events,'audio_loads':self.media.loaded,'audio_decoded':len(self.media.decoded),'videos_played':self.media.videos_played,
                 'heap_bytes':self.arm.heap-(self.arm.base+16*1024*1024),
                 'native_import_calls':self.fast.calls(),
                 'audio_output_frames':self.media.audio.re4_audio_measure(0),
                 'audio_nonzero_samples':self.media.audio.re4_audio_measure(1),
                 'gl_messages':sorted(self.graphics.debug_messages),
                 'save_roundtrip_verified':self.save_verified,
                 'successful_saves':self.save_boundary.completed,'failed_saves':self.save_boundary.failed,
                 'engine_hz':ENGINE_HZ, 'presentation_hz':ENGINE_HZ,
                 'frame_overruns':pacer.overruns if pacer else 0,
                 'startup_seconds':round(self.startup_seconds, 6),
                 'elapsed_seconds':round(elapsed if elapsed is not None else time.monotonic()-self.startup_started,3),
                 'max_engine_ms':round(self.max_engine_seconds*1000,2),
                 'mean_engine_ms':round(self.engine_seconds/max(self.frames,1)*1000,2)}
        from .assets import COMPATIBLE_LIBRARIES
        stats['engine_hashes'] = COMPATIBLE_LIBRARIES
        stats['graphics'] = {'renderer':self.graphics.renderer, 'version':self.graphics.version,
                             'logical_size':[self.graphics.width,self.graphics.height],
                             'window_size':self.graphics.window_size, 'drawable_size':self.graphics.drawable_size}
        import resource
        stats['peak_process_rss_bytes_since_process_start'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        stats['settings'] = self.settings
        stats['diagnostics'] = self.diagnostics.metrics() if self.diagnostics else {'enabled':False}
        stats['texture_cache'] = self.graphics.texture_cache.metrics()
        stats['native_unzip'] = {'calls': self.unzip.calls, 'fallbacks': self.unzip.fallbacks,
                                 'bytes': self.unzip.bytes}
        stats['pending_audio_decodes'] = sum(not future.done() for future in self.media.decoding.values())
        stats['pending_audio_requests'] = len(self.media.pending_audio)
        return stats

    def verify_save_roundtrip(self):
        """Verify the engine's own serialization using the current test save."""
        user=self.arm.symbols['_ZZN13Bio4_UserData11GetInstanceEvE4inst']
        getter='_ZNK13Bio4_UserData9GetLangIdEv'
        setter='_ZN13Bio4_UserData9SetLangIdEh'
        original=self.arm.call(getter,user)
        probe=2 if original != 2 else 1
        try:
            self.arm.call(setter,user,probe)
            if self.arm.call('_ZN13Bio4_UserData4SaveEl',user,63) != 1:
                raise RuntimeError('Original engine save failed')
            self.arm.call(setter,user,original)
            if self.arm.call('_ZN13Bio4_UserData4LoadEl',user,63) != 1:
                raise RuntimeError('Original engine load failed')
            if self.arm.call(getter,user) != probe:
                raise RuntimeError('Engine load did not restore saved language')
            self.save_verified=True
            print('[test] Original engine save/load roundtrip passed',flush=True)
        finally:
            self.arm.call(setter,user,original)
            if self.arm.call('_ZN13Bio4_UserData4SaveEl',user,63) != 1:
                raise RuntimeError('Could not restore original language in test save')

    def run(self, frames=0, screenshot=None, script=None, replay_only=False):
        scheduled = {}
        if script:
            for entry in json.loads(Path(script).read_text()):
                scheduled.setdefault(entry['frame'], []).append(entry)
        running=True
        pacer = FramePacer()
        run_started = time.monotonic()
        try:
            while running and (not frames or self.frames < frames):
                with self.phase('input_poll'):
                    for event in self.graphics.events():
                        if replay_only and event[0] != 'quit' and event != ('key',True,1073741893):
                            continue
                        if not self.event(event): running=False
                if not running: break
                captures = []
                for entry in scheduled.get(self.frames,[]):
                    if entry['action']=='skip_video': self.media.end_video()
                    elif entry['action']=='save_roundtrip': self.verify_save_roundtrip()
                    elif entry['action'] in ('down','up'):
                        self.event(('touch',entry['action']=='down',entry['x'],entry['y']))
                    elif entry['action']=='move': self.touch('move',entry['x'],entry['y'])
                    elif entry['action']=='assert_no_video':
                        if self.media.video is not None:
                            raise RuntimeError('Visible menu check reached a video instead')
                    elif entry['action'] in ('key_down','key_up'):
                        self.pc.key(entry['action']=='key_down',entry['code'])
                        self.jni.native('native_onKeyDown' if entry['action']=='key_down' else 'native_onKeyUp',entry['code'],self.jni.activity)
                    elif entry['action']=='label':
                        print('[test]',entry['text'],flush=True)
                        self.graphics.sdl.SDL_SetWindowTitle(self.graphics.window,entry['text'].encode())
                    elif entry['action']=='screenshot': captures.append(entry['path'])
                    elif entry['action']=='event':
                        if not self.event(tuple(entry['event'])): running=False
                    elif entry['action']=='resize':
                        width, height = entry['width'], entry['height']
                        if not (240 <= width <= 16384 and 240 <= height <= 16384):
                            raise ValueError('Invalid replay window size')
                        import ctypes as C
                        self.graphics.signature('SDL_SetWindowSize', None, C.c_void_p, C.c_int, C.c_int)
                        self.graphics.sdl.SDL_SetWindowSize(self.graphics.window, width, height)
                        self.graphics.update_drawable()
                    else: raise ValueError('Unknown scripted input action')
                self.frame()
                for path in captures: self.graphics.screenshot(path)
                if screenshot and frames and self.frames==frames: self.graphics.screenshot(screenshot)
                self.present()
                with self.phase('pacing'):
                    pacer.wait(self.media.next_video_time, self.present_video)
            if screenshot and (not frames or self.frames < frames):
                self.frame()
                self.graphics.screenshot(screenshot)
            stats = self.statistics(pacer, time.monotonic()-run_started)
            log.info('Final statistics: %s',json.dumps(stats))
            return stats
        finally:
            self.close()

    def close(self):
        if getattr(self, 'menu', None):
            try: self.menu.cancel()
            except Exception as error: log.warning('[shutdown input] %s', error)
        if getattr(self, '_closed', False):
            return
        self._closed = True
        if getattr(self, 'unlock_capture', None):
            self.unlock_capture.close()
        if self.initialized:
            for method in ('native_onPause','native_onStop','native_onDestroy'):
                try: self.jni.native(method)
                except Exception as error: log.warning('[shutdown] %s', error)
            self.initialized=False
        # Attempt every cleanup even if flushing a save or reaping media fails.
        for name, callback in (
                ('save transaction', getattr(getattr(self,'save_boundary',None),'abort',None)),
                ('files', getattr(getattr(self,'bionic',None),'close',None)),
                ('media', getattr(getattr(self,'media',None),'close',None)),
                ('graphics', getattr(getattr(self,'graphics',None),'close',None)),
                ('arm', getattr(getattr(self,'arm',None),'close',None)),
                ('saves', getattr(getattr(self,'save_store',None),'close',None)),
                ('diagnostics', getattr(getattr(self,'diagnostics',None),'close',None))):
            if callback:
                try: callback()
                except Exception as error: log.warning('[shutdown %s] %s',name,error)
