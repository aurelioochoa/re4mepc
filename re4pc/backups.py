"""Coherent, checksummed save sets and an installation-wide process lock.

The native save entry point brackets all writes with before_write/after_write.
Snapshots contain the entire saves directory, never imported resources or caches.
"""
import ctypes
import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from .paths import xdg_home

MAX_BYTES = 256 * 1024 * 1024
MAX_FILES = 4096


class GameRunningError(RuntimeError):
    pass


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def _sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _exchange(source, destination):
    """Swap complete directory names atomically (Linux RENAME_EXCHANGE)."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 2):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def _safe_name(value):
    if not isinstance(value, str) or '\\' in value or '\0' in value:
        raise ValueError('Unsafe save filename')
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or any(p in ('.', '..') for p in path.parts) or str(path) != value:
        raise ValueError('Unsafe save filename')
    return path


class SaveStore:
    def __init__(self, root, state_dir=None):
        self.root = Path(root).resolve()
        self.saves = self.root / 'saves'
        key = _digest(os.fsencode(str(self.root)))
        base = Path(state_dir) if state_dir is not None else xdg_home('XDG_STATE_HOME', '.local/state') / 're4mepc/backups'
        self.directory = base / key
        self.snapshots = self.directory / 'snapshots'
        self._lock = None
        self.running = False
        self._writing = False

    def acquire(self, running=False):
        if self._lock is not None:
            raise RuntimeError('Save lock already held')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = (self.directory / 'game.lock').open('a+b')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            lock.close()
            raise GameRunningError('Game or another save operation is running for this installation') from error
        self._lock = lock
        self.running = bool(running)
        self.snapshots.mkdir(exist_ok=True, mode=0o700)
        return self

    def close(self):
        if self._lock is not None:
            fcntl.flock(self._lock, fcntl.LOCK_UN)
            self._lock.close()
            self._lock = None
        self.running = self._writing = False

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *args):
        self.close()

    def _require(self, stopped=False):
        if self._lock is None:
            raise RuntimeError('Acquire the save lock before accessing backups')
        if stopped and self.running:
            raise GameRunningError('Stop the game before exporting or restoring saves')

    def _read_saves(self):
        if self.saves.is_symlink():
            raise ValueError('The saves directory must not be a symbolic link')
        files = {}
        total = 0
        if not self.saves.exists():
            return files
        for folder, directories, names in os.walk(self.saves, followlinks=False):
            for name in directories:
                if (Path(folder) / name).is_symlink():
                    raise ValueError('Save sets cannot contain symbolic links')
            for name in sorted(names):
                path = Path(folder) / name
                if path.is_symlink() or not path.is_file():
                    raise ValueError('Save sets must contain regular files')
                relative = path.relative_to(self.saves).as_posix()
                _safe_name(relative)
                total += path.stat().st_size
                if total > MAX_BYTES or len(files) >= MAX_FILES:
                    raise ValueError('Save set exceeds backup limits')
                files[relative] = path.read_bytes()
        return files

    def _publish(self, files, label):
        records = {name: {'bytes': len(data), 'sha256': _digest(data)} for name, data in sorted(files.items())}
        identity = _digest(_canonical(records))
        destination = self.snapshots / identity
        if destination.exists():
            manifest, _ = self._validate(destination)
            manifest.update(created_ns=time.time_ns(), label=str(label))
            fd, temporary = tempfile.mkstemp(prefix='.manifest-', dir=destination)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(_canonical(manifest) + b'\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, destination / 'manifest.json')
                _sync(destination)
            finally:
                Path(temporary).unlink(missing_ok=True)
            return manifest
        manifest = {'version': 1, 'id': identity, 'created_ns': time.time_ns(), 'label': str(label), 'files': records}
        work = Path(tempfile.mkdtemp(prefix='.snapshot-', dir=self.snapshots))
        try:
            for name, data in files.items():
                target = work / 'files' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            with (work / 'manifest.json').open('xb') as stream:
                stream.write(_canonical(manifest) + b'\n')
                stream.flush()
                os.fsync(stream.fileno())
            for folder, _, _ in os.walk(work, topdown=False):
                _sync(folder)
            os.rename(work, destination)
            _sync(self.snapshots)
        finally:
            if work.exists():
                shutil.rmtree(work)
        self._prune()
        return manifest

    def snapshot(self, label='manual'):
        self._require()
        if self._writing:
            raise RuntimeError('Cannot snapshot an incomplete native save')
        return self._publish(self._read_saves(), label)

    def before_write(self):
        self._require()
        if self._writing:
            raise RuntimeError('Native save already in progress')
        snapshot = self.snapshot('before-save')
        self._writing = True
        return snapshot

    def after_write(self, success):
        self._require()
        if not self._writing:
            raise RuntimeError('Native save was not started')
        self._writing = False
        return self.snapshot('saved') if success else None

    def _path(self, identity):
        if not isinstance(identity, str) or len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
            raise ValueError('Invalid snapshot ID')
        return self.snapshots / identity

    def _validate(self, path):
        if path.is_symlink() or not path.is_dir():
            raise ValueError('Snapshot missing or unsafe')
        manifest_path = path / 'manifest.json'
        if manifest_path.is_symlink() or manifest_path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('Invalid snapshot manifest')
        try:
            manifest = json.loads(manifest_path.read_text())
            records = manifest['files']
            if manifest['version'] != 1 or not isinstance(records, dict) or len(records) > MAX_FILES:
                raise ValueError('Invalid snapshot manifest')
            identity = _digest(_canonical(records))
            if manifest['id'] != identity or path.name != identity:
                raise ValueError('Snapshot manifest checksum mismatch')
            if not isinstance(manifest['created_ns'], int) or not isinstance(manifest['label'], str):
                raise ValueError('Invalid snapshot metadata')
            files = {}
            total = 0
            for name, record in records.items():
                _safe_name(name)
                target = path / 'files' / name
                if any(parent.is_symlink() for parent in (target, *target.parents)) or not target.is_file():
                    raise ValueError('Unsafe or missing snapshot file')
                total += target.stat().st_size
                if total > MAX_BYTES:
                    raise ValueError('Snapshot exceeds size limit')
                data = target.read_bytes()
                if len(data) != record['bytes'] or _digest(data) != record['sha256']:
                    raise ValueError('Snapshot file checksum mismatch: ' + name)
                files[name] = data
            # Reject unlisted payloads so exported/restored sets remain complete.
            actual = {p.relative_to(path / 'files').as_posix() for p in (path / 'files').rglob('*') if not p.is_dir()}
            if actual != set(records):
                raise ValueError('Snapshot contains unlisted files')
            return manifest, files
        except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError('Invalid snapshot manifest') from error

    def list_snapshots(self):
        self._require()
        result = []
        for path in self.snapshots.iterdir():
            if path.name.startswith('.'):
                continue
            # Corruption is surfaced, never silently presented as restorable.
            manifest, _ = self._validate(path)
            result.append(manifest)
        return sorted(result, key=lambda item: item['created_ns'], reverse=True)

    def _prune(self):
        for manifest in self.list_snapshots()[10:]:
            shutil.rmtree(self._path(manifest['id']))
        _sync(self.snapshots)

    def export(self, identity, destination):
        self._require(stopped=True)
        manifest, files = self._validate(self._path(identity))
        destination = Path(destination).absolute()
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.backup-', dir=destination.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('manifest.json', _canonical(manifest))
                for name, data in files.items():
                    archive.writestr('files/' + name, data)
            with open(temporary, 'rb') as stream:
                os.fsync(stream.fileno())
            # Refuse to overwrite another backup or an unrelated file.
            os.link(temporary, destination)
            _sync(destination.parent)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return destination

    def delete(self, identity):
        """Remove one validated snapshot under the stopped-installation lock."""
        self._require(stopped=True)
        path = self._path(identity)
        self._validate(path)
        shutil.rmtree(path)
        _sync(self.snapshots)
        return {'deleted': identity}

    def import_backup(self, archive):
        self._require(stopped=True)
        work = Path(tempfile.mkdtemp(prefix='.import-', dir=self.snapshots))
        try:
            with zipfile.ZipFile(archive) as source:
                infos = source.infolist()
                if len(infos) > MAX_FILES + 1 or len({i.filename for i in infos}) != len(infos):
                    raise ValueError('Invalid backup archive members')
                total = 0
                for info in infos:
                    _safe_name(info.filename)
                    if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16) or (info.filename != 'manifest.json' and not info.filename.startswith('files/')):
                        raise ValueError('Unexpected backup archive member')
                    total += info.file_size
                    if total > MAX_BYTES + 2 * 1024 * 1024:
                        raise ValueError('Backup archive exceeds size limit')
                    target = work / info.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(info) as src, target.open('xb') as dst:
                        shutil.copyfileobj(src, dst)
            manifest = json.loads((work / 'manifest.json').read_text())
            self._path(manifest['id'])
            named = work.parent / ('.import-' + uuid.uuid4().hex)
            named.mkdir()
            child = named / manifest['id']
            os.rename(work, child)
            work = named
            validated, files = self._validate(child)
            return self._publish(files, 'imported')
        except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError('Invalid backup archive') from error
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def restore(self, identity):
        self._require(stopped=True)
        manifest, files = self._validate(self._path(identity))
        # Preserve a complete independent recovery snapshot before replacement.
        recovery = self.snapshot('before-restore')
        self.root.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.save-recovery-', dir=self.root))
        swapped = published = False
        try:
            for name, data in files.items():
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            for folder, _, _ in os.walk(stage, topdown=False):
                _sync(folder)
            if self.saves.exists():
                # A crash at any point leaves a complete active set. After this
                # atomic swap, stage holds the original independent recovery.
                _exchange(stage, self.saves)
                swapped = True
            else:
                os.rename(stage, self.saves)
                published = True
            try:
                _sync(self.root)
            except BaseException:
                if swapped:
                    try:
                        _exchange(stage, self.saves)
                    except OSError as error:
                        raise RuntimeError('Restore rollback failed; original saves preserved at ' + str(stage) + '; recovery snapshot ' + recovery['id']) from error
                    swapped = False
                elif published:
                    os.rename(self.saves, stage)
                    published = False
                _sync(self.root)
                raise
            return {'restored': manifest['id'], 'recovery': recovery['id'],
                    'recovery_directory': str(stage) if swapped else None}
        finally:
            if stage.exists() and not swapped:
                shutil.rmtree(stage)
