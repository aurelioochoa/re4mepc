import json
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch
from re4pc.backups import SaveStore, GameRunningError


class BackupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'game with spaces'
        self.saves = self.root / 'saves'
        self.saves.mkdir(parents=True)
        self.state = self.base / 'state'
        self.store = SaveStore(self.root, self.state).acquire()
        self.addCleanup(self.store.close)

    def write(self, data):
        (self.saves / 'slot').write_bytes(data)

    def test_coherent_boundaries_success_failure_and_retention(self):
        (self.root / 'cache').mkdir()
        (self.root / 'cache/private').write_bytes(b'excluded')
        (self.saves / 'nested').mkdir()
        (self.saves / 'nested/config').write_bytes(b'complete set')
        self.write(b'before')
        before = self.store.before_write()
        self.write(b'partial')
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            self.store.snapshot()
        self.assertIsNone(self.store.after_write(False))
        self.assertEqual(len(self.store.list_snapshots()), 1)
        self.assertEqual(set(before['files']), {'slot', 'nested/config'})
        self.write(b'before')
        self.store.before_write()
        self.write(b'after')
        after = self.store.after_write(True)
        self.assertEqual(len(self.store.list_snapshots()), 2)
        self.assertNotEqual(before['id'], after['id'])
        for i in range(15):
            self.write(str(i).encode())
            self.store.snapshot()
        self.assertEqual(len(self.store.list_snapshots()), 10)
        self.write(b'5')
        reused = self.store.snapshot()
        self.assertEqual(self.store.list_snapshots()[0]['id'], reused['id'])
        self.write(b'new')
        self.store.snapshot()
        self.assertIn(reused['id'], [s['id'] for s in self.store.list_snapshots()])

    def test_export_import_restore_and_recovery(self):
        self.write(b'old')
        old = self.store.snapshot()
        archive = self.base / 'export with spaces.zip'
        self.store.export(old['id'], archive)
        self.write(b'new')
        (self.saves / 'extra').write_bytes(b'delete on restore')
        result = self.store.restore(old['id'])
        self.assertEqual((self.saves / 'slot').read_bytes(), b'old')
        self.assertFalse((self.saves / 'extra').exists())
        recovery = Path(result['recovery_directory'])
        self.assertEqual((recovery / 'slot').read_bytes(), b'new')
        self.assertEqual((recovery / 'extra').read_bytes(), b'delete on restore')
        destination = SaveStore(self.base / 'other game', self.state)
        with destination:
            imported = destination.import_backup(archive)
            destination.restore(imported['id'])
            self.assertEqual((destination.saves / 'slot').read_bytes(), b'old')
        with self.assertRaises(FileExistsError):
            self.store.export(old['id'], archive)

    def test_same_installation_lock_and_running_guard(self):
        with self.assertRaises(GameRunningError):
            SaveStore(self.root / '..' / self.root.name, self.state).acquire()
        self.store.close()
        self.store.acquire(running=True)
        snapshot = self.store.snapshot()
        for operation in (lambda: self.store.restore(snapshot['id']),
                          lambda: self.store.delete(snapshot['id']),
                          lambda: self.store.export(snapshot['id'], self.base / 'x.zip')):
            with self.assertRaises(GameRunningError):
                operation()
        self.store.close()
        with SaveStore(self.root, self.state) as second:
            self.assertEqual(second.list_snapshots()[0]['id'], snapshot['id'])

    def test_delete_only_selected_snapshot_preserves_current_saves_and_refuses_corruption(self):
        self.write(b'first')
        first = self.store.snapshot()
        self.write(b'second')
        second = self.store.snapshot()
        self.assertEqual(self.store.delete(first['id']), {'deleted': first['id']})
        self.assertEqual([item['id'] for item in self.store.list_snapshots()], [second['id']])
        self.assertEqual((self.saves / 'slot').read_bytes(), b'second')
        with self.assertRaisesRegex(ValueError, 'Invalid snapshot ID'):
            self.store.delete('../saves')
        payload = self.store.snapshots / second['id'] / 'files/slot'
        payload.write_bytes(b'broken')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.store.delete(second['id'])
        self.assertTrue(payload.exists())

    def test_corruption_refused_before_replacement(self):
        self.write(b'old')
        snapshot = self.store.snapshot()
        self.write(b'new')
        payload = self.store.snapshots / snapshot['id'] / 'files/slot'
        payload.write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.store.restore(snapshot['id'])
        self.assertEqual((self.saves / 'slot').read_bytes(), b'new')

    def test_restore_publication_failure_rolls_back_original(self):
        self.write(b'old')
        snapshot = self.store.snapshot()
        self.write(b'new')
        with patch('re4pc.backups._exchange', side_effect=OSError('injected publication failure')):
            with self.assertRaisesRegex(OSError, 'injected'):
                self.store.restore(snapshot['id'])
        self.assertEqual((self.saves / 'slot').read_bytes(), b'new')
        self.assertEqual(len(self.store.list_snapshots()), 2)

    def test_postpublication_fsync_failure_restores_original(self):
        from re4pc.backups import _sync
        self.write(b'old')
        snapshot = self.store.snapshot()
        self.write(b'new')
        failed = False
        def sync(directory):
            nonlocal failed
            if Path(directory) == self.root and not failed:
                failed = True
                raise OSError('injected fsync failure')
            return _sync(directory)
        with patch('re4pc.backups._sync', side_effect=sync):
            with self.assertRaisesRegex(OSError, 'fsync failure'):
                self.store.restore(snapshot['id'])
        self.assertTrue(failed)
        self.assertEqual((self.saves / 'slot').read_bytes(), b'new')
        self.assertFalse(list(self.root.glob('.save-recovery-*')))

    def test_rollback_failure_keeps_original_recovery_directory(self):
        from re4pc.backups import _sync, _exchange
        self.write(b'old')
        snapshot = self.store.snapshot()
        self.write(b'new')
        count = 0
        def exchange(source, destination):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('injected rollback failure')
            return _exchange(source, destination)
        def sync(directory):
            if Path(directory) == self.root:
                raise OSError('injected fsync failure')
            return _sync(directory)
        with patch('re4pc.backups._sync', side_effect=sync), patch('re4pc.backups._exchange', side_effect=exchange):
            with self.assertRaisesRegex(RuntimeError, 'rollback failed; original saves preserved'):
                self.store.restore(snapshot['id'])
        recoveries = list(self.root.glob('.save-recovery-*'))
        self.assertEqual(len(recoveries), 1)
        self.assertEqual((recoveries[0] / 'slot').read_bytes(), b'new')
        self.assertEqual((self.saves / 'slot').read_bytes(), b'old')

    def test_interrupted_snapshot_leaves_previous_set(self):
        self.write(b'old')
        old = self.store.snapshot()
        self.write(b'new')
        with patch('re4pc.backups.os.rename', side_effect=OSError('injected')):
            with self.assertRaises(OSError):
                self.store.snapshot()
        self.assertEqual([s['id'] for s in self.store.list_snapshots()], [old['id']])
        self.assertFalse(any(p.name.startswith('.snapshot-') for p in self.store.snapshots.iterdir()))

    def test_process_interruption_keeps_previous_atomic_snapshot(self):
        self.write(b'old')
        old = self.store.snapshot()
        self.write(b'new')
        self.store.close()
        code = """import os,sys
from re4pc.backups import SaveStore
with SaveStore(sys.argv[1],sys.argv[2]) as store:
    os.rename=lambda *args:os._exit(99)
    store.snapshot()
"""
        result = subprocess.run([sys.executable, '-c', code, str(self.root), str(self.state)])
        self.assertEqual(result.returncode, 99)
        self.store.acquire()
        self.assertEqual([s['id'] for s in self.store.list_snapshots()], [old['id']])
        self.assertTrue(list(self.store.snapshots.glob('.snapshot-*')))
        # A subsequent operation skips unpublished directories and succeeds.
        new = self.store.snapshot()
        self.assertNotEqual(old['id'], new['id'])
        self.assertEqual(len(self.store.list_snapshots()), 2)

    def test_archive_traversal_duplicates_symlinks_and_manifest_tamper(self):
        for kind in ('traversal', 'duplicate', 'symlink', 'manifest'):
            archive = self.base / (kind + '.zip')
            with zipfile.ZipFile(archive, 'w') as z:
                if kind == 'traversal':
                    z.writestr('../outside', b'x')
                elif kind == 'duplicate':
                    z.writestr('manifest.json', b'{}')
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore', UserWarning)
                        z.writestr('manifest.json', b'{}')
                elif kind == 'symlink':
                    info = zipfile.ZipInfo('files/link')
                    info.external_attr = 0o120777 << 16
                    z.writestr(info, b'/tmp')
                else:
                    z.writestr('manifest.json', json.dumps({'id': '../evil'}))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.store.import_backup(archive)
        self.assertFalse((self.base / 'outside').exists())
        self.assertEqual(self.store.list_snapshots(), [])

    def test_save_symlinks_are_rejected(self):
        outside = self.base / 'outside'
        outside.write_bytes(b'private')
        (self.saves / 'slot').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'regular'):
            self.store.snapshot()


class DeleteBackupCliTests(unittest.TestCase):
    def test_cli_delete_roundtrip_preserves_active_saves(self):
        from re4pc.launcher import child_command
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / 'game with spaces'
            (root / 'saves').mkdir(parents=True)
            (root / 'saves' / 'slot').write_bytes(b'active save')
            environment = dict(os.environ, XDG_STATE_HOME=str(base / 'state'))
            state = base / 'state/re4mepc/backups'
            with SaveStore(root, state) as store:
                identity = store.snapshot()['id']
            result = subprocess.run(child_command('delete-backup', identity, '--game', root),
                                    env=environment, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {'deleted': identity})
            with SaveStore(root, state) as store:
                self.assertEqual(store.list_snapshots(), [])
            self.assertEqual((root / 'saves/slot').read_bytes(), b'active save')
