"""Movie scheduling must follow elapsed time, including decoder EOF."""
import io
import queue
import threading
import unittest
import tempfile
from pathlib import Path
from concurrent.futures import Future, ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch
from re4pc.media import Media


class VideoTests(unittest.TestCase):
    def media(self):
        media = Media.__new__(Media)
        media.video = Mock()
        media.video_started = 100.0
        media.video_index = 0
        media.video_frame = b'first'
        media.video_queue = queue.Queue()
        media.graphics = Mock()
        return media

    def test_frames_wait_for_clock_and_catch_up_after_slow_render(self):
        media = self.media()
        for frame in (b'second', b'third', b'fourth'):
            media.video_queue.put(frame)
        with patch('re4pc.media.time.monotonic', return_value=100.01):
            media.update_video()
        self.assertEqual(media.video_index, 0)
        media.graphics.draw_video.assert_called_with(b'first')
        with patch('re4pc.media.time.monotonic', return_value=100.105):
            media.update_video()
        self.assertEqual(media.video_index, 3)
        media.graphics.draw_video.assert_called_with(b'fourth')

    def test_decoder_exit_does_not_discard_buffered_frames(self):
        media = self.media()
        media.video_queue.put(b'last')
        media.video_queue.put(None)
        media.end_video = Mock()
        with patch('re4pc.media.time.monotonic', return_value=100.04):
            media.update_video()
        media.end_video.assert_not_called()
        media.graphics.draw_video.assert_called_with(b'last')
        with patch('re4pc.media.time.monotonic', return_value=100.07):
            media.update_video()
        media.end_video.assert_called_once()

    def test_reader_delivers_complete_frames_and_eof(self):
        frames = queue.Queue()
        Media.read_video(SimpleNamespace(stdout=io.BytesIO(b'abcdefg')),
                         frames, threading.Event(), 3)
        self.assertEqual([frames.get_nowait() for _ in range(3)],
                         [b'abc', b'def', None])

    def test_reader_can_stop_while_queue_is_full(self):
        frames = queue.Queue(maxsize=1)
        stop = threading.Event()
        reader = threading.Thread(target=Media.read_video,
            args=(SimpleNamespace(stdout=io.BytesIO(b'abcdef')), frames, stop, 3))
        reader.start()
        self.assertEqual(frames.get(timeout=1), b'abc')
        stop.set()
        reader.join(timeout=1)
        self.assertFalse(reader.is_alive())


class AsyncMediaTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.media = Media.__new__(Media)
        m = self.media
        m.root = Path(self.directory.name)
        m.cache = m.root / 'cache'
        m.cache.mkdir()
        m.decoder = ThreadPoolExecutor(max_workers=2)
        self.addCleanup(m.decoder.shutdown)
        m.cleanup = Mock()
        m.audio = Mock()
        m.audio.re4_audio_load.return_value = 0
        m.decoded, m.decoding, m.audio_sources = {}, {}, {}
        m.audio_ready, m.paused_audio = set(), set()
        m.audio_volumes = {}
        m.retired_videos = []
        m.pending_audio = {}
        m.loaded = m.videos_played = 0
        m.video = m.video_frame = m.video_started = m.video_audio = None
        m.video_queue = m.video_stop = m.video_reader = None
        m.skip_videos = False
        m.graphics = Mock(width=800, height=480)
        self.path = m.root / 'data/monhun/sample'
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b'encoded')
        self.arm = Mock()
        self.arm.string.return_value = 'sample'

    def load(self, slot=0, bgm=False):
        return self.media.audio_service('loadBGM' if bgm else 'loadSE',
            [slot, 1, 0, 7, int(bgm)], self.arm)

    def future(self, slot=0, bgm=False):
        key = (str(self.path), 0, 7, False)
        future = Future()
        self.media.decoding[key] = future
        self.load(slot, bgm)
        return future

    def test_unready_audio_never_waits_on_main_thread(self):
        future = self.future()
        m = self.media
        m.audio_service('playSE', [0, 0.5], self.arm)
        m.update_audio()
        m.audio.re4_audio_play.assert_not_called()
        future.set_result(b'\0'*8)
        m.update_audio()
        m.audio.re4_audio_play.assert_called_once_with(0, 0.5)
        self.assertEqual(m.pending_audio, {})
        m.update_audio()
        m.audio.re4_audio_load.assert_called_once()

    def test_unused_sound_bank_is_not_decoded(self):
        self.load()
        self.assertEqual(self.media.decoding, {})

    def test_stop_cancels_a_pending_sound(self):
        future = self.future()
        m = self.media
        m.audio_service('playSE', [0, 1.0], self.arm)
        m.audio_service('stopSE', [0], self.arm)
        future.set_result(b'\0'*8)
        m.update_audio()
        m.audio.re4_audio_play.assert_not_called()

    def test_pause_and_restart_preserve_pending_bgm(self):
        future = self.future(bgm=True)
        m = self.media
        m.audio_service('playBGM', [0], self.arm)
        m.audio_service('pauseBGM', [0], self.arm)
        future.set_result(b'\0'*8)
        m.update_audio()
        m.audio.re4_audio_play.assert_not_called()
        m.audio_service('restartBGM', [0], self.arm)
        m.update_audio()
        m.audio.re4_audio_play.assert_called_once_with(128, 1.0)

    def test_reload_does_not_play_a_stale_request(self):
        future = self.future()
        m = self.media
        m.audio_service('playSE', [0, 1.0], self.arm)
        self.load()
        future.set_result(b'\0'*8)
        m.update_audio()
        m.audio.re4_audio_play.assert_not_called()

    def test_term_releases_readiness_before_reloading(self):
        future = self.future()
        future.set_result(b'\0'*8)
        m = self.media
        m.audio_service('playSE', [0, 1.0], self.arm)
        m.audio_service('termSE', [0], self.arm)
        self.assertNotIn(0, m.audio_ready)
        self.assertNotIn(0, m.audio_sources)
        self.load()
        m.audio_service('playSE', [0, 1.0], self.arm)
        self.assertEqual(m.audio.re4_audio_load.call_count, 2)

    def test_volume_is_retained_while_decoding(self):
        future = self.future()
        m = self.media
        m.audio_service('playSE', [0, 1.0], self.arm)
        m.audio_service('setVolumeSE', [0, 0.25], self.arm)
        future.set_result(b'\0'*8)
        m.update_audio()
        m.audio.re4_audio_control.assert_called_with(0, 3, 0.25)

    def test_duplicate_resources_share_one_decode(self):
        m = self.media
        with patch.object(m.decoder, 'submit', return_value=Future()) as submit:
            m.queue_audio(self.path, 0, 7)
            m.queue_audio(self.path, 0, 7)
        submit.assert_called_once()

    def test_worker_decode_failure_is_reported(self):
        future = self.future()
        m = self.media
        m.audio_service('playSE', [0, 1.0], self.arm)
        future.set_exception(RuntimeError('bad sound'))
        with self.assertRaisesRegex(RuntimeError, 'bad sound'): m.update_audio()

    def test_video_start_returns_before_decoders_are_ready(self):
        m = self.media
        future = Future()
        with patch.object(m.decoder, 'submit', return_value=future), \
                patch('re4pc.media.subprocess.Popen', return_value=Mock()) as popen, \
                patch('re4pc.media.threading.Thread'):
            self.assertEqual(m.video_service('start', [1, 0.5], self.arm), 1)
        m.update_video()
        m.graphics.draw_video.assert_not_called()
        future.set_result(b'\0'*8)
        m.video_queue.put(b'frame')
        m.update_video()
        m.audio.re4_audio_play.assert_called_once_with(255, 0.5)
        m.graphics.draw_video.assert_called_once_with(b'frame')
        process = popen.return_value
        process.poll.return_value = None
        m.end_video()
        self.assertIsNone(m.video)
        process.terminate.assert_called_once()
        process.wait.assert_not_called()
        m.cleanup.submit.assert_called_once()
        m.video_service('nowPlaying', [], self.arm)
        self.assertIsNone(m.video_audio)

    def test_skip_pending_video_cannot_start_audio_later(self):
        m = self.media
        future = Future()
        with patch.object(m.decoder, 'submit', return_value=future), \
                patch('re4pc.media.subprocess.Popen'), \
                patch('re4pc.media.threading.Thread'):
            m.video_service('start', [1, 1.0], self.arm)
        m.end_video()
        future.set_result(b'\0'*8)
        m.update_video()
        m.audio.re4_audio_play.assert_not_called()

    def test_video_reaper_kills_an_unresponsive_decoder(self):
        import subprocess
        process, reader = Mock(), Mock()
        process.wait.side_effect = [subprocess.TimeoutExpired('ffmpeg', 1), 0]
        Media.reap_video(process, reader)
        process.kill.assert_called_once()
        reader.join.assert_called_once_with(timeout=1)
        process.stdout.close.assert_called_once()
