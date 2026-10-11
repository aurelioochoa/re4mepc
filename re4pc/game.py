"""Original engine lifecycle and desktop input routing."""
import json
import time
from pathlib import Path
from .arm import ArmRuntime
from .assets import validate
from .bionic import Bionic, float_out
from .eabi import install
from .graphics import Graphics
from .jni import JNI
from .media import Media
from .fast import Fast
from .input import DesktopInput
from .pc_controls import PCControls
from .runtime_log import log

KEYS = {
    1073741906:19, 1073741905:20, 1073741904:21, 1073741903:22,
    ord('w'):19, ord('s'):20, ord('a'):21, ord('d'):22,
    ord('z'):8, ord('x'):9, ord('q'):29, ord('e'):47,
    ord('r'):12, ord('f'):11, 13:66, 32:23, 27:32,
}

class Game:
    def __init__(self, root, width=800, height=480, hidden=False, trace=False, skip_videos=False, language='en', controls='pc'):
        self.root = validate(root)
        self.arm = ArmRuntime()
        self.bionic = Bionic(self.arm, self.root)
        self.graphics = Graphics(self.arm, width, height, hidden)
        self.jni = JNI(self.arm, self.root, width, height, trace)
        self.media = Media(self.root, self.graphics.sdl, self.graphics)
        self.media.skip_videos = skip_videos
        self.jni.media = self.media
        self.language=language
        self.frames = 0
        self.input_events = 0
        self.touch_previous = (0, 0)
        self.key_sources = {}
        self.key_routes = {}
        self.desktop_input = DesktopInput(self.touch, self.key,lambda down,button:self.pc.button(down,button))
        self.skipping_touch = False
        self.pc = PCControls(self.arm,controls=='pc')
        self.mouse_captured=False
        self.mouse_released=False
        self.save_verified = False
        self.frame_times = []
        self.initialized = False
        try:
            log.info('Loading and linking original ARM libraries')
            mce = self.arm.load(self.root / 'lib/libmc_eruption_for_android_jni.so', 0)
            bio = self.arm.load(self.root / 'lib/libbio4af.so', 2 * 1024 * 1024)
            install(self.arm)
            self.fast=Fast(self.arm)
            self.arm.relocate()
            self.pc.install()
            self.arm.initialize()
            for module in (mce,bio):
                target = module['base'] + next(s['st_value'] for s in module['symbols'].iter_symbols() if s.name=='JNI_OnLoad')
                version = self.arm.call(target, self.jni.vm, 0)
                if version != 0x10004:
                    raise RuntimeError(f'JNI_OnLoad returned {version:x}')
            self.jni.native('native_onCreate', self.jni.activity)
            self.jni.native('native_onStart')
            self.jni.native('native_onResume')
            self.jni.native('native_onSurfaceCreated', self.jni.activity, self.jni.activity, width, height, 0)
            self.jni.native('native_onSurfaceChanged', self.jni.activity, width, height)
            self.initialized = True
            log.info('Engine ready; WASD move, RMB aim, LMB fire, R reload, Tab cursor, F12 quit')
        except BaseException:
            self.close()
            raise

    def touch(self, action, x, y):
        methods = {'down':'native_onTouchBegan','move':'native_onTouchMoved','up':'native_onTouchEnded'}
        previous = (x, y) if action == 'down' else self.touch_previous
        self.jni.native(methods[action],self.jni.activity,float_out(x),float_out(y),float_out(previous[0]),float_out(previous[1]))
        self.touch_previous = (x, y)
        self.input_events += 1

    def key(self, down, code):
        mapped = KEYS[code]
        sources = self.key_sources.setdefault(mapped, set())
        if down:
            if sources:
                sources.add(code)
                return
            sources.add(code)
            # Keep the release on the same route even if a menu opens.
            self.key_routes[mapped] = self.pc.enabled and self.pc.active
        else:
            sources.discard(code)
            if sources:
                return
        if self.key_routes.get(mapped, False):
            self.pc.key(down, mapped)
        else:
            self.jni.native('native_onKeyDown' if down else 'native_onKeyUp',mapped,self.jni.activity)
        if not down:
            self.key_routes.pop(mapped, None)
        self.input_events += 1

    def event(self, event):
        kind = event[0]
        if kind=='quit': return False
        if kind=='key':
            down,key = event[1:]
            if key==1073741893 and down: return False  # F12
            if key==9 and down:
                self.mouse_released=not self.mouse_released
                self.desktop_input.release()
                self.pc.release()
                return True
            if self.media.video is not None and down and key in (13,27,32):
                self.media.end_video()
                return True
            if self.pc.story_active and key in (13,32):
                self.desktop_input.enqueue(('touch',down,742,416))
                return True
            if key in KEYS: self.desktop_input.enqueue(('key',down,key))
        elif kind=='touch':
            down,x,y = event[1:]
            if self.mouse_captured:
                self.desktop_input.enqueue(('mouse_button',down,1))
            elif down and self.pc.enabled and self.pc.active and self.mouse_released:
                self.mouse_released=False
            elif down and self.media.video is not None:
                self.media.end_video()
                self.skipping_touch = True
            elif self.skipping_touch:
                if not down: self.skipping_touch = False
            else: self.desktop_input.enqueue(event)
        elif kind=='motion':
            if not self.mouse_captured and not self.skipping_touch: self.desktop_input.enqueue(event)
        elif kind=='mouse_button':
            if self.pc.active and not self.mouse_released:self.desktop_input.enqueue(event)
        elif kind=='mouse_delta':
            if self.mouse_captured:self.pc.move(*event[1:])
        elif kind=='focus_lost':
            self.desktop_input.release()
            self.pc.release()
            self.mouse_released=True
            self.skipping_touch=False
        return True

    def frame(self):
        start=time.monotonic()
        self.desktop_input.flush()
        self.pc.begin_frame()
        result=self.jni.native('native_onDrawFrame',self.jni.activity)
        if result==1: self.jni.native('native_setStereoHard',self.jni.activity,0)
        self.media.update_video()
        capture=self.pc.active and not self.mouse_released and self.media.video is None
        if capture != self.mouse_captured:
            self.desktop_input.release()
            if self.graphics.sdl.SDL_SetRelativeMouseMode(int(capture)):
                raise RuntimeError('Cannot capture mouse: '+self.graphics.sdl.SDL_GetError().decode())
            self.mouse_captured=capture
            log.info('Mouse %s', 'captured for gameplay' if capture else 'released')
        self.frames += 1
        if self.frames==3 and self.language=='en':
            user=self.arm.symbols['_ZZN13Bio4_UserData11GetInstanceEvE4inst']
            self.arm.call('_ZN13Bio4_UserData9SetLangIdEh',user,1)
        self.frame_times.append(time.monotonic()-start)
        if getattr(self,'telemetry',None): self.telemetry.sample(self)

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
        try:
            while running and (not frames or self.frames < frames):
                start=time.monotonic()
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
                    else: raise ValueError('Unknown scripted input action')
                self.frame()
                for path in captures: self.graphics.screenshot(path)
                if screenshot and frames and self.frames==frames: self.graphics.screenshot(screenshot)
                self.graphics.swap()
                time.sleep(max(0,1/45-(time.monotonic()-start)))
            if screenshot and (not frames or self.frames < frames):
                self.frame()
                self.graphics.screenshot(screenshot)
            stats = {'frames':self.frames,'draw_calls':self.graphics.draws,'texture_uploads':self.graphics.textures,
                     'input_events':self.input_events,'audio_loads':self.media.loaded,'audio_decoded':len(self.media.decoded),'videos_played':self.media.videos_played,
                     'heap_bytes':self.arm.heap-(self.arm.base+16*1024*1024),
                     'native_import_calls':self.fast.calls(),
                     'audio_output_frames':self.media.audio.re4_audio_measure(0),
                     'audio_nonzero_samples':self.media.audio.re4_audio_measure(1),
                     'gl_messages':sorted(self.graphics.debug_messages),
                     'save_roundtrip_verified':self.save_verified,
                     'mean_engine_ms':round(sum(self.frame_times)/max(len(self.frame_times),1)*1000,2)}
            log.info('Final statistics: %s',json.dumps(stats))
            return stats
        finally:
            self.close()

    def close(self):
        if self.initialized:
            for method in ('native_onPause','native_onStop','native_onDestroy'):
                try: self.jni.native(method)
                except Exception as error: log.warning('[shutdown] %s', error)
            self.initialized=False
        if getattr(self,'media',None): self.media.close()
        if getattr(self,'graphics',None): self.graphics.close()
        if getattr(self,'arm',None) and self.arm.uc is not None: self.arm.close()
