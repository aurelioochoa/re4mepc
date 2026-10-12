"""Bounded, optional unlock captures. Encoding never runs in an ARM hook."""
import collections
import concurrent.futures
import os
import subprocess
import time
import uuid
from pathlib import Path

from .paths import ffmpeg_binary
from .runtime_log import log

CLIP_FPS = 5
CLIP_SIZE = (400, 240)


class UnlockCapture:
    def __init__(self, root, store, settings):
        self.directory = Path(root) / 'achievement-media'
        self.store = store
        self.mode = settings.get('achievement_capture', 'screenshot')
        self.seconds = settings.get('achievement_clip_seconds', 10)
        self.history = collections.deque(maxlen=CLIP_FPS * self.seconds)
        self.last_frame = -1.0
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='unlock-capture')
        self.jobs = []

    def tick(self, read_frame, identifiers=(), now=None):
        if self.mode == 'off':
            return
        now = time.monotonic() if now is None else now
        self.jobs[:] = [job for job in self.jobs if not job.done()]
        clip = self.mode in ('clip', 'both')
        sample = clip and (now - self.last_frame >= 1 / CLIP_FPS)
        if not sample and not identifiers:
            return
        try:
            image = read_frame().convert('RGB')
            if sample or (clip and identifiers):
                from PIL import Image
                frame = image.resize(CLIP_SIZE, Image.Resampling.BILINEAR).tobytes()
                self.history.append(frame)
                self.last_frame = now
            if identifiers:
                if len(self.jobs) >= 2:
                    log.warning('Unlock capture queue is full; achievements are still recorded')
                    return
                frames = tuple(self.history) if clip else ()
                self.jobs.append(self.pool.submit(self._save, tuple(identifiers), image, frames))
        except (OSError, ValueError, RuntimeError) as error:
            log.warning('Could not capture achievement frame: %s', error)

    def _save(self, identifiers, image, frames):
        captures = {}
        name = 'unlock-' + str(time.time_ns()) + '-' + uuid.uuid4().hex[:8]
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            if self.mode in ('screenshot', 'both'):
                destination = self.directory / (name + '.png')
                temporary = destination.with_suffix('.tmp.png')
                try:
                    image.save(temporary, format='PNG')
                    os.replace(temporary, destination)
                    captures['image'] = destination.name
                finally:
                    temporary.unlink(missing_ok=True)
            if frames:
                destination = self.directory / (name + '.mp4')
                temporary = destination.with_suffix('.tmp.mp4')
                try:
                    command = [ffmpeg_binary(), '-hide_banner', '-loglevel', 'error', '-y',
                               '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size',
                               '400x240', '-framerate', str(CLIP_FPS), '-i', 'pipe:0',
                               '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '26',
                               '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(temporary)]
                    subprocess.run(command, input=b''.join(frames), stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, timeout=15, check=True)
                    os.replace(temporary, destination)
                    captures['clip'] = destination.name
                except (OSError, subprocess.SubprocessError) as error:
                    log.warning('Could not encode achievement clip: %s', error)
                finally:
                    temporary.unlink(missing_ok=True)
            if captures:
                self.store.attach_media(identifiers, captures)
        except (OSError, ValueError) as error:
            log.warning('Could not save achievement media: %s', error)

    def close(self):
        self.pool.shutdown(wait=True)
        self.history.clear()


def media_path(root, filename):
    """Only validated relative filenames from achievement records are accepted."""
    directory = Path(root).resolve() / 'achievement-media'
    path = (directory / filename).resolve()
    if path.parent != directory.resolve() or not path.is_file():
        raise OSError('This achievement capture is no longer available')
    return path


def draw_icon(canvas, item, unlocked):
    """Original vector badges: readable at small sizes, no shipped game artwork."""
    platinum = item.kind == 'platinum'
    accent = '#c4dcdf' if platinum else '#ccac72' if unlocked else '#69746d'
    canvas.create_oval(4, 4, 60, 60, outline=accent, width=2)
    canvas.create_oval(8, 8, 56, 56, outline='#38453d', width=1)
    if platinum:
        canvas.create_polygon(17, 39, 14, 23, 25, 29, 32, 17, 39, 29, 50, 23, 47, 39,
                              fill='', outline=accent, width=2)
        canvas.create_line(19, 44, 45, 44, fill=accent, width=3)
    elif item.kind in ('purchase', 'upgrade'):
        canvas.create_polygon(16, 24, 46, 24, 46, 33, 34, 33, 28, 45, 19, 45,
                              23, 32, 16, 32, fill='', outline=accent, width=2)
        canvas.create_line(20, 20, 44, 20, fill=accent, width=2)
        if item.kind == 'upgrade':
            canvas.create_line(41, 37, 51, 37, fill=accent, width=2)
            canvas.create_line(46, 32, 46, 42, fill=accent, width=2)
    elif item.kind in ('s_rank', 'all_s', 'all_difficulties_s'):
        canvas.create_text(32, 32, text='S', fill=accent, font=('DejaVu Sans', 25, 'bold'))
    elif item.kind == 'mission':
        canvas.create_polygon(32, 15, 47, 21, 44, 38, 32, 49, 20, 38, 17, 21,
                              fill='', outline=accent, width=2)
        canvas.create_line(25, 36, 39, 24, fill=accent, width=3)
        canvas.create_line(28, 24, 39, 36, fill=accent, width=2)
    else:
        canvas.create_polygon(19, 18, 45, 18, 41, 34, 32, 40, 23, 34,
                              fill='', outline=accent, width=2)
        canvas.create_line(32, 40, 32, 47, fill=accent, width=2)
        canvas.create_line(24, 48, 40, 48, fill=accent, width=3)
        canvas.create_arc(12, 18, 29, 35, start=90, extent=180, outline=accent, width=2)
        canvas.create_arc(35, 18, 52, 35, start=270, extent=180, outline=accent, width=2)
