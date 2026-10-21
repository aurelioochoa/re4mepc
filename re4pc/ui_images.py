"""Decode launcher artwork once per process and reuse resampled copies.

Artwork files are never rewritten or re-encoded; this only memoizes the exact
Pillow operations the launcher already performs. Returned images are shared
and must be treated as read-only: crop, resize or copy before drawing on them.
"""
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image, ImageOps

# Full-size sources are a few MB each; resampled copies are mostly small.
SOURCE_BUDGET = 64 * 1024 * 1024
DERIVED_BUDGET = 64 * 1024 * 1024
# Stable description of how a shared image was produced. Derived entries are
# keyed on it rather than on the input object, so they never pin a full-size
# source in memory after the source cache has evicted it.
KEY = '_re4_ui_image_key'


def _cost(image):
    return len(image.getbands()) * image.width * image.height


class _Cache:
    def __init__(self, budget):
        self.budget, self.used = budget, 0
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            image = self.entries.get(key)
            if image is not None:
                self.entries.move_to_end(key)
            return image

    def put(self, key, image):
        setattr(image, KEY, key)
        cost = _cost(image)
        with self.lock:
            if key in self.entries or cost > self.budget:
                return
            self.entries[key] = image
            self.used += cost
            while self.used > self.budget:
                self.used -= _cost(self.entries.popitem(last=False)[1])

    def clear(self):
        with self.lock:
            self.entries.clear()
            self.used = 0


_sources = _Cache(SOURCE_BUDGET)
_derived = _Cache(DERIVED_BUDGET)


_inflight = {}
_inflight_lock = threading.Lock()


def _single_flight(key, cache, compute):
    """Return the cached value or compute it once, even across threads.

    A dialog that needs artwork while the background warm-up is decoding the
    same file waits for that decode instead of repeating it.
    """
    while True:
        value = cache.get(key)
        if value is not None:
            return value
        with _inflight_lock:
            pending = _inflight.get(key)
            if pending is None:
                pending = _inflight[key] = threading.Event()
                break
        pending.wait()
        # The owner may have failed or chosen not to cache; check again.
    try:
        return compute()
    finally:
        with _inflight_lock:
            del _inflight[key]
        pending.set()


def _source_key(path, mode):
    stat = path.stat()
    return ('source', str(path), mode, stat.st_mtime_ns, stat.st_size)


def source(path, mode=None, *, store=True):
    """Decoded artwork, converted like ``Image.open(path).convert(mode)``.

    Missing or unreadable files raise OSError, as Image.open does.
    """
    path = Path(path)
    key = _source_key(path, mode)

    def decode():
        with Image.open(path) as opened:
            image = opened.convert(mode) if mode else opened.copy()
        if store:
            _sources.put(key, image)
        else:
            setattr(image, KEY, key)
        return image
    return _single_flight(key, _sources, decode)


def _derive(image, operation, argument, store=True):
    parent = getattr(image, KEY, None)
    key = None if parent is None else (parent, operation, argument)
    # Without a parent key the input is not shared artwork and has no stable
    # identity to cache under.
    result = None if key is None else _derived.get(key)
    if result is None:
        result = OPERATIONS[operation](image, argument)
        if result is None:
            pass
        elif store and key is not None:
            _derived.put(key, result)
        elif key is not None:
            setattr(result, KEY, key)
    return result


def _trim(image, threshold):
    alpha = image.getchannel('A')
    if threshold:
        alpha = alpha.point(lambda value: 255 if value > threshold else 0)
    bounds = alpha.getbbox()
    return image.crop(bounds) if bounds else None


OPERATIONS = {
    'resize': lambda image, size: image.resize(size, Image.Resampling.LANCZOS),
    'contain': lambda image, size: ImageOps.contain(image, size, Image.Resampling.LANCZOS),
    'trim': _trim,
}


def resized(image, size):
    return _derive(image, 'resize', tuple(size))


def contained(image, size):
    return _derive(image, 'contain', tuple(size))


def trimmed(image, threshold=0):
    """Crop to the alpha bounds; pixels above ``threshold`` count as visible.

    Returns None when nothing is visible.
    """
    return _derive(image, 'trim', threshold)


def prepared(path, mode, *steps):
    """Apply ``(operation, argument)`` steps to a source, caching only the result.

    A cached result needs no decode, so many large sources (achievement art)
    can be shown repeatedly without holding all of them at full size.
    """
    path = Path(path)
    key = _source_key(path, mode)
    for operation, argument in steps:
        key = (key, operation, argument)

    def build():
        # Keep the full-size source out of the shared cache: a batch of
        # thumbnails would otherwise evict the paper textures dialogs reuse.
        image = source(path, mode, store=False)
        for index, (operation, argument) in enumerate(steps):
            image = _derive(image, operation, argument, store=index == len(steps) - 1)
            if image is None:
                return None
        return image
    return _single_flight(key, _derived, build)


_pool = None
_pool_lock = threading.Lock()


def _ignore_missing(function, *arguments):
    try:
        function(*arguments)
    except (OSError, ValueError):
        pass  # The drawing code reports or replaces missing artwork itself.


def warm(sources=(), prepared_items=()):
    """Decode artwork on worker threads; Pillow releases the GIL while decoding.

    ``sources`` holds ``(path, mode)`` and ``prepared_items`` holds
    ``(path, mode, *steps)``. Returns futures; failures are left for the
    drawing code, which already handles missing artwork.
    """
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='re4-ui-art')
        return ([_pool.submit(_ignore_missing, source, path, mode) for path, mode in sources] +
                [_pool.submit(_ignore_missing, prepared, *item) for item in prepared_items])


def shutdown():
    """Drop queued warm-up work so closing the launcher never waits for it."""
    global _pool
    with _pool_lock:
        pool, _pool = _pool, None
    if pool:
        pool.shutdown(wait=False, cancel_futures=True)


def clear():
    _sources.clear()
    _derived.clear()
