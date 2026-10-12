"""Rate-limited desktop runtime telemetry, including long engine calls."""
import logging
import os
import threading
import time

log = logging.getLogger('re4pc')


class ConsoleFormatter(logging.Formatter):
    COLORS = {logging.DEBUG: '\033[36m', logging.INFO: '\033[32m',
              logging.WARNING: '\033[33m', logging.ERROR: '\033[31m',
              logging.CRITICAL: '\033[1;31m'}

    def __init__(self, color=False):
        super().__init__('%(asctime)s %(levelname)-7s %(message)s', '%H:%M:%S')
        self.color = color

    def format(self, record):
        # Format a copy so file handlers and other consumers keep plain levels.
        if self.color and record.levelno in self.COLORS:
            record = logging.makeLogRecord(record.__dict__.copy())
            record.levelname = (self.COLORS[record.levelno] +
                                f'{record.levelname:<7}' + '\033[0m')
        return super().format(record)


def configure(level='info', path=None):
    console = logging.StreamHandler()
    color = ('FORCE_COLOR' in os.environ or
             ('NO_COLOR' not in os.environ and console.stream.isatty() and
              os.environ.get('TERM') != 'dumb'))
    console.setFormatter(ConsoleFormatter(color))
    handlers = [console]
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding='utf-8')
        file_handler.setFormatter(ConsoleFormatter())
        handlers.append(file_handler)
    logging.basicConfig(level=level.upper(), handlers=handlers, force=True)


class RuntimeLog:
    def __init__(self, interval=5, diagnostics=None):
        self.interval = interval
        self.diagnostics = diagnostics
        self.snapshot = ('startup', 0, 0, 0, False)
        self.started = self.sampled = time.monotonic()
        self.stopped = threading.Event()
        self.thread = None

    def __enter__(self):
        if self.interval:
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        return self

    def sample(self, game):
        self.diagnostics = getattr(game, 'diagnostics', self.diagnostics)
        state = ('video' if game.media.video is not None else
                 'story' if game.pc.story_active else
                 'gameplay' if game.pc.active else 'menu/loading')
        self.snapshot = (state, game.frames, game.graphics.draws,
                         game.input_events, game.mouse_captured)

    def _run(self):
        previous_frames = 0
        previous_time = self.started
        while not self.stopped.wait(self.interval):
            now = time.monotonic()
            state, frames, draws, inputs, captured = self.snapshot
            fps = (frames-previous_frames)/(now-previous_time)
            active = self.diagnostics.active_operation if self.diagnostics else None
            waiting = (' | operation=%s (%.2fs)' % (active['name'], active['seconds'])
                       if active else ' | waiting for engine/startup' if frames == previous_frames else '')
            log.info('runtime: %s | %.1f FPS | frame=%d draws=%d inputs=%d mouse=%s%s',
                     state, fps, frames, draws, inputs,
                     'captured' if captured else 'free',
                     waiting)
            previous_frames, previous_time = frames, now

    def __exit__(self, *args):
        self.stopped.set()
        if self.thread:
            self.thread.join()
