"""Movie scheduling must follow elapsed time, including decoder EOF."""
import io
import queue
import threading
import unittest
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
