import tempfile
import unittest
from pathlib import Path
from tools.migrate_local import inventory, migrate, verify


class MigrationTests(unittest.TestCase):
    def test_migration_retains_all_bytes_and_save_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'legacy';source.mkdir()
            (source/'empty').mkdir();(source/'save.dat').write_bytes(b'synthetic save')
            (source/'link').symlink_to('save.dat')
            before=inventory(source);destination=root/'external/game';receipt=root/'receipt.json'
            migrate([(source,destination)],receipt)
            self.assertFalse(source.exists())
            self.assertEqual(inventory(destination),before)
            (destination/'new-test-log').write_text('new artifact')
            verify(receipt)
            (destination/'save.dat').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'inventory changed'): verify(receipt)

    def test_every_destination_is_checked_before_any_move(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);first=root/'first';second=root/'second'
            first.mkdir();second.mkdir();existing=root/'existing';existing.mkdir()
            (existing/'keep').write_bytes(b'preserve')
            with self.assertRaisesRegex(ValueError,'already exists'):
                migrate([(first,root/'new'),(second,existing)],root/'receipt.json')
            self.assertTrue(first.exists());self.assertTrue(second.exists())
            self.assertFalse((root/'new').exists())
            self.assertEqual((existing/'keep').read_bytes(),b'preserve')

    def test_broken_symlink_destination_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'legacy';source.mkdir()
            destination=root/'external';destination.symlink_to('absent')
            with self.assertRaisesRegex(ValueError,'already exists'):
                migrate([(source,destination)],root/'receipt.json')
            self.assertTrue(destination.is_symlink());self.assertTrue(source.exists())
