import unittest
from types import SimpleNamespace
from re4pc.arm import ArmRuntime
from re4pc.save_boundary import SaveBoundary, SAVE_SYMBOL


class SaveBoundaryTests(unittest.TestCase):
    def test_backup_publication_failure_is_not_finalized_twice(self):
        arm = ArmRuntime()
        address = arm.base + 0x4000
        arm.write(address, b'\x00\xb5\x01\x20\x00\xbd')
        arm.symbols[SAVE_SYMBOL] = address | 1
        arm.symbol_sizes[SAVE_SYMBOL] = 6
        attempts = []
        def publish(success):
            attempts.append(success)
            raise OSError('snapshot publication failed')
        try:
            boundary = SaveBoundary(arm, SimpleNamespace(before_write=lambda:None, after_write=publish))
            with self.assertRaisesRegex(OSError, 'publication failed'):
                arm.call(SAVE_SYMBOL)
            boundary.abort()
            self.assertEqual(attempts, [True])
            self.assertEqual((boundary.completed, boundary.failed), (0, 1))
            self.assertFalse(boundary.active)
        finally:
            arm.close()

    def test_snapshot_brackets_success_failure_and_interruption(self):
        arm = ArmRuntime()
        operations = []
        store = SimpleNamespace(before_write=lambda: operations.append('before'),
            after_write=lambda success: operations.append(('after', success)))
        # Authored Thumb instructions: push lr; mov r0,1; pop pc.
        address = arm.base + 0x4000
        arm.write(address, b'\x00\xb5\x01\x20\x00\xbd')
        arm.symbols[SAVE_SYMBOL] = address | 1
        arm.symbol_sizes[SAVE_SYMBOL] = 6
        try:
            boundary = SaveBoundary(arm, store)
            self.assertEqual(arm.call(SAVE_SYMBOL), 1)
            self.assertEqual(operations, ['before', ('after', True)])
            arm.write(address + 2, b'\x00\x20')
            # Invalidate translated code after modifying this synthetic fixture.
            arm.uc.ctl_remove_cache(address, address + 6)
            self.assertEqual(arm.call(SAVE_SYMBOL), 0)
            self.assertEqual(operations[-2:], ['before', ('after', False)])
            self.assertEqual((boundary.completed, boundary.failed), (1, 1))
            boundary.active = True
            boundary.abort()
            self.assertEqual(operations[-1], ('after', False))
            self.assertFalse(boundary.active)
        finally:
            arm.close()

    def test_failed_prewrite_prevents_native_execution(self):
        arm = ArmRuntime()
        address = arm.base + 0x4000
        arm.write(address, b'\x00\xb5\x01\x20\x00\xbd')
        arm.symbols[SAVE_SYMBOL] = address | 1
        arm.symbol_sizes[SAVE_SYMBOL] = 6
        def fail():
            raise OSError('backup disk full')
        try:
            boundary = SaveBoundary(arm, SimpleNamespace(before_write=fail))
            with self.assertRaisesRegex(OSError, 'disk full'):
                arm.call(SAVE_SYMBOL)
            self.assertFalse(boundary.active)
        finally:
            arm.close()
