from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image, ImageOps

from re4pc import ui_images

ASSETS = Path(__file__).resolve().parent.parent / 're4pc/ui_assets'


class UiImageTests(unittest.TestCase):
    def setUp(self):
        ui_images.clear()
        self.addCleanup(ui_images.clear)

    def opened(self):
        original = Image.open
        calls = []
        def counting(path, *args, **kwargs):
            calls.append(Path(path).name)
            return original(path, *args, **kwargs)
        return calls, patch('re4pc.ui_images.Image.open', side_effect=counting)

    def test_cached_results_match_the_original_pillow_operations(self):
        with Image.open(ASSETS / 'case-seal.png') as image:
            rgba = image.convert('RGBA')
        bounds = rgba.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox()
        trimmed = rgba.crop(bounds)
        expected = ImageOps.contain(trimmed, (70, 70), Image.Resampling.LANCZOS)
        for _ in range(2):
            source = ui_images.source(ASSETS / 'case-seal.png', 'RGBA')
            self.assertEqual(source.tobytes(), rgba.tobytes())
            cached = ui_images.contained(ui_images.trimmed(source, 8), (70, 70))
            self.assertEqual((cached.mode, cached.size, cached.tobytes()),
                             (expected.mode, expected.size, expected.tobytes()))
        resized = trimmed.resize((40, 30), Image.Resampling.LANCZOS)
        self.assertEqual(ui_images.resized(ui_images.trimmed(source, 8), (40, 30)).tobytes(), resized.tobytes())
        # Achievement thumbnails: alpha bounds without a threshold, then contain.
        with Image.open(ASSETS / 'achievement-village.png') as image:
            rgba = image.convert('RGBA')
        expected = ImageOps.contain(rgba.crop(rgba.getchannel('A').getbbox()), (64, 64), Image.Resampling.LANCZOS)
        icon = ui_images.prepared(ASSETS / 'achievement-village.png', 'RGBA', ('trim', 0), ('contain', (64, 64)))
        self.assertEqual(icon.tobytes(), expected.tobytes())

    def test_each_source_is_decoded_once_and_derived_hits_need_no_decode(self):
        calls, opener = self.opened()
        with opener:
            first = ui_images.source(ASSETS / 'paperclip.png', 'RGBA')
            self.assertIs(ui_images.source(ASSETS / 'paperclip.png', 'RGBA'), first)
            self.assertIs(ui_images.resized(first, (20, 20)), ui_images.resized(first, (20, 20)))
            steps = (ASSETS / 'achievement-ashley.png', 'RGBA', ('trim', 0), ('contain', (40, 40)))
            icon = ui_images.prepared(*steps)
            self.assertIs(ui_images.prepared(*steps), icon)
        self.assertEqual(calls, ['paperclip.png', 'achievement-ashley.png'])

    def test_thumbnails_do_not_retain_or_evict_full_size_sources(self):
        paper = ui_images.source(ASSETS / 'case-paper-v2.png', 'RGB')
        ui_images.prepared(ASSETS / 'achievement-saddler.png', 'RGBA', ('trim', 0), ('contain', (40, 40)))
        self.assertIs(ui_images.source(ASSETS / 'case-paper-v2.png', 'RGB'), paper)
        cached = [key[1] for key in ui_images._sources.entries]
        self.assertEqual(cached, [str(ASSETS / 'case-paper-v2.png')])

    def test_budget_evicts_least_recently_used_entries(self):
        cache = ui_images._Cache(2 * 3 * 10 * 10)  # two 10x10 RGB images
        images = [Image.new('RGB', (10, 10)) for _ in range(3)]
        cache.put('a', images[0])
        cache.put('b', images[1])
        cache.get('a')
        cache.put('c', images[2])
        self.assertEqual(list(cache.entries), ['a', 'c'])
        self.assertEqual(cache.used, 600)
        cache.put('huge', Image.new('RGB', (100, 100)))
        self.assertNotIn('huge', cache.entries)

    def test_unshared_images_are_processed_without_caching(self):
        image = Image.new('RGBA', (8, 8), (1, 2, 3, 255))
        self.assertIsNot(ui_images.resized(image, (4, 4)), ui_images.resized(image, (4, 4)))
        self.assertEqual(ui_images._derived.entries, {})
        self.assertIsNone(ui_images.trimmed(Image.new('RGBA', (8, 8))))

    def test_missing_and_corrupt_artwork_raise_oserror(self):
        with tempfile.TemporaryDirectory() as directory:
            corrupt = Path(directory) / 'corrupt.png'
            corrupt.write_bytes(b'not a png')
            for path in (Path(directory) / 'missing.png', corrupt):
                with self.assertRaises(OSError):
                    ui_images.source(path, 'RGBA')
                with self.assertRaises(OSError):
                    ui_images.prepared(path, 'RGBA', ('trim', 0))
            self.assertEqual(ui_images._inflight, {})

    def test_concurrent_requests_share_one_decode(self):
        calls, opener = self.opened()
        release = threading.Event()
        original = Image.open
        def slow(path, *args, **kwargs):
            calls.append(Path(path).name)
            release.wait(5)
            return original(path, *args, **kwargs)
        results = []
        with patch('re4pc.ui_images.Image.open', side_effect=slow):
            workers = [threading.Thread(target=lambda: results.append(ui_images.source(ASSETS / 'backups.png', 'RGBA')))
                       for _ in range(4)]
            for worker in workers:
                worker.start()
            release.set()
            for worker in workers:
                worker.join(5)
        self.assertEqual(calls, ['backups.png'])
        self.assertEqual(len(results), 4)
        self.assertTrue(all(result is results[0] for result in results))

    def test_warm_prepares_in_background_and_ignores_missing_files(self):
        futures = ui_images.warm(sources=[(ASSETS / 'missing.png', 'RGBA'), (ASSETS / 'paperclip.png', 'RGBA')],
                                 prepared_items=[(ASSETS / 'achievement-krauser.png', 'RGBA', ('trim', 0), ('contain', (40, 40)))])
        for future in futures:
            future.result(10)
        calls, opener = self.opened()
        with opener:
            ui_images.source(ASSETS / 'paperclip.png', 'RGBA')
            ui_images.prepared(ASSETS / 'achievement-krauser.png', 'RGBA', ('trim', 0), ('contain', (40, 40)))
        self.assertEqual(calls, [])
        ui_images.shutdown()
        self.assertIsNone(ui_images._pool)


if __name__ == '__main__':
    unittest.main()
