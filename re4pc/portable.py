"""File-system primitives with the same guarantees on Linux, macOS and Windows.

Linux and macOS keep atomic no-clobber renames and directory swaps
(renameat2 / renamex_np). Windows has no atomic directory exchange; there the
swap is three renames, which never deletes either set and leaves both names
recoverable if interrupted.
"""
import ctypes
import os
import sys
import time

WINDOWS = sys.platform == 'win32'
if WINDOWS:
    import msvcrt
else:
    import fcntl


def lock(stream, blocking=True):
    """Exclusive advisory lock on an open file; BlockingIOError when busy."""
    if not WINDOWS:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        return
    stream.seek(0)
    while True:
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError as error:
            if not blocking:
                raise BlockingIOError(*error.args) from error
            time.sleep(0.05)


def unlock(stream):
    if not WINDOWS:
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        return
    stream.seek(0)
    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def sync_directory(directory):
    """Persist directory entries; Windows commits them with the files."""
    if WINDOWS:
        return
    fd = os.open(directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _rename_flags(source, destination, linux_flag, darwin_flag):
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        rename = libc.renamex_np
        rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        failed = rename(os.fsencode(source), os.fsencode(destination), darwin_flag)
    else:
        rename = libc.renameat2
        rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        # AT_FDCWD for both paths.
        failed = rename(-100, os.fsencode(source), -100, os.fsencode(destination), linux_flag)
    if failed:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def rename_new(source, destination):
    """Rename without replacing anything, even an empty directory."""
    if WINDOWS:
        # MoveFileEx without MOVEFILE_REPLACE_EXISTING never replaces.
        os.rename(source, destination)
        return
    _rename_flags(source, destination, 1, 0x4)  # RENAME_NOREPLACE / RENAME_EXCL


def exchange(source, destination):
    """Swap two existing directory names."""
    if not WINDOWS:
        _rename_flags(source, destination, 2, 0x2)  # RENAME_EXCHANGE / RENAME_SWAP
        return
    parking = str(destination) + '.exchange'
    os.rename(destination, parking)
    try:
        os.rename(source, destination)
    except BaseException:
        os.rename(parking, destination)
        raise
    os.rename(parking, source)


def process_alive(pid):
    """Whether a process exists. Never signals it (os.kill(pid, 0) on Windows
    would terminate the process)."""
    if WINDOWS:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: it exists
        kernel.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
