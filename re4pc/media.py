"""Decode original game audio via FFmpeg and play it using SDL's audio device."""
import ctypes as C
from .runtime_log import log
from .paths import native_library, ffmpeg_binary
import hashlib
import subprocess
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

class Media:
    def __init__(self, root, sdl, graphics=None):
        self.root, self.sdl = Path(root).resolve(), sdl
        native = native_library('libre4audio.so')
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
        self.audio_volumes = {}
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
        self.decoder = ThreadPoolExecutor(max_workers=2, thread_name_prefix='re4-audio')
        self.cleanup = ThreadPoolExecutor(max_workers=1, thread_name_prefix='re4-video-cleanup')
        self.decoding = {}
        self.pending_audio = {}
        self.paused_audio = set()
        self.video_audio = None
        self.video_volume = 1.0
        self.video_started = None
        self.retired_videos = []

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
            self.pending_audio.pop(slot, None)
            self.paused_audio.discard(slot)
            self.audio_volumes[slot] = 1.0
            self.audio.re4_audio_control(slot, 4, 1.0)
            self.audio_ready.discard(slot)
            self.loaded += 1
            # The engine registers hundreds of SEs but plays only a handful
            # in a menu. Avoid decoding the entire bank ahead of a movie/BGM.
            if bgm: self.queue_audio(path, offset, length)
            return 1
        if name in ('playBGM', 'playSE'):
            volume = 1.0 if bgm else args[1]
            if self.prepare_audio(slot) and slot not in self.paused_audio:
                self.audio.re4_audio_play(slot, volume)
            else:
                pending = self.pending_audio.setdefault(slot, [])
                # Match the mixer's finite voice count; a slow decoder must
                # not accumulate an unlimited queue of repeated effects.
                if bgm: pending.clear()
                if len(pending) < 32: pending.append(volume)
            return 0
        for prefix, operation in (('stop',0),('pause',1),('restart',2),('setVolume',3),('term',4)):
            if name.startswith(prefix):
                if operation in (0, 4): self.pending_audio.pop(slot, None)
                if operation == 1: self.paused_audio.add(slot)
                elif operation in (0, 2, 4): self.paused_audio.discard(slot)
                if operation == 4:
                    self.audio_ready.discard(slot)
                    self.audio_sources.pop(slot, None)
                    self.audio_volumes.pop(slot, None)
                elif operation == 3:
                    self.audio_volumes[slot] = args[1]
                self.audio.re4_audio_control(slot, operation, args[1] if operation==3 else 1.0)
                return 0
        raise RuntimeError('Unknown audio operation: ' + name)

    def queue_audio(self, path, offset, length, video=False):
        key = (str(path), offset, length, video)
        if key not in self.decoding:
            self.decoding[key] = self.decoder.submit(self.decode_audio, path, offset, length, video)
        return key

    def decode_audio(self, path, offset, length, video=False):
        # Workers only read resources/decode PCM; SDL and guest state stay on
        # the main thread. File input for movies permits FFmpeg to seek.
        with path.open('rb') as stream:
            stream.seek(offset)
            source = stream.read(length)
        cached = self.cache / (hashlib.sha256(source).hexdigest() + '.f32')
        if cached.is_file(): return cached.read_bytes()
        result = subprocess.run([ffmpeg_binary(),'-v','error','-threads','1','-i',str(path) if video else 'pipe:0',
            '-vn','-f','f32le','-ac','2','-ar','44100','pipe:1'],
            input=None if video else source, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=30)
        if result.returncode or (not video and not result.stdout):
            raise RuntimeError('Audio decode: '+result.stderr.decode(errors='replace'))
        # Two resources can contain identical encoded bytes. Atomic replace
        # prevents another worker/process from reading a partial cache file.
        import tempfile
        with tempfile.NamedTemporaryFile(dir=self.cache, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(result.stdout)
        try: temporary.replace(cached)
        finally: temporary.unlink(missing_ok=True)
        return result.stdout

    def prepare_audio(self, slot):
        if slot in self.audio_ready: return True
        path, offset, length, loop = self.audio_sources[slot]
        key = self.queue_audio(path, offset, length)
        future = self.decoding[key]
        if not future.done(): return False
        if key not in self.decoded: self.decoded[key] = future.result()
        data = self.decoded[key]
        buffer = C.c_char_p(data)
        if self.audio.re4_audio_load(slot,buffer,len(data),loop):
            raise RuntimeError('Cannot load decoded audio')
        self.audio.re4_audio_control(slot, 3, self.audio_volumes.get(slot, 1.0))
        self.audio_ready.add(slot)
        return True

    def update_audio(self):
        for slot, volumes in list(self.pending_audio.items()):
            if slot in self.paused_audio or not self.prepare_audio(slot): continue
            for volume in volumes: self.audio.re4_audio_play(slot, volume)
            del self.pending_audio[slot]

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
            key = self.queue_audio(path, 0, path.stat().st_size, video=True)
            self.video_audio = self.decoding[key]
            self.video_volume = volume

            # Decode ahead on a worker: a raw frame is much larger than the
            # OS pipe, so reading only once per render tick throttles FFmpeg.
            self.video_queue = queue.Queue(maxsize=8)
            self.video_stop = threading.Event()
            self.video = subprocess.Popen([ffmpeg_binary(),'-v','error','-threads','1','-filter_threads','1','-i',str(path),
                '-an','-vf','fps=30,'+filters,'-pix_fmt','rgb24','-f','rawvideo','pipe:1'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.video_reader = threading.Thread(target=self.read_video,
                args=(self.video, self.video_queue, self.video_stop, g.width*g.height*3),
                daemon=True)
            self.video_reader.start()
            self.video_index = 0
            self.video_started = None
            self.video_requested = time.monotonic()
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
        if self.video_started is None:
            if time.monotonic() - self.video_requested > 30:
                raise TimeoutError('Video decoder startup timed out: '+self.video_name)
            if not self.video_audio.done(): return
            if self.video_frame is None:
                try: self.video_frame = self.video_queue.get_nowait()
                except queue.Empty: return
                if self.video_frame is None:
                    raise RuntimeError('Video decoder produced no frames: '+self.video_name)
            pcm = self.video_audio.result()
            if pcm:
                buffer = C.c_char_p(pcm)
                if self.audio.re4_audio_load(255, buffer, len(pcm), 0):
                    raise RuntimeError('Cannot load decoded video audio')
                self.audio.re4_audio_play(255, self.video_volume)
            self.video_started = time.monotonic()
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
        outstanding = []
        for future in self.retired_videos:
            if future.done(): future.result()
            else: outstanding.append(future)
        self.retired_videos = outstanding
        if self.video is not None:
            process,self.video = self.video,None
            self.video_stop.set()
            if process.poll() is None:
                process.terminate()
            self.retired_videos.append(self.cleanup.submit(self.reap_video, process, self.video_reader))
        self.video_queue = None
        self.video_reader = None
        self.video_stop = None
        self.video_frame = None
        self.video_audio = None
        self.video_started = None
        self.audio.re4_audio_control(255,4,1.0)

    @staticmethod
    def reap_video(process, reader):
        try: process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        reader.join(timeout=1)
        process.stdout.close()

    def close(self):
        try:
            self.end_video()
        finally:
            self.decoder.shutdown(wait=True, cancel_futures=True)
            self.cleanup.shutdown(wait=True)
            self.audio.re4_audio_close()
        for future in self.retired_videos: future.result()
