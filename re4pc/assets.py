"""Import user-supplied APK data without running Android code."""
import hashlib
import json
import os
import shutil
import stat
import struct
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from .filesystem import rename_new

LIBRARIES = ('libbio4af.so', 'libmc_eruption_for_android_jni.so')
# Interoperability identifiers for the only engine layout supported by this host.
COMPATIBLE_LIBRARIES = {
    'libbio4af.so': '6f6e52ef26b096cda44fc08c3f541cdc3bf1056a88f13fc1c3e17201589a0423',
    'libmc_eruption_for_android_jni.so': '25109c3b799045312073243b644f6053726689d7baf05bcf09b7acd786cff4f6',
}
REQUIRED = ('Acv_GmParam.bin', 'Acv_Sound.bin', 'Acv_Tex.h2z', 'common.h2z',
            'Acv_3DBase.h2z', 'Acv_3DChar.h2z', 'eu_font_U16le.fnt',
            'jp_font_U16le.fnt', 'bio4.m4v', 'buki.m4v', 'ending.m4v', 'res4.m4v') + tuple(
                f'Acv_3DStg{i:02d}.h2z' for i in range(1, 23)) + ('Acv_3DStg19_1.h2z',)
MAX_FILE = 128 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def normalized_name(name):
    return name[:-4] if name.endswith('.png') else name


def validate_libraries(root):
    for name in LIBRARIES:
        path = Path(root) / 'lib' / name
        if not path.is_file():
            raise ValueError(f'Missing game library: {name}; import your APK with ./re4pc.sh import /path/to/game.apk')
        with path.open('rb') as stream:
            header = stream.read(52)
        if len(header) < 52 or header[:7] != b'\x7fELF\x01\x01\x01' or struct.unpack_from('<H', header, 18)[0] != 40:
            raise ValueError(f'{name} must be a little-endian ARM32 ELF library')
        digest = sha256_file(path)
        if digest != COMPATIBLE_LIBRARIES[name]:
            raise ValueError(f'Incompatible game library: {name}; SHA-256 {digest}; expected {COMPATIBLE_LIBRARIES[name]}')


def validate(root):
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f'Game data missing at {root}; import your APK with ./re4pc.sh import /path/to/game.apk')
    validate_libraries(root)
    for name in REQUIRED:
        path = root / 'data' / 'monhun' / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'Missing or empty game asset: {name}; import a complete APK into a new directory')
    return root


def manifest_target(entry):
    if not isinstance(entry, dict) or not isinstance(entry.get('assetName'), str) or not isinstance(entry.get('path'), str):
        raise ValueError('Invalid APK asset manifest entry')
    source, destination = entry['assetName'], entry['path']
    if not source or PurePosixPath(source).name != source or source in ('.', '..') or '\\' in source or '\0' in source:
        raise ValueError('Unsafe asset source in APK manifest')
    parts = PurePosixPath(destination).parts
    if '..' in parts or 'data' not in parts or '\\' in destination or '\0' in destination:
        raise ValueError('Unsafe asset destination in APK manifest')
    # The last /data/ follows Android/data/ and is the game's asset directory.
    index = max(i for i, part in enumerate(parts) if part == 'data')
    relative = PurePosixPath(*parts[index + 1:])
    if not relative.parts:
        raise ValueError('Unsafe empty asset destination')
    name = normalized_name(relative.name)
    if not name or name in ('.', '..'):
        raise ValueError('Unsafe normalized asset destination')
    return f'assets/{source}', str(PurePosixPath('data', *relative.parts[:-1], name))


def import_apk(apk, destination):
    apk, destination = Path(apk), Path(destination).absolute()
    if os.path.lexists(destination):
        raise ValueError(f'Destination already exists: {destination}; use a new directory')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.re4-import-', dir=destination.parent) as temporary:
        work = Path(temporary)
        try:
            with zipfile.ZipFile(apk) as archive:
                infos = archive.infolist()
                members = {info.filename: info for info in infos}
                if len(members) != len(infos):
                    raise ValueError('Duplicate APK archive member')
                records = {}
                total = 0

                def copy(member, target):
                    nonlocal total
                    if target in records:
                        raise ValueError(f'Duplicate asset destination: {target}')
                    if member not in members:
                        raise ValueError(f'Missing APK asset: {member}')
                    info = members[member]
                    if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
                        raise ValueError(f'Unsafe APK member: {member}')
                    total += info.file_size
                    if info.file_size > MAX_FILE or total > MAX_TOTAL:
                        raise ValueError(f'Asset too large: {member}')
                    path = work / target
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as src, path.open('xb') as dst:
                        shutil.copyfileobj(src, dst)
                    records[target] = {'source': member, 'bytes': path.stat().st_size,
                                       'sha256': sha256_file(path)}

                for name in LIBRARIES:
                    candidates = [f'lib/{abi}/{name}' for abi in ('armeabi', 'armeabi-v7a')]
                    member = next((n for n in candidates if n in members), None)
                    if member is None:
                        raise ValueError(f'Missing ARM32 game library in APK: {name}')
                    copy(member, f'lib/{name}')
                validate_libraries(work)
                if 'assets/bundle_file_list.json' in members:
                    info = members['assets/bundle_file_list.json']
                    if info.file_size > 4 * 1024 * 1024:
                        raise ValueError('APK manifest too large')
                    manifest = json.loads(archive.read(info))
                    if not isinstance(manifest, list):
                        raise ValueError('Invalid APK asset manifest: expected a list')
                    for entry in manifest:
                        copy(*manifest_target(entry))
                for member in members:
                    if not member.startswith('assets/') or member.endswith('/'):
                        continue
                    normalized = normalized_name(PurePosixPath(member).name)
                    if normalized in REQUIRED and f'data/monhun/{normalized}' not in records:
                        copy(member, f'data/monhun/{normalized}')
                validate(work)
                (work / 'saves').mkdir()
                (work / 'import.json').write_text(json.dumps({
                    'apk_sha256': sha256_file(apk), 'files': records}, indent=2) + '\n')
        except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError(f'Invalid or incomplete APK: {error}') from error
        try:
            rename_new(work, destination)
        except FileExistsError as error:
            raise ValueError(f'Destination already exists: {destination}; use a new directory') from error
    return destination
