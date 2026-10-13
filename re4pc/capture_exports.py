"""Streaming gallery ZIPs and versioned, checksummed save/media bundles.

Callers hold the stopped-installation SaveStore lock. Media is published before
an imported snapshot; Restore is the only operation that activates that snapshot.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile

from .achievements import ACHIEVEMENTS, AchievementStore, FILENAME, IDS, MAX_RECORD_BYTES
from .backups import MAX_BYTES, _canonical, _digest, _safe_name, _sync

MAX_MEDIA_BYTES = 1024 * 1024 * 1024
MAX_MEDIA_FILES = 4096
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
BUNDLE_FORMAT = 're4mepc-save-media'


def _media_name(name):
    _safe_name(name)
    if (Path(name).name != name or len(name) > 120 or not name.startswith('unlock-')
            or not name.endswith(('.png', '.mp4'))
            or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-.' for c in name)):
        raise ValueError('Invalid achievement media filename')
    return name


def _media_directory(root):
    directory = Path(root).resolve() / 'achievement-media'
    if directory.is_symlink():
        raise ValueError('Achievement media directory cannot be a symbolic link')
    if directory.exists() and not directory.is_dir():
        raise ValueError('Achievement media directory must be a directory')
    return directory


def _record(raw):
    if raw is None:
        return {}, {}, None
    progress, unlocked, media = AchievementStore.decode(raw)
    return unlocked, media, progress


def _snapshot_record(files):
    path = files.get(FILENAME)
    if path is None:
        return _record(None)
    if path.stat().st_size > MAX_RECORD_BYTES:
        raise ValueError('Achievement record is too large')
    return _record(path.read_bytes())


def _hash_file(path):
    # Refuse symlinks, FIFOs and devices before opening a payload.
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('Capture must be a regular file: ' + path.name)
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while chunk := stream.read(CHUNK_BYTES):
            size += len(chunk)
            if size > MAX_MEDIA_BYTES:
                raise ValueError('Capture exceeds media size limit')
            digest.update(chunk)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def _collect(root, media, *, strict):
    directory = _media_directory(root)
    records, paths, missing = {}, {}, []
    total = 0
    for identifier, captures in sorted(media.items()):
        for kind, name in sorted(captures.items()):
            _media_name(name)
            if name in records:
                continue
            path = directory / name
            if not path.exists() and not path.is_symlink():
                missing.append({'achievement': identifier, 'kind': kind, 'filename': name})
                continue
            record = _hash_file(path)
            total += record['bytes']
            if total > MAX_MEDIA_BYTES or len(records) >= MAX_MEDIA_FILES:
                raise ValueError('Achievement media exceeds export limits')
            records[name], paths[name] = record, path
    if strict and missing:
        raise ValueError('Referenced achievement media is missing: ' + ', '.join(sorted({m['filename'] for m in missing})))
    return records, paths, missing


@contextmanager
def _new_archive(destination):
    destination = Path(destination).absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.capture-export-', dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED,
                             allowZip64=True) as archive:
            yield archive
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        os.link(temporary, destination)  # Never overwrite an existing export.
        _sync(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _write_payload(archive, member, path, expected):
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as source, archive.open(member, 'w', force_zip64=True) as target:
        while chunk := source.read(CHUNK_BYTES):
            size += len(chunk)
            if size > expected['bytes']:
                raise ValueError('Capture changed during export: ' + path.name)
            digest.update(chunk)
            target.write(chunk)
    if size != expected['bytes'] or digest.hexdigest() != expected['sha256']:
        raise ValueError('Capture changed during export: ' + path.name)


def export_achievements(store, destination, identifiers=()):
    store._require(stopped=True)
    selected = set(identifiers) if identifiers else set(IDS)
    if not selected <= IDS:
        raise ValueError('Unknown achievement ID: ' + ', '.join(sorted(selected - IDS)))
    record = AchievementStore(store.root)
    progress, unlocked = record.load()
    media = {key: value for key, value in record.media.items() if key in selected}
    records, paths, missing = _collect(store.root, media, strict=False)
    metadata = {'format': 're4mepc-achievement-captures', 'version': 1,
                'achievements': [{'id': item.id, 'title': item.title,
                                  'unlocked_ns': unlocked.get(item.id),
                                  'media': {kind: 'media/' + name for kind, name in media.get(item.id, {}).items()}}
                                 for item in ACHIEVEMENTS if item.id in selected],
                'files': {'media/' + name: value for name, value in records.items()},
                'missing_captures': missing}
    with _new_archive(destination) as archive:
        archive.writestr('achievements.json', _canonical(metadata))
        for name, path in paths.items():
            _write_payload(archive, 'media/' + name, path, records[name])
    return {'destination': str(Path(destination).absolute()), 'files': len(paths),
            'missing_captures': missing}


def export_bundle(store, identity, destination):
    store._require(stopped=True)
    _, files = store._validate(store._path(identity), paths=True)
    _, media, _ = _snapshot_record(files)
    records, paths, _ = _collect(store.root, media, strict=True)
    with tempfile.TemporaryDirectory(prefix='.bundle-', dir=store.directory) as temporary:
        save = Path(temporary) / 'save.zip'
        store.export(identity, save)
        manifest = {'format': BUNDLE_FORMAT, 'version': 1, 'snapshot_id': identity,
                    'files': {'save.zip': _hash_file(save),
                              **{'media/' + name: value for name, value in records.items()}}}
        manifest['checksum'] = _digest(_canonical(manifest))
        with _new_archive(destination) as archive:
            archive.writestr('bundle.json', _canonical(manifest))
            _write_payload(archive, 'save.zip', save, manifest['files']['save.zip'])
            for name, path in paths.items():
                _write_payload(archive, 'media/' + name, path, records[name])
    return Path(destination).absolute()


def _bundle_manifest(source):
    infos = source.infolist()
    names = [info.filename for info in infos]
    if len(infos) > MAX_MEDIA_FILES + 2 or len(names) != len(set(names)):
        raise ValueError('Invalid bundle archive members')
    for info in infos:
        _safe_name(info.filename)
        mode = stat.S_IFMT(info.external_attr >> 16)
        if info.is_dir() or mode not in (0, stat.S_IFREG):
            raise ValueError('Bundle members must be regular files')
        if info.filename not in ('bundle.json', 'save.zip'):
            if not info.filename.startswith('media/'):
                raise ValueError('Unexpected bundle archive member')
            _media_name(info.filename[6:])
    info = source.getinfo('bundle.json')
    if info.file_size > MAX_MANIFEST_BYTES:
        raise ValueError('Bundle manifest exceeds size limit')
    manifest = json.loads(source.read(info))
    if (not isinstance(manifest, dict) or manifest.get('format') != BUNDLE_FORMAT
            or type(manifest.get('version')) is not int or manifest['version'] != 1):
        raise ValueError('Unsupported media bundle format')
    checksum = manifest.pop('checksum', None)
    if checksum != _digest(_canonical(manifest)):
        raise ValueError('Bundle manifest checksum mismatch')
    records = manifest['files']
    if not isinstance(records, dict) or set(records) != set(names) - {'bundle.json'} or 'save.zip' not in records:
        raise ValueError('Bundle payload inventory mismatch')
    media_total = 0
    for name, record in records.items():
        if (not isinstance(record, dict) or set(record) != {'bytes', 'sha256'}
                or type(record['bytes']) is not int or record['bytes'] < 0
                or not isinstance(record['sha256'], str) or len(record['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in record['sha256'])):
            raise ValueError('Invalid bundle payload record')
        size = record['bytes']
        if size != source.getinfo(name).file_size:
            raise ValueError('Bundle payload size mismatch')
        if name == 'save.zip':
            # Deflate can slightly grow an incompressible save set; include
            # bounded ZIP/member overhead in addition to the save/manifest cap.
            if size > MAX_BYTES + 4 * MAX_MANIFEST_BYTES:
                raise ValueError('Nested save archive exceeds size limit')
        else:
            media_total += size
    if media_total > MAX_MEDIA_BYTES:
        raise ValueError('Bundle media exceeds size limit')
    return manifest


def _extract_payload(source, name, target, record):
    digest, size = hashlib.sha256(), 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open(name) as src, target.open('xb') as dst:
        while chunk := src.read(CHUNK_BYTES):
            size += len(chunk)
            if size > record['bytes']:
                raise ValueError('Bundle payload exceeds declared size')
            digest.update(chunk)
            dst.write(chunk)
        dst.flush()
        os.fsync(dst.fileno())
    if size != record['bytes'] or digest.hexdigest() != record['sha256']:
        raise ValueError('Bundle payload checksum mismatch: ' + name)


def import_bundle(store, archive):
    store._require(stopped=True)
    try:
        with tempfile.TemporaryDirectory(prefix='.bundle-import-', dir=store.directory) as temporary:
            work = Path(temporary)
            with zipfile.ZipFile(archive) as source:
                manifest = _bundle_manifest(source)
                store._path(manifest['snapshot_id'])
                for name, record in manifest['files'].items():
                    _extract_payload(source, name, work / name, record)
            saves = work / 'saves'
            saves.mkdir()
            snapshot, files = store._read_archive(work / 'save.zip', saves)
            if snapshot['id'] != manifest['snapshot_id']:
                raise ValueError('Bundle snapshot identity mismatch')
            raw = files.get(FILENAME)
            _, media, _ = _record(raw)
            referenced = {'media/' + name for captures in media.values() for name in captures.values()}
            if referenced != set(manifest['files']) - {'save.zip'}:
                raise ValueError('Bundle media does not match snapshot references')
            destination = _media_directory(store.root)
            # Check every conflict before publishing even the first media file.
            for name in sorted(referenced):
                path = destination / name[6:]
                if path.exists() or path.is_symlink():
                    if _hash_file(path) != manifest['files'][name]:
                        raise ValueError('Conflicting achievement media: ' + path.name)
            if referenced:
                destination.mkdir(parents=True, exist_ok=True, mode=0o700)
            for name in sorted(referenced):
                path = destination / name[6:]
                if path.exists():
                    continue
                fd, temporary_media = tempfile.mkstemp(prefix='.media-import-', dir=destination)
                try:
                    with os.fdopen(fd, 'wb') as dst, (work / name).open('rb') as src:
                        shutil.copyfileobj(src, dst, CHUNK_BYTES)
                        dst.flush()
                        os.fsync(dst.fileno())
                    try:
                        os.link(temporary_media, path)
                    except FileExistsError:
                        if _hash_file(path) != manifest['files'][name]:
                            raise ValueError('Conflicting achievement media: ' + path.name)
                finally:
                    Path(temporary_media).unlink(missing_ok=True)
            if referenced:
                _sync(destination)
            # Failure/interruption may leave reusable, validated media, but no
            # active saves change. A subsequent import safely reuses the media.
            return store._publish(files, 'imported')
    except (zipfile.BadZipFile, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid save/media bundle') from error
