"""Decode original game audio via FFmpeg and play it using SDL's audio device."""
import ctypes as C
from .runtime_log import log
import hashlib
import subprocess
import queue
import threading
import time
from pathlib import Path

class Media:
    def __init__(self, root, sdl, graphics=None):
        self.root, self.sdl = Path(root).resolve(), sdl
        native = Path(__file__).resolve().parent.parent / 'build' / 'libre4audio.so'
        self.audio = C.CDLL(str(native))
        self.audio.re4_audio_open.restype = C.c_int
        self.audio.re4_audio_load.argtypes = (C.c_int, C.c_void_p, C.c_size_t, C.c_int)
        self.audio.re4_audio_play.argtypes = (C.c_int, C.c_float)
        self.audio.re4_audio_control.argtypes = (C.c_int, C.c_int, C.c_float)
        self.audio.re4_audio_playing.argtypes = (C.c_int,)
        self.audio.re4_audio_playing.restype = C.c_int
        self.audio.re4_audio_measure.argtypes = (C.c_int,)
        self.audio.re4_audio_measure.restype = C.c_uint64
        if self.audio.re4_audio_open():
            raise RuntimeError('SDL audio: ' + sdl.SDL_GetError().decode())
        self.decoded = {}
        self.audio_sources = {}
        self.audio_ready = set()
        self.cache = self.root / "cache" / "audio"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.loaded = 0
        self.graphics = graphics
        self.video = None
        self.video_queue = None
        self.video_reader = None
        self.video_stop = None
        self.video_frame = None
        self.videos_played = 0
        self.skip_videos = False

    def audio_service(self, name, args, arm):
        if name in ('init', 'term'):
            return 1
        bgm = name.endswith('BGM')
        slot = int(args[0]) + (128 if bgm else 0)
        if not 0 <= slot < 255:
            raise ValueError('Invalid audio slot')
        if name in ('loadBGM', 'loadSE'):
            path = Path(arm.string(args[1]))
            if not path.is_absolute(): path = self.root / 'data' / 'monhun' / path
            path = path.resolve()
            if not path.is_relative_to(self.root):
                raise ValueError(f'Audio path outside game directory: {path}, args={args}, raw={arm.string(args[1])!r}')
            offset, length = args[2:4]
            if offset < 0 or length <= 0 or offset + length > path.stat().st_size:
                raise ValueError(f'Invalid audio range: {offset}+{length} in {path}')
            loop = bool(args[4]) if bgm else False
            self.audio_sources[slot] = (path, offset, length, loop)
            self.audio_ready.discard(slot)
            self.loaded += 1
            if bgm: self.prepare_audio(slot)
            return 1
        if name in ('playBGM', 'playSE'):
            self.prepare_audio(slot)
            self.audio.re4_audio_play(slot, 1.0 if bgm else args[1])
            return 0
        for prefix, operation in (('stop',0),('pause',1),('restart',2),('setVolume',3),('term',4)):
            if name.startswith(prefix):
                self.audio.re4_audio_control(slot, operation, args[1] if operation==3 else 1.0)
                return 0
        raise RuntimeError('Unknown audio operation: ' + name)

    def prepare_audio(self, slot):
        if slot in self.audio_ready: return
        path, offset, length, loop = self.audio_sources[slot]
        key = (str(path), offset, length)
        if key not in self.decoded:
            with path.open('rb') as stream:
                stream.seek(offset)
                source = stream.read(length)
            cached = self.cache / (hashlib.sha256(source).hexdigest() + '.f32')
            if cached.is_file():
                data = cached.read_bytes()
            else:
                result = subprocess.run(['ffmpeg','-v','error','-i','pipe:0','-f','f32le',
                    '-ac','2','-ar','44100','pipe:1'],input=source,stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,timeout=30)
                if result.returncode or not result.stdout:
                    raise RuntimeError('Audio decode: '+result.stderr.decode(errors='replace'))
                data = result.stdout
                cached.write_bytes(data)
            self.decoded[key] = data
        data = self.decoded[key]
        buffer = C.create_string_buffer(data)
        if self.audio.re4_audio_load(slot,buffer,len(data),loop):
            raise RuntimeError('Cannot load decoded audio')
        self.audio_ready.add(slot)

    def video_service(self, name, args, arm):
        if name in ('create',): return 1
        if name in ('dispose','end'):
            self.end_video()
            return 0
        if name == 'nowPlaying': return int(self.video is not None)
        if name == 'start':
            self.end_video()
            if self.skip_videos: return 1
            filename = Path(arm.string(args[0])).name.removesuffix('.png')
            path = self.root / 'data' / 'monhun' / filename
            if not path.is_file(): raise FileNotFoundError(path)
            self.video_name = filename
            volume = max(0.0, min(float(args[1]), 1.0))
            g = self.graphics
            filters = f'scale={g.width}:{g.height}:force_original_aspect_ratio=decrease,pad={g.width}:{g.height}:(ow-iw)/2:(oh-ih)/2'
            result = subprocess.run(['ffmpeg','-v','error','-i',str(path),'-vn','-f','f32le',
                '-ac','2','-ar','44100','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            if result.returncode: raise RuntimeError('Video audio decode: '+result.stderr.decode(errors='replace'))
            if result.stdout:
                data = C.create_string_buffer(result.stdout)
                if self.audio.re4_audio_load(255,data,len(result.stdout),0):
                    raise RuntimeError("Cannot load decoded video audio")

            # Decode ahead on a worker: a raw frame is much larger than the
            # OS pipe, so reading only once per render tick throttles FFmpeg.
            self.video_queue = queue.Queue(maxsize=8)
            self.video_stop = threading.Event()
            self.video = subprocess.Popen(['ffmpeg','-v','error','-i',str(path),
                '-an','-vf','fps=30,'+filters,'-pix_fmt','rgb24','-f','rawvideo','pipe:1'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.video_reader = threading.Thread(target=self.read_video,
                args=(self.video, self.video_queue, self.video_stop, g.width*g.height*3),
                daemon=True)
            self.video_reader.start()
            try:
                self.video_frame = self.video_queue.get(timeout=30)
                if self.video_frame is None:
                    raise RuntimeError('Video decoder produced no frames: '+filename)
            except Exception:
                self.end_video()
                raise
            self.video_index = 0
            self.video_started = time.monotonic()
            if result.stdout:
                self.audio.re4_audio_play(255,volume)
            self.videos_played += 1
            log.info('Playing video: %s',filename)
            return 1
        if name == 'fileName': return arm.cstring(self.video_name)
        if name == 'getVolume':
            from .bionic import float_out
            return float_out(1.0)
        raise RuntimeError('Unknown video operation: '+name)

    @staticmethod
    def read_video(process, frames, stop, frame_size):
        def enqueue(frame):
            while not stop.is_set():
                try:
                    frames.put(frame, timeout=0.1)
                    return True
                except queue.Full:
                    pass
            return False

        while not stop.is_set():
            frame = process.stdout.read(frame_size)
            if len(frame) != frame_size:
                enqueue(None)
                return
            if not enqueue(frame):
                return

    def update_video(self):
        if self.video is None: return
        target = int((time.monotonic()-self.video_started)*30)
        while self.video_index < target:
            try: frame = self.video_queue.get_nowait()
            except queue.Empty: break
            if frame is None:
                self.end_video()
                return
            self.video_frame = frame
            self.video_index += 1
        if self.video_frame is not None:
            self.graphics.draw_video(self.video_frame)

    def end_video(self):
        if self.video is not None:
            process,self.video = self.video,None
            self.video_stop.set()
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            self.video_reader.join(timeout=3)
            process.stdout.close()
        self.video_queue = None
        self.video_reader = None
        self.video_stop = None
        self.video_frame = None
        self.audio.re4_audio_control(255,0,1.0)

    def close(self):
        self.end_video()
        self.audio.re4_audio_close()
