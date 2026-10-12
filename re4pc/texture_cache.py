"""Bounded, content-addressed immutable RGBA texture conversion cache.

This stores host pixels only. Guest pointers and GL objects never cross runs.
Filesystem failures or corrupt entries cause a normal conversion, not a game
failure. A converter-version change invalidates every prior representation.
"""
from collections import Counter, OrderedDict
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile

from .textures import palette_texture

CONVERTER_VERSION = 'oes-palette-rgba-v1'
MAGIC = b'RE4TEX1\0'
MAX_HEADER = 16384


class TextureCache:
    def __init__(self, directory=None, enabled=True, max_memory_bytes=64*1024*1024,
                 max_disk_bytes=256*1024*1024, diagnostics=None,
                 converter_version=CONVERTER_VERSION):
        if max_memory_bytes < 0 or max_disk_bytes < 0:
            raise ValueError('Cache limits must be nonnegative')
        self.directory = Path(directory) if directory is not None else None
        self.enabled = bool(enabled)
        self.max_memory_bytes, self.max_disk_bytes = max_memory_bytes, max_disk_bytes
        self.diagnostics, self.converter_version = diagnostics, converter_version
        self._memory, self._disk = OrderedDict(), OrderedDict()
        self._memory_bytes = self._disk_bytes = 0
        self._indexed = False
        self._counts = Counter()

    def _count(self, name):
        self._counts[name] += 1
        if self.diagnostics:
            self.diagnostics.count('texture_cache_'+name)

    def _metadata(self, fmt, width, height, level, data):
        return {'version': self.converter_version, 'format': fmt, 'width': width,
                'height': height, 'level': level,
                'source_sha256': hashlib.sha256(data).hexdigest()}

    @staticmethod
    def _key(metadata):
        return hashlib.sha256(json.dumps(metadata, sort_keys=True,
                             separators=(',', ':')).encode()).hexdigest()

    @staticmethod
    def _immutable(images):
        return tuple((mip, width, height, bytes(pixels)) for mip, width, height, pixels in images)

    def convert(self, fmt, width, height, level, data, converter=palette_texture):
        if not self.enabled:
            self._count('disabled')
            return self._immutable(converter(fmt, width, height, level, data))
        metadata = self._metadata(fmt, width, height, level, data)
        key = self._key(metadata)
        if key in self._memory:
            images, size = self._memory.pop(key)
            self._memory[key] = (images, size)
            self._count('memory_hits')
            return images
        images = self._read(key, metadata)
        if images is not None:
            self._count('disk_hits')
            self._remember(key, images)
            return images
        self._count('misses')
        images = self._immutable(converter(fmt, width, height, level, data))
        self._remember(key, images)
        self._write(key, metadata, images)
        return images

    def _remember(self, key, images):
        # Include a conservative allowance for tuples/dictionary/key overhead.
        size = 512 + sum(len(image[3])+256 for image in images)
        if size > self.max_memory_bytes:
            return
        while self._memory and self._memory_bytes+size > self.max_memory_bytes:
            _, (_, old_size) = self._memory.popitem(last=False)
            self._memory_bytes -= old_size
            self._count('memory_evictions')
        self._memory[key] = (images, size)
        self._memory_bytes += size

    @contextmanager
    def _publication_lock(self):
        with (self.directory/'.cache.lock').open('a+b') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _index(self):
        if self._indexed:
            return
        self._indexed = True
        if self.directory is None or not self.max_disk_bytes:
            return
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with self._publication_lock():
                self._scan_disk()
                self._prune()
        except OSError:
            self._count('io_errors')

    def _scan_disk(self):
        self._remove_abandoned_writes()
        entries = []
        for path in self.directory.glob('*.tex'):
            # Cache owns only its digest-named entries, never other files.
            if len(path.stem) != 64 or any(c not in '0123456789abcdef' for c in path.stem):
                continue
            if not path.is_file() or path.is_symlink():
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            entries.append((stat.st_mtime_ns, path.stem, stat.st_size))
        self._disk.clear()
        self._disk_bytes = 0
        for _, key, size in sorted(entries):
            self._disk[key] = size
            self._disk_bytes += size

    def _remove_abandoned_writes(self):
        # PID-scoped temporaries let the next runtime remove interrupted writes
        # without racing another running instance's atomic publication.
        for path in self.directory.glob('.texture-*.tmp'):
            try:
                pid = int(path.name.split('-')[1])
            except (ValueError, IndexError):
                continue
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                path.unlink(missing_ok=True)
            except PermissionError:
                pass

    def _prune(self):
        while self._disk and self._disk_bytes > self.max_disk_bytes:
            key, size = next(iter(self._disk.items()))
            try:
                (self.directory / (key+'.tex')).unlink(missing_ok=True)
            except OSError:
                self._count('io_errors')
                break
            self._disk.pop(key)
            self._disk_bytes -= size
            self._count('disk_evictions')

    def _read(self, key, metadata):
        if self.directory is None or not self.max_disk_bytes:
            return None
        self._index()
        path = self.directory/(key+'.tex')
        try:
            if path.is_symlink():
                return None
            with path.open('rb') as stream:
                # A hostile/corrupt file must not defeat the memory bound.
                if os.fstat(stream.fileno()).st_size > self.max_disk_bytes:
                    raise ValueError('Oversized cache entry')
                if stream.read(len(MAGIC)) != MAGIC:
                    raise ValueError('Invalid cache magic')
                size_bytes = stream.read(4)
                if len(size_bytes) != 4:
                    raise ValueError('Truncated cache header size')
                size = struct.unpack('<I', size_bytes)[0]
                if size > MAX_HEADER:
                    raise ValueError('Oversized cache header')
                header = json.loads(stream.read(size))
                if header['source'] != metadata:
                    raise ValueError('Cache source mismatch')
                images = []
                digest = hashlib.sha256()
                descriptors = header['images']
                if len(descriptors) != 1-metadata['level']:
                    raise ValueError('Invalid cache mip count')
                for index, (mip, width, height) in enumerate(descriptors):
                    if (mip, width, height) != (index, max(1, metadata['width']>>index),
                                               max(1, metadata['height']>>index)):
                        raise ValueError('Invalid cached dimensions')
                    byte_count = width*height*4
                    if byte_count > self.max_disk_bytes:
                        raise ValueError('Oversized cached pixels')
                    pixels = stream.read(byte_count)
                    if len(pixels) != byte_count:
                        raise ValueError('Truncated cached pixels')
                    digest.update(pixels)
                    images.append((mip, width, height, pixels))
                if stream.read(1) or digest.hexdigest() != header['sha256']:
                    raise ValueError('Corrupt cached pixels')
            if key in self._disk:
                self._disk.move_to_end(key)
            return tuple(images)
        except FileNotFoundError:
            return None
        except (ValueError, KeyError, TypeError, OverflowError, UnicodeDecodeError, RecursionError):
            self._count('corruptions')
            try:
                path.unlink(missing_ok=True)
                self._disk_bytes -= self._disk.pop(key, 0)
            except OSError:
                self._count('io_errors')
            return None
        except OSError:
            self._count('io_errors')
            return None

    def _write(self, key, metadata, images):
        if self.directory is None or not self.max_disk_bytes:
            return
        self._index()
        digest = hashlib.sha256()
        for image in images:
            digest.update(image[3])
        header = json.dumps({'source': metadata, 'images': [image[:3] for image in images],
                    'sha256': digest.hexdigest()}, separators=(',', ':')).encode()
        size = len(MAGIC)+4+len(header)+sum(len(image[3]) for image in images)
        if size > self.max_disk_bytes or len(header) > MAX_HEADER:
            return
        temporary = None
        try:
            descriptor, temporary = tempfile.mkstemp(prefix=f'.texture-{os.getpid()}-', suffix='.tmp', dir=self.directory)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(MAGIC)
                stream.write(struct.pack('<I', len(header)))
                stream.write(header)
                for image in images:
                    stream.write(image[3])
                stream.flush()
                os.fsync(stream.fileno())
            with self._publication_lock():
                # Other installations can share this content cache. Recount
                # only at publication, so ordinary cache hits stay cheap.
                self._scan_disk()
                os.replace(temporary, self.directory/(key+'.tex'))
                self._disk_bytes -= self._disk.pop(key, 0)
                self._disk[key] = size
                self._disk_bytes += size
                self._count('writes')
                self._prune()
        except OSError:
            self._count('io_errors')
        finally:
            if temporary is not None:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass

    def metrics(self):
        return {'enabled': self.enabled, 'converter_version': self.converter_version,
            'memory_bytes': self._memory_bytes, 'memory_limit_bytes': self.max_memory_bytes,
            'disk_bytes': self._disk_bytes, 'disk_limit_bytes': self.max_disk_bytes,
            'memory_entries': len(self._memory), 'disk_entries': len(self._disk),
            'counters': dict(self._counts)}
