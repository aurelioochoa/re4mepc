import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from re4pc.achievements import AchievementStore, FILENAME, Progress
from re4pc.backups import GameRunningError, SaveStore, _canonical, _digest
from re4pc.capture_exports import export_achievements


class CaptureExportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'source game'
        self.root.mkdir()
        self.state = self.base / 'state'
        self.store = SaveStore(self.root, self.state).acquire()
        self.addCleanup(self.store.close)
        self.achievements = AchievementStore(self.root)
        self.achievements.update(Progress(story=(True,) * 22))
        self.media = self.root / 'achievement-media'
        self.media.mkdir()
        (self.media / 'unlock-shared.png').write_bytes(b'original image payload')
        (self.media / 'unlock-shared.mp4').write_bytes(b'original movie payload')
        self.achievements.attach_media(('village', 'gigante'),
            {'image': 'unlock-shared.png', 'clip': 'unlock-shared.mp4'})
        (self.root / 'saves/slot').write_bytes(b'saved game')
        self.snapshot = self.store.snapshot()

    def other(self):
        other = SaveStore(self.base / 'destination game', self.state).acquire()
        self.addCleanup(other.close)
        return other

    def bundle(self, filename='bundle.zip'):
        archive = self.base / filename
        self.store.export(self.snapshot['id'], archive, include_media=True)
        return archive

    def rewrite(self, archive, mutate):
        with zipfile.ZipFile(archive) as source:
            values = {i.filename: source.read(i) for i in source.infolist()}
        mutate(values)
        target = self.base / 'modified.zip'
        with zipfile.ZipFile(target, 'w') as out:
            for name, data in values.items():
                out.writestr(name, data)
        return target

    def test_gallery_selected_deduplicates_originals_and_reports_missing(self):
        result = export_achievements(self.store, self.base / 'gallery.zip', ['village', 'gigante', 'village'])
        self.assertEqual(result['files'], 2)
        with zipfile.ZipFile(result['destination']) as source:
            self.assertEqual(set(source.namelist()), {'achievements.json', 'media/unlock-shared.png', 'media/unlock-shared.mp4'})
            self.assertEqual(source.read('media/unlock-shared.png'), b'original image payload')
            self.assertEqual(source.read('media/unlock-shared.mp4'), b'original movie payload')
            metadata = json.loads(source.read('achievements.json'))
            self.assertEqual([a['id'] for a in metadata['achievements']], ['village', 'gigante'])
            self.assertTrue(all(a['unlocked_ns'] for a in metadata['achievements']))
            self.assertTrue(all(link in source.namelist() for a in metadata['achievements'] for link in a['media'].values()))
        (self.media / 'unlock-shared.mp4').unlink()
        result = export_achievements(self.store, self.base / 'missing-gallery.zip')
        self.assertEqual(result['files'], 1)
        self.assertEqual({item['achievement'] for item in result['missing_captures']}, {'village', 'gigante'})
        with self.assertRaisesRegex(ValueError, 'Unknown achievement'):
            export_achievements(self.store, self.base / 'unknown.zip', ['absent'])
        self.assertFalse((self.base / 'unknown.zip').exists())

    def test_bundle_roundtrip_and_reuse_keeps_activation_explicit(self):
        bundle = self.bundle()
        with zipfile.ZipFile(bundle) as archive:
            self.assertEqual(set(archive.namelist()), {'bundle.json', 'save.zip', 'media/unlock-shared.png', 'media/unlock-shared.mp4'})
        other = self.other()
        other.saves.mkdir(parents=True)
        (other.saves / 'slot').write_bytes(b'active destination save')
        imported = other.import_backup(bundle)
        self.assertEqual(imported['id'], self.snapshot['id'])
        self.assertEqual((other.saves / 'slot').read_bytes(), b'active destination save')
        path = other.root / 'achievement-media/unlock-shared.png'
        inode = path.stat().st_ino
        self.assertEqual(other.import_backup(bundle)['id'], imported['id'])
        self.assertEqual(path.stat().st_ino, inode)
        other.restore(imported['id'])
        self.assertEqual((other.saves / 'slot').read_bytes(), b'saved game')
        records = AchievementStore(other.root)
        records.load()
        self.assertEqual(records.media['village']['image'], path.name)
        self.assertEqual(path.read_bytes(), b'original image payload')

    def test_bundle_uses_selected_snapshot_references_and_save_only_stays_compatible(self):
        (self.media / 'unlock-later.png').write_bytes(b'later media')
        self.achievements.attach_media(('village',), {'image': 'unlock-later.png'})
        bundle = self.bundle()
        with zipfile.ZipFile(bundle) as source:
            self.assertNotIn('media/unlock-later.png', source.namelist())
            self.assertIn('media/unlock-shared.png', source.namelist())
        plain = self.base / 'plain.zip'
        self.store.export(self.snapshot['id'], plain)
        with zipfile.ZipFile(plain) as source:
            self.assertIn('manifest.json', source.namelist())
            self.assertNotIn('bundle.json', source.namelist())
        other = self.other()
        self.assertEqual(other.import_backup(plain)['id'], self.snapshot['id'])
        self.assertFalse((other.root / 'achievement-media').exists())

    def test_missing_media_conflicts_and_symlinks_are_refused_before_snapshot_publication(self):
        bundle = self.bundle()
        other = self.other()
        dest = other.root / 'achievement-media'
        dest.mkdir(parents=True)
        (dest / 'unlock-shared.png').write_bytes(b'conflicting image')
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            other.import_backup(bundle)
        self.assertEqual(other.list_snapshots(), [])
        self.assertFalse((dest / 'unlock-shared.mp4').exists())
        (dest / 'unlock-shared.png').unlink()
        (dest / 'unlock-shared.png').symlink_to(self.media / 'unlock-shared.png')
        with self.assertRaisesRegex(ValueError, 'regular'):
            other.import_backup(bundle)
        (self.media / 'unlock-shared.png').unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.store.export(self.snapshot['id'], self.base / 'missing.zip', include_media=True)
        self.assertFalse((self.base / 'missing.zip').exists())

    def test_archive_hash_inventory_traversal_size_and_versions_fail_closed(self):
        bundle = self.bundle()
        def change_manifest(values, callback):
            manifest = json.loads(values['bundle.json'])
            callback(manifest)
            manifest.pop('checksum', None)
            manifest['checksum'] = _digest(_canonical(manifest))
            values['bundle.json'] = _canonical(manifest)
        mutations = (
            lambda v: v.update({'media/unlock-shared.png': b'corrupted media contents'}),
            lambda v: v.update({'bundle.json': b'{}'}),
            lambda v: v.update({'../outside': b'unsafe'}),
            lambda v: v.update({'media/unlock-extra.png': b'unlisted'}),
            lambda v: change_manifest(v, lambda m: m.update(version=2)),
            lambda v: change_manifest(v, lambda m: m.update(snapshot_id='0'*64)),
            lambda v: change_manifest(v, lambda m: m['files']['media/unlock-shared.png'].update(bytes=10**12)),
            lambda v: change_manifest(v, lambda m: m['files']['media/unlock-shared.png'].update(sha256='0'*64)),
            lambda v: v.update({'save.zip': b'not a save archive'}),
        )
        other = self.other()
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                modified = self.rewrite(bundle, mutate)
                with self.assertRaises(ValueError):
                    other.import_backup(modified)
                self.assertEqual(other.list_snapshots(), [])
                self.assertFalse((other.root / 'achievement-media').exists())
        self.assertFalse((self.base / 'outside').exists())
        with zipfile.ZipFile(bundle, 'a') as source, warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            source.writestr('bundle.json', b'{}')
        with self.assertRaisesRegex(ValueError, 'members'):
            other.import_backup(bundle)

    def test_media_limits_and_unsafe_member_types(self):
        with patch('re4pc.capture_exports.MAX_MEDIA_BYTES', 25):
            with self.assertRaisesRegex(ValueError, 'limits'):
                self.bundle('oversized.zip')
        with patch('re4pc.capture_exports.MAX_MEDIA_FILES', 1):
            with self.assertRaisesRegex(ValueError, 'limits'):
                self.bundle('too-many.zip')
        bundle = self.bundle()
        other = self.other()
        with patch('re4pc.capture_exports.MAX_MEDIA_BYTES', 25):
            with self.assertRaisesRegex(ValueError, 'size limit'):
                other.import_backup(bundle)
        with zipfile.ZipFile(self.base / 'unsafe.zip', 'w') as archive:
            info = zipfile.ZipInfo('bundle.json')
            info.external_attr = 0o120777 << 16
            archive.writestr(info, b'{}')
        with self.assertRaisesRegex(ValueError, 'regular'):
            other.import_backup(self.base / 'unsafe.zip')

    def test_interrupted_exports_and_imports_publish_no_partial_snapshot(self):
        with patch('re4pc.capture_exports._write_payload', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.bundle('interrupted.zip')
        self.assertFalse((self.base / 'interrupted.zip').exists())
        self.assertFalse(list(self.base.glob('.capture-export-*')))
        bundle = self.bundle()
        other = self.other()
        with patch.object(other, '_publish', side_effect=OSError('publication interrupted')):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                other.import_backup(bundle)
        self.assertEqual(other.list_snapshots(), [])
        self.assertFalse(other.saves.exists())
        self.assertEqual((other.root / 'achievement-media/unlock-shared.png').read_bytes(), b'original image payload')
        self.assertFalse(list((other.root / 'achievement-media').glob('.media-import-*')))
        self.assertEqual(other.import_backup(bundle)['id'], self.snapshot['id'])
        with self.assertRaises(FileExistsError):
            self.bundle()

    def test_cli_gallery_bundle_import_and_legacy_roundtrip(self):
        self.store.close()
        env = dict(os.environ, XDG_STATE_HOME=str(self.state.parent / 'cli-state'))
        def cli(*args):
            result = subprocess.run([sys.executable, '-m', 're4pc', *map(str, args)],
                                    env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        snap = cli('backup', '--game', self.root)
        gallery = cli('export-achievements', self.base / 'cli-gallery.zip', '--game', self.root,
                      '--achievement', 'village', '--achievement', 'gigante')
        self.assertEqual(gallery['files'], 2)
        destination = self.base / 'cli-other'
        destination.mkdir()
        for include, name in ((True, 'cli-bundle.zip'), (False, 'cli-save.zip')):
            args = ['export-backup', snap['id'], self.base / name, '--game', self.root]
            if include:
                args.append('--include-media')
            cli(*args)
            imported = cli('import-backup', self.base / name, '--game', destination)
            cli('restore-backup', imported['id'], '--game', destination)
            self.assertEqual((destination / 'saves/slot').read_bytes(), b'saved game')

    def test_stopped_lock_is_required(self):
        self.store.close()
        self.store.acquire(running=True)
        for operation in (lambda: self.bundle(),
                          lambda: export_achievements(self.store, self.base / 'gallery.zip')):
            with self.assertRaises(GameRunningError):
                operation()
