from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from re4pc.texture_cache import TextureCache
from re4pc.textures import palette_texture


PALETTE = b''.join(bytes((i,0,0,255)) for i in range(256))
SOURCE = PALETTE + bytes((1,2,3,4,5))


class TextureCacheTests(unittest.TestCase):
    def test_immutable_memory_and_cross_runtime_disk_hits_match_uncached_output(self):
        expected = tuple(palette_texture(0x8b96,2,2,-1,SOURCE))
        with tempfile.TemporaryDirectory() as directory:
            cache = TextureCache(directory)
            result = cache.convert(0x8b96,2,2,-1,SOURCE)
            self.assertEqual(result,expected)
            self.assertIsInstance(result,tuple)
            self.assertIsInstance(result[0][3],bytes)
            with patch('re4pc.texture_cache.palette_texture',side_effect=AssertionError('conversion')):
                self.assertIs(cache.convert(0x8b96,2,2,-1,SOURCE,converter=lambda *_:self.fail('memory conversion')),result)
                another = TextureCache(directory)
                self.assertEqual(another.convert(0x8b96,2,2,-1,SOURCE,converter=lambda *_:self.fail('disk conversion')),expected)
            self.assertEqual(cache.metrics()['counters']['memory_hits'],1)
            self.assertEqual(another.metrics()['counters']['disk_hits'],1)

    def test_source_dimensions_mips_format_and_converter_version_invalidate(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = TextureCache(directory)
            for fmt,width,height,level,source in (
                (0x8b96,2,2,-1,SOURCE), (0x8b96,2,2,-1,SOURCE[:-1]+b'\x06'),
                (0x8b96,4,1,-1,SOURCE+b'\x07'), (0x8b96,2,2,0,SOURCE),
                (0x8b95,2,2,0,SOURCE)):
                result = cache.convert(fmt,width,height,level,source)
                self.assertEqual(result,tuple(palette_texture(fmt,width,height,level,source)))
            other = TextureCache(directory,converter_version='next-converter')
            self.assertEqual(other.convert(0x8b96,2,2,-1,SOURCE),tuple(palette_texture(0x8b96,2,2,-1,SOURCE)))
            self.assertEqual(other.metrics()['counters']['misses'],1)
            self.assertEqual(len(list(Path(directory).glob('*.tex'))),6)

    def test_checksum_corruption_and_truncation_recompute_and_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            expected = TextureCache(directory).convert(0x8b96,2,2,-1,SOURCE)
            path = next(Path(directory).glob('*.tex'))
            original = path.read_bytes()
            for bad in (original[:-1],original[:-1]+bytes((original[-1]^0xff,)),b'bad header'):
                path.write_bytes(bad)
                cache = TextureCache(directory)
                self.assertEqual(cache.convert(0x8b96,2,2,-1,SOURCE),expected)
                self.assertEqual(cache.metrics()['counters']['corruptions'],1)
                self.assertEqual(path.read_bytes(),original)

    def test_disabled_mode_does_not_hash_or_touch_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'must not exist'
            cache = TextureCache(path,enabled=False)
            with patch('re4pc.texture_cache.hashlib.sha256',side_effect=AssertionError('hashed')):
                self.assertEqual(cache.convert(0x8b96,2,2,-1,SOURCE),tuple(palette_texture(0x8b96,2,2,-1,SOURCE)))
            self.assertFalse(path.exists())
            self.assertEqual(cache.metrics()['memory_bytes'],0)

    def test_memory_and_disk_evict_within_bounds_and_ignore_foreign_files(self):
        with tempfile.TemporaryDirectory() as directory:
            foreign = Path(directory)/'notes.txt'
            foreign.write_text('preserve')
            cache = TextureCache(directory,max_memory_bytes=1100,max_disk_bytes=800)
            for index in range(10):
                cache.convert(0x8b96,2,2,-1,SOURCE[:-1]+bytes((index,)))
                self.assertLessEqual(cache.metrics()['memory_bytes'],1100)
                self.assertLessEqual(cache.metrics()['disk_bytes'],800)
                self.assertLessEqual(sum(p.stat().st_size for p in Path(directory).glob('*.tex')),800)
            self.assertGreater(cache.metrics()['counters']['disk_evictions'],0)
            self.assertGreater(cache.metrics()['counters']['memory_evictions'],0)
            self.assertEqual(foreign.read_text(),'preserve')
            self.assertEqual(list(Path(directory).glob('*.tmp')),[])

    def test_failed_atomic_publication_returns_correct_pixels_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = TextureCache(directory)
            with patch('re4pc.texture_cache.os.replace',side_effect=OSError('publication failed')):
                result = cache.convert(0x8b96,2,2,-1,SOURCE)
            self.assertEqual(result,tuple(palette_texture(0x8b96,2,2,-1,SOURCE)))
            self.assertEqual(cache.metrics()['counters']['io_errors'],1)
            self.assertEqual([p for p in Path(directory).iterdir() if p.name!='.cache.lock'],[])

    def test_oversized_entry_is_not_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = TextureCache(directory,max_memory_bytes=1,max_disk_bytes=1)
            cache.convert(0x8b96,2,2,-1,SOURCE)
            self.assertEqual(cache.metrics()['memory_bytes'],0)
            self.assertEqual([p for p in Path(directory).iterdir() if p.name!='.cache.lock'],[])

    def test_multiple_stale_writers_recount_shared_bound_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            first=TextureCache(directory,max_disk_bytes=800)
            second=TextureCache(directory,max_disk_bytes=800)
            for index in range(10):
                cache=first if index%2 else second
                cache.convert(0x8b96,2,2,-1,SOURCE[:-1]+bytes((index,)))
                self.assertLessEqual(sum(p.stat().st_size for p in Path(directory).glob('*.tex')),800)
            self.assertGreater(first.metrics()['counters']['disk_evictions'],0)
