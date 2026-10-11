"""Fail closed on unpublished paths, symlinks, unapproved binaries and encoded dumps.

Inspect the index, every tree reachable through refs/reflogs, and every stored
blob (even dangling objects). A source review remains necessary for provenance.
"""
import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

TOP_LEVEL = {'.gitignore', 'LICENSE', 'Makefile', 'README.md', 'VALIDATION.md',
             'requirements.txt', 'setup.sh', 're4pc.sh', '.github/workflows/ci.yml',
             'docs/readme-banner.svg', 'docs/banner-artwork.md'}
# Only this reviewed, AI-generated documentation artwork may be binary.
# New versions require visual review and an explicit SHA-256 update.
DOCUMENTATION_IMAGES = {
    'docs/readme-banner.png':
        'c588302bbfd8dc9806bdf25832cacc86a51cc08b88c067437755b081b3dcadea',
}
SOURCE_FILES = {
    're4pc': ('__init__', '__main__', 'arm', 'assets', 'bionic', 'desktop', 'eabi', 'fast',
              'filesystem', 'game', 'graphics', 'input', 'jni', 'media',
              'paths', 'pc_controls', 'runtime_log', 'textures'),
    'tools': ('audit_source', 'build_native', 'disassemble', 'install_desktop', 'live_test',
              'migrate_local', 'probe_input', 'test_components',
              'test_pc_controls', 'test_visible'),
    'tests': ('test_arm', 'test_assets', 'test_audit_source', 'test_desktop', 'test_graphics',
              'test_input', 'test_key_routing', 'test_media', 'test_migration',
              'test_paths', 'test_pc_controls', 'test_runtime_log', 'test_textures'),
}
PUBLISH_FILES = TOP_LEVEL | set(DOCUMENTATION_IMAGES) | {'native/audio.c', 'native/fast.c'} | {
    f'{folder}/{name}.py' for folder, names in SOURCE_FILES.items() for name in names}
MAX_SOURCE_BYTES = 256 * 1024
MAX_DOCUMENTATION_IMAGE_BYTES = 4 * 1024 * 1024


class AuditError(ValueError):
    pass


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


def check_entry(path, mode, kind='blob'):
    if path not in PUBLISH_FILES:
        raise AuditError(f'Forbidden publication path: {path}')
    if mode not in ('100644', '100755') or kind != 'blob':
        raise AuditError(f'Forbidden file mode/type (symlink or submodule): {path} {mode} {kind}')


def check_blob(data, identifier, path=None):
    if len(data) > MAX_DOCUMENTATION_IMAGE_BYTES:
        raise AuditError(f'Oversized source blob: {identifier}')
    digest = hashlib.sha256(data).hexdigest()
    if path in DOCUMENTATION_IMAGES and digest != DOCUMENTATION_IMAGES[path]:
        raise AuditError(f'Unreviewed documentation image: {path}')
    if digest in DOCUMENTATION_IMAGES.values():
        if path is not None and DOCUMENTATION_IMAGES.get(path) != digest:
            raise AuditError(f'Documentation image at wrong path: {path}')
        return
    if len(data) > MAX_SOURCE_BYTES:
        raise AuditError(f'Oversized source blob: {identifier}')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as error:
        raise AuditError(f'Binary/non-UTF-8 blob: {identifier}') from error
    if any(ord(c) < 32 and c not in '\t\n\r' for c in text) or '\x7f' in text:
        raise AuditError(f'Binary/control bytes in blob: {identifier}')
    # Reject long hex/base64 payloads, byte escape dumps and disassembler output.
    # Short hashes, hand-written ABI trampolines and synthetic fixtures are valid.
    if (re.search(r'[0-9a-fA-F]{128,}', text)
            or re.search(r'[A-Za-z0-9+/]{256,}={0,2}', text)
            or re.search(r'(?:\\x[0-9a-fA-F]{2}){32,}', text)
            or re.search(r'^\s*[0-9a-fA-F]{6,16}:\s+(?:[0-9a-fA-F]{2,8}\s+){2,}', text, re.M)):
        raise AuditError(f'Encoded payload or disassembly dump: {identifier}')


def audit(root):
    checked_entries = set()

    def check_content(path, blob):
        if (path, blob) not in checked_entries:
            check_blob(git(root, 'cat-file', 'blob', blob), blob, path)
            checked_entries.add((path, blob))

    entries = git(root, 'ls-files', '--stage', '-z').split(b'\0')
    if not any(entries):
        raise AuditError('No staged/tracked source files to audit')
    indexed = 0
    for entry in filter(None, entries):
        metadata, path = entry.split(b'\t', 1)
        mode, blob, stage = metadata.decode().split()
        if stage != '0':
            raise AuditError('Unmerged index entry')
        check_entry(path.decode('utf-8'), mode)
        check_content(path.decode('utf-8'), blob)
        indexed += 1
    commits = git(root, 'rev-list', '--all', '--reflog').decode().splitlines()
    for commit in commits:
        for entry in filter(None, git(root, 'ls-tree', '-r', '-z', commit).split(b'\0')):
            metadata, path = entry.split(b'\t', 1)
            mode, kind, blob = metadata.decode().split()
            check_entry(path.decode('utf-8'), mode, kind)
            check_content(path.decode('utf-8'), blob)
    objects = git(root, 'cat-file', '--batch-all-objects',
                  '--batch-check=%(objectname) %(objecttype) %(objectsize)').decode().splitlines()
    blobs = 0
    for obj in objects:
        identifier, kind, size = obj.split()
        if kind != 'blob':
            continue
        if int(size) > MAX_DOCUMENTATION_IMAGE_BYTES:
            raise AuditError(f'Oversized source blob: {identifier}')
        check_blob(git(root, 'cat-file', 'blob', identifier), identifier)
        blobs += 1
    print(f'SOURCE_AUDIT_PASS: {indexed} index files, {len(commits)} commits, {blobs} blobs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    try:
        audit(args.repo)
    except (AuditError, UnicodeDecodeError, subprocess.CalledProcessError) as error:
        print(f'SOURCE_AUDIT_FAILED: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
