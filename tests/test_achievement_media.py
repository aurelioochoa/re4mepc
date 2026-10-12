import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from re4pc.achievement_media import UnlockCapture, media_path
from re4pc.achievements import AchievementStore, Progress


class UnlockCaptureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = AchievementStore(self.root)
        self.store.update(Progress(story=(True,) + (False,) * 21))

    def capture(self, mode='screenshot', seconds=5):
        capture = UnlockCapture(self.root, self.store,
                                {'achievement_capture':mode, 'achievement_clip_seconds':seconds})
        self.addCleanup(capture.close)
        return capture

    def test_off_and_idle_screenshot_do_not_read_frame(self):
        read = Mock()
        self.capture('off').tick(read, ['village'])
        self.capture().tick(read)
        read.assert_not_called()
        self.assertFalse((self.root / 'achievement-media').exists())

    def test_screenshot_is_saved_linked_and_preserves_records(self):
        capture = self.capture()
        capture.tick(lambda: Image.new('RGB', (80, 48), 'red'), ['village'])
        capture.close()
        records, earned = self.store.load()
        path = media_path(self.root, self.store.media['village']['image'])
        with Image.open(path) as image:
            self.assertEqual(image.getpixel((40, 24)), (255, 0, 0))
        self.assertIn('village', earned)
        self.assertTrue(records.story[0])
        self.assertEqual(list(path.parent.glob('*.tmp.*')), [])

    def test_background_failure_does_not_remove_unlocks(self):
        capture = self.capture()
        with patch('PIL.Image.Image.save', side_effect=OSError('disk full')):
            capture.tick(lambda: Image.new('RGB', (80, 48)), ['village'])
            capture.close()
        self.assertIn('village', self.store.load()[1])
        self.assertEqual(self.store.media, {})

    def test_clip_buffer_is_bounded_and_ffmpeg_failure_keeps_screenshot(self):
        capture = self.capture('both')
        image = Image.new('RGB', (80, 48), 'green')
        for index in range(100):
            capture.tick(lambda:image, now=index * .21)
        self.assertEqual(len(capture.history), 25)
        with patch('re4pc.achievement_media.subprocess.run', side_effect=subprocess.TimeoutExpired('ffmpeg', 15)):
            capture.tick(lambda:image, ['village'], now=22)
            capture.close()
        self.store.load()
        self.assertIn('image', self.store.media['village'])
        self.assertNotIn('clip', self.store.media['village'])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg required')
    def test_real_ffmpeg_clip_is_playable_and_linked(self):
        capture = self.capture('clip')
        for index in range(8):
            capture.tick(lambda:Image.new('RGB', (80, 48), (index * 20, 20, 30)), now=index * .21)
        capture.tick(lambda:Image.new('RGB', (80, 48), 'blue'), ['village'], now=2)
        capture.close()
        self.store.load()
        clip = media_path(self.root, self.store.media['village']['clip'])
        result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(clip), '-f', 'null', '-'],
                                capture_output=True, check=True)
        self.assertEqual(result.stderr, b'')
        self.assertGreater(clip.stat().st_size, 100)

    def test_traversal_and_missing_media_rejected(self):
        with self.assertRaises(OSError):
            media_path(self.root, '../../elsewhere.png')
        with self.assertRaises(OSError):
            media_path(self.root, 'unlock-missing.png')
