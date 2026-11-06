"""Reserve the 256 MiB ARM32 guest RAM on Linux, Windows and macOS.

Guest pointers are 32-bit. Where the host can place the mapping below 4 GiB
(Linux MAP_32BIT, Windows VirtualAlloc at a low address) guest and host
addresses are identical. macOS reserves the whole low 4 GiB for __PAGEZERO, so
there the mapping lives anywhere and every host access adds a fixed offset:
``host = guest + delta``. Native helpers receive both bases and translate.
"""
import ctypes as C
import os
import sys

# Guest address used when the host mapping cannot sit below 4 GiB. Any 32-bit
# value works; this one leaves page zero unmapped for null-pointer faults.
TRANSLATED_GUEST_BASE = 0x10000000
LOW_CANDIDATES = tuple(range(0x10000000, 0xF0000000, 0x10000000))


def c_runtime():
    """The C runtime exporting strnlen/memcmp to ctypes on every host."""
    if sys.platform == 'win32':
        return C.CDLL('msvcrt')
    return C.CDLL(None)


class GuestMemory:
    """Owns one read/write host mapping and its guest base address."""

    def __init__(self, size):
        self.size = size
        self.host = 0
        self.base = 0
        self._release = None
        force = os.environ.get('RE4PC_TRANSLATED_MEMORY') == '1'
        if sys.platform == 'win32':
            self._windows(force)
        else:
            self._posix(force)
        if not self.host:
            raise RuntimeError('Cannot allocate ARM32 guest memory')
        if not (0 < self.base and self.base + size <= 0x100000000):
            self.close()
            raise RuntimeError('ARM32 guest memory is outside the 32-bit address space')

    @property
    def delta(self):
        return self.host - self.base

    @property
    def translated(self):
        return self.host != self.base

    def _posix(self, force):
        libc = C.CDLL(None, use_errno=True)
        mmap = libc.mmap
        mmap.argtypes = (C.c_void_p, C.c_size_t, C.c_int, C.c_int, C.c_int, C.c_long)
        mmap.restype = C.c_void_p
        munmap = libc.munmap
        munmap.argtypes = (C.c_void_p, C.c_size_t)
        failed = C.c_void_p(-1).value
        protection = 3  # PROT_READ | PROT_WRITE
        if sys.platform.startswith('linux'):
            private_anonymous = 0x22
            low = 0x40  # MAP_32BIT
        else:  # macOS and BSDs
            private_anonymous = 0x1002
            low = 0
        if low and not force:
            pointer = mmap(None, self.size, protection, private_anonymous | low, -1, 0)
            if pointer not in (None, failed) and pointer + self.size <= 0x100000000:
                self.host = self.base = pointer
                self._release = lambda: munmap(pointer, self.size)
                return
            if pointer not in (None, failed):
                munmap(pointer, self.size)
        pointer = mmap(None, self.size, protection, private_anonymous, -1, 0)
        if pointer in (None, failed):
            error = C.get_errno()
            raise OSError(error, os.strerror(error), 'guest memory')
        self.host, self.base = pointer, TRANSLATED_GUEST_BASE
        self._release = lambda: munmap(pointer, self.size)

    def _windows(self, force):
        kernel = C.WinDLL('kernel32', use_last_error=True)
        allocate = kernel.VirtualAlloc
        allocate.argtypes = (C.c_void_p, C.c_size_t, C.c_uint32, C.c_uint32)
        allocate.restype = C.c_void_p
        free = kernel.VirtualFree
        free.argtypes = (C.c_void_p, C.c_size_t, C.c_uint32)
        free.restype = C.c_int
        commit, read_write, release = 0x3000, 0x04, 0x8000  # MEM_COMMIT|MEM_RESERVE
        if not force:
            for address in LOW_CANDIDATES:
                if address + self.size > 0x100000000:
                    break
                pointer = allocate(address, self.size, commit, read_write)
                if pointer:
                    self.host = self.base = pointer
                    self._release = lambda: free(pointer, 0, release)
                    return
        pointer = allocate(None, self.size, commit, read_write)
        if not pointer:
            raise OSError(C.get_last_error(), 'VirtualAlloc failed for guest memory')
        self.host, self.base = pointer, TRANSLATED_GUEST_BASE
        self._release = lambda: free(pointer, 0, release)

    def close(self):
        release, self._release = self._release, None
        if release:
            release()
