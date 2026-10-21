"""Explicit release allowlist and auditable staged contents."""
import hashlib
import json
import os
import stat
from pathlib import Path

APPLICATION_MODULES = (
    '__init__.py', '__main__.py', 'achievement_media.py', 'achievements.py', 'actions.py', 'arm.py', 'assets.py', 'backups.py',
    'bionic.py', 'capture_exports.py', 'controllers.py', 'desktop.py', 'diagnostics.py', 'eabi.py',
    'fast.py', 'filesystem.py', 'game.py', 'graphics.py', 'input.py', 'jni.py',
    'launcher.py', 'launcher_ui.py', 'languages.py', 'case_dialog.py', 'media.py', 'menu_controls.py', 'native_unzip.py', 'packaging.py', 'paths.py', 'pc_controls.py',
    'runtime_log.py', 'save_boundary.py', 'settings.py', 'texture_cache.py',
    'textures.py', 'timing.py', 'ui_images.py')
NATIVE_INPUTS = ('audio.c', 'fast.c')
APPLICATION_ASSETS = ('forest.png', 'icon.png', 'settings.png', 'backups.png',
                     'case-file.png', 'numeral-4.png', 'resident-evil-wordmark.png', 'paper.png', 'case-paper-v2.png',
                     'case-seal.png', 'ribbon-spools.png', 'paperclip.png',
                     'achievement-village.png', 'achievement-gigante.png',
                     'achievement-ashley.png', 'achievement-verdugo.png',
                     'achievement-salazar.png', 'achievement-krauser.png',
                     'achievement-saddler.png', 'achievement-campaign.png',
                     'achievement-extreme.png', 'achievement-first_s.png',
                     'achievement-all_s.png', 'achievement-strongest.png',
                     'achievement-mercenary.png', 'achievement-mercenary_master.png',
                     'achievement-first_purchase.png', 'achievement-collector.png',
                     'achievement-arsenal.png', 'achievement-first_upgrade.png',
                     'achievement-tuned.png', 'achievement-expert.png',
                     'achievement-platinum.png')
FORBIDDEN_DIGESTS = {
    '6f6e52ef26b096cda44fc08c3f541cdc3bf1056a88f13fc1c3e17201589a0423',
    '25109c3b799045312073243b644f6053726689d7baf05bcf09b7acd786cff4f6'}

APPLICATION_FILES = ('LICENSE', 'requirements.txt')
FORBIDDEN_SUFFIXES = {'.apk', '.apks', '.aab', '.obb', '.h2z', '.fnt', '.sav', '.dat', '.m4v', '.mp4'}
FORBIDDEN_PARTS = {'game', 'saves', 'cache', '.git', '.venv', '.unlazy', '.aws', '.codex'}


def audit_stage(root):
    root = Path(root).resolve()
    records = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if set(relative.parts) & FORBIDDEN_PARTS or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            raise ValueError('Forbidden release content: ' + str(relative))
        if path.name in ('libbio4af.so', 'libmc_eruption_for_android_jni.so', 'import.json'):
            raise ValueError('Imported game content in release: ' + str(relative))
        if path.is_symlink():
            target = path.resolve()
            if target != root and root not in target.parents:
                raise ValueError('Package symlink escapes stage: ' + str(relative))
            records[relative.as_posix()] = {'link': os.readlink(path)}
            continue
        if path.is_dir():
            continue
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError('Nonregular release member: ' + str(relative))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in FORBIDDEN_DIGESTS:
            raise ValueError('Imported engine bytes in release: ' + str(relative))
        records[relative.as_posix()] = {'bytes': path.stat().st_size, 'sha256': digest}
    required = ('AppRun', 're4mepc.desktop', 'usr/bin/python3', 'usr/bin/ffmpeg',
                'usr/lib/re4mepc/re4pc/__main__.py', 'usr/lib/re4mepc/build/libre4audio.so',
                'usr/lib/re4mepc/build/libre4fast.so')
    for name in required:
        if name not in records:
            raise ValueError('Missing release runtime: ' + name)
    return records


def write_manifest(root):
    records = audit_stage(root)
    path = Path(root) / 'CONTENTS.json'
    records.pop('CONTENTS.json', None)
    path.write_text(json.dumps({'version': 1, 'files': records}, indent=2, sort_keys=True) + '\n')
    return records


def verify_manifest(root):
    root = Path(root)
    expected = json.loads((root / 'CONTENTS.json').read_text())
    actual = audit_stage(root)
    actual.pop('CONTENTS.json', None)
    if expected.get('version') != 1 or expected.get('files') != actual:
        raise ValueError('Release content manifest mismatch')
    return actual
