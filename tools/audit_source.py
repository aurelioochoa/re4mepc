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

TOP_LEVEL = {'.gitignore', 'LICENSE', 'Makefile', 'README.md', 'README.es.md', 'VALIDATION.md',
             'requirements.txt', 'setup.sh', 're4pc.sh', '.github/workflows/ci.yml',
             'docs/readme-banner.svg', 'docs/banner-artwork.md', 'docs/launcher-assets.md', 'docs/advanced-usage.md',
             'docs/render-audit.md', 'docs/diagnostics.md', 'docs/desktop-release.md', 'docs/achievements.md',
             'docs/qualification-summary.md', 'docs/dialogs.md', 'docs/roadmap-results.md', 'docs/rea-workflow.md', 'docs/menu-controls.md', 'docs/portable-captures.md', 'docs/campaign-coverage.md'}
# Only reviewed artwork, host UI screenshots and explicitly requested gameplay
# documentation images may be binary.
# New versions require visual review and an explicit SHA-256 update.
DOCUMENTATION_IMAGES = {
    'docs/gameplay-mosaic.png':
        '639ba91c7c49750295bca08087b48a8a140774d58ec9ce9729210fc55976ef76',
    're4pc/ui_assets/resident-evil-wordmark.png': 'efb3652a76621b8f041a1f719f1bb5403bed5f058da1f0f8afdabd933026d288',
    're4pc/ui_assets/case-paper-v2.png': '0e96d69e5c8bdabf15a74abd8bb360b60acef265a1d1d86101a2970cddd3bae8',
    're4pc/ui_assets/paperclip.png': '5076fca75ba3a674481bc545431004087f17c8aa51059c83fab61ef8bdc57868',
    're4pc/ui_assets/ribbon-spools.png': 'fd86662d6a90b2f56f9f4092b9356e5e07ec7c6555505ba1e38b184b7710a6ad',
    're4pc/ui_assets/case-seal.png': '035c8f83de91569ea21f1a4a8aaeacbbffd5eda49bc23f858b4d6fb347287e6e',
    'docs/backups-minimum-preview.png': '5a3cb269fd70b794bde4c9ba41c07d105e8e7df6208d5b84d8e72ebc6ebbe2a4',
    'docs/backups-preview.png': '6e3a063f481f4c5a22ad3be2c4fb30191ac57e50f3ef3eeee34f2f14a1ea919c',
    'docs/readme-banner.png':
        'c588302bbfd8dc9806bdf25832cacc86a51cc08b88c067437755b081b3dcadea',
    'docs/launcher-preview.png':
        'fb960f1caa8cf2cece4b0427bdef16cd837211e2488aafa0274e77b77c087077',
    're4pc/ui_assets/forest.png':
        'cd2e3e68510f524fdbe4e5cc8568a8d2390cfdab6280cb5ff661fed4122523ef',
    're4pc/ui_assets/icon.png':
        'b87ab5f37498c63eef1a95cb6c925b3e62a62131959ebc149373b75b1f8c0f75',
    're4pc/ui_assets/settings.png':
        '1b4f751e146d6df20eb309bf60fff3e093a98b9d83bb95f0de23611504048bf7',
    're4pc/ui_assets/backups.png':
        '871385cba9545cf62a3ede4bcd2504c81ca51be697702734e390ff31c45a453b',
    're4pc/ui_assets/case-file.png':
        '6e4b958b67444f0a0d1f9008d9a850b34f77f6dd6238f469429e1c25a0447ae5',
    're4pc/ui_assets/numeral-4.png':
        '6e8f54bed4105458bfafdee4c95fb270cffce4903fbc51e3b813b6750cd5926a',
    're4pc/ui_assets/achievement-all_s.png':
        '1ea1506be1f65c3d3cc81bdc83c3b88ffda6b829ea3d1f08a7e9852285e4cb57',
    're4pc/ui_assets/achievement-arsenal.png':
        '2283ec37c6b2de49b5b552bf6e227999ba9106a6e9446e608f51b78cf22fa9ac',
    're4pc/ui_assets/achievement-ashley.png':
        'ad489890ab327677b7e9f82eec233972f18938030c0bc7dd670e4d469d5c3523',
    're4pc/ui_assets/achievement-campaign.png':
        '57d2aefa1fc0a6de3fa7a1e003ae44a609f808fac77d778d353e5b453b092bdc',
    're4pc/ui_assets/achievement-collector.png':
        'e20c7f53dba90b424191c8bd0ba1686b5f7531c03e669b5530e685456fddf29e',
    're4pc/ui_assets/achievement-expert.png':
        'd747eda7b8839e07b24995399664169346fd92698bf759f6b5a34e41619bac30',
    're4pc/ui_assets/achievement-extreme.png':
        '276037f97cf9b10b5329aed63003882894676e3481434187534679a29c9b8758',
    're4pc/ui_assets/achievement-first_purchase.png':
        'ce980f7436945d4472bb2c318bd6b1b78eb4557805acc08a00f47a78e7458d13',
    're4pc/ui_assets/achievement-first_s.png':
        'fd8f6de66fd8016987cbf83a73bb31e6d21a82ef0eca3274e919ba6605a76172',
    're4pc/ui_assets/achievement-first_upgrade.png':
        '4f882b3cf1f213e664e3ab54c0fc66115b6f14eafbf08bfd17ac5574c81bc82a',
    're4pc/ui_assets/achievement-gigante.png':
        '752248e8e46f1952e6f168124ce2adc213ca35e4a65aa0c4b9e659c537691ef0',
    're4pc/ui_assets/achievement-krauser.png':
        'f9887fc66d0574bfaeb617c183ee99f7d50b9dc0f625285502d6080f54ced886',
    're4pc/ui_assets/achievement-mercenary.png':
        'a3e70eb15137dcc1cca6dd105f63721cdff00473e3ebeb71bd3e21850173aad6',
    're4pc/ui_assets/achievement-mercenary_master.png':
        'da4382f01490d0484f1d8cc3ad88c4b2ab85553004721f1e86482484418b6cb7',
    're4pc/ui_assets/achievement-platinum.png':
        '5b8f3e56cdf8ca3885c22c950176c93f7cba852fc80f500257330e76a3ee3001',
    're4pc/ui_assets/achievement-saddler.png':
        '5d57357a1653f6083e00ba3d2e7b7bd93b0f8d3074fa0b99c0c380f6c95fdc57',
    're4pc/ui_assets/achievement-salazar.png':
        'fd244f2f5bade05f4d44dfea6b17cb6a15f0efb6ff403969e055f2ca5cf089ea',
    're4pc/ui_assets/achievement-strongest.png':
        '3b9ddf4201426efbab0fefca11ebc5c983c7275631beb97592dbac6c897da9c4',
    're4pc/ui_assets/achievement-tuned.png':
        'b5c044c492fc1496188f6258572fc579bdc10c9d289d457ec04d556151415a32',
    're4pc/ui_assets/achievement-verdugo.png':
        'f95a876f133e58cfa2fb01b04c3b99495e4bab2a5c13eb69df861ad889046eee',
    're4pc/ui_assets/achievement-village.png':
        '882a255c0f631014c02a36f7ae46b0786d4ef9df31370327e8d70abe3d1c16bd',
    're4pc/ui_assets/paper.png':
        '3733d76b13657efcbfdf961ce3c30693f81a63dd23013f6ddba100a7c884d8a6',
    'docs/settings-preview.png':
        '6ad75b9cbafd94b2f401065ed9621c9d7077b50cbae331f2b563896699b83363',
    'docs/settings-minimum-preview.png':
        '92f08871091b5128d621f00b0bb04bc2e9f2bdff25f372867f1cdbdc08ecc515',
    'docs/achievements-preview.png':
        '50e4ee202c1cfe314eb90028f8c8aa081419e9bc43aa1c55e7a51d24106d42e4',
    'docs/achievements-minimum-preview.png':
        '5f71a7660329891aa979bcb4d3a376083a5fe1659697e78f76568801586b8a00',
}
SOURCE_FILES = {
    're4pc': ('__init__', '__main__', 'arm', 'assets', 'bionic', 'desktop', 'eabi', 'fast',
              'filesystem', 'game', 'graphics', 'input', 'jni', 'laser', 'media',
              'paths', 'pc_controls', 'menu_controls', 'capture_exports', 'runtime_log', 'textures', 'timing',
              'actions', 'controllers', 'settings', 'languages', 'backups', 'save_boundary',
              'launcher', 'launcher_ui', 'case_dialog', 'packaging', 'diagnostics', 'texture_cache', 'achievements', 'achievement_media'),
    'tools': ('audit_source', 'build_native', 'disassemble', 'install_desktop', 'live_test',
              'migrate_local', 'probe_input', 'test_components',
              'test_pc_controls', 'test_combat', 'test_laser', 'test_visible', 'package', 'benchmark', 'compare_dispatch', 'audit_render', 'validate_package', 'preview_dialogs', 'rea_workflow', 'test_menu_controls', 'validate_session', 'probe_render'),
    'tests': ('test_arm', 'test_assets', 'test_audit_source', 'test_desktop', 'test_graphics',
              'test_input', 'test_key_routing', 'test_mouse_capture', 'test_laser', 'test_media', 'test_migration',
              'test_paths', 'test_pc_controls', 'test_runtime_log', 'test_textures', 'test_timing',
              'test_actions', 'test_controllers', 'test_settings', 'test_languages', 'test_backups',
              'test_save_boundary', 'test_launcher', 'test_packaging', 'test_diagnostics',
              'test_texture_cache', 'test_cli', 'test_setup_commands', 'test_benchmark', 'test_achievements', 'test_achievement_media', 'test_build_native', 'test_menu_controls', 'test_capture_exports', 'test_rea_workflow'),
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


def audit(root, worktree=False):
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
    working = 0
    if worktree:
        for raw in filter(None, git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0')):
            path = raw.decode('utf-8')
            target = root / path
            if target.is_symlink():
                raise AuditError(f'Working-tree symlink: {path}')
            if not target.exists():
                continue
            check_entry(path, '100755' if target.stat().st_mode & 0o111 else '100644')
            check_blob(target.read_bytes(), 'worktree:' + path, path)
            working += 1
    print(f'SOURCE_AUDIT_PASS: {indexed} index files, {len(commits)} commits, {blobs} blobs, {working} working files')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--worktree', action='store_true', help='Also audit current tracked and unignored new files')
    args = parser.parse_args()
    try:
        audit(args.repo, args.worktree)
    except (AuditError, UnicodeDecodeError, subprocess.CalledProcessError) as error:
        print(f'SOURCE_AUDIT_FAILED: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
