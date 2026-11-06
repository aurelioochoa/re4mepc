"""Cross-platform invariants of the native helpers and guest memory."""
import ctypes as C
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import unicorn.arm_const as arm_const
import unicorn.unicorn_const as unicorn_const

from re4pc.arm import ArmRuntime
from re4pc.platform_memory import TRANSLATED_GUEST_BASE

ROOT = Path(__file__).resolve().parent.parent


class NativeAbiTests(unittest.TestCase):
    def test_vendored_unicorn_constants_match_the_python_binding(self):
        header = (ROOT / 'native/uc_api.h').read_text()
        values = dict(re.findall(r'#define (UC_\w+) (\d+)', header))
        expected = {'UC_ERR_OK': unicorn_const.UC_ERR_OK, 'UC_HOOK_CODE': unicorn_const.UC_HOOK_CODE,
                    'UC_ARM_REG_R0': arm_const.UC_ARM_REG_R0, 'UC_ARM_REG_R1': arm_const.UC_ARM_REG_R1,
                    'UC_ARM_REG_R2': arm_const.UC_ARM_REG_R2, 'UC_ARM_REG_R3': arm_const.UC_ARM_REG_R3}
        self.assertEqual({name: int(values[name]) for name in expected}, expected)

    def test_translated_memory_keeps_guest_addresses_32_bit(self):
        with patch.dict(os.environ, {'RE4PC_TRANSLATED_MEMORY': '1'}):
            arm = ArmRuntime()
        try:
            self.assertEqual(arm.base, TRANSLATED_GUEST_BASE)
            self.assertLessEqual(arm.base + arm.SIZE, 1 << 32)
            pointer = arm.alloc(32)
            arm.write(pointer, b'guest bytes\0')
            self.assertEqual(arm.string(pointer), 'guest bytes')
            self.assertEqual(C.string_at(arm.pointer(pointer), 5), b'guest')
            self.assertEqual(bytes(arm.uc.mem_read(pointer, 5)), b'guest')
            if arm.host != arm.base:
                self.assertEqual(arm.pointer(pointer) - pointer, arm.delta)
        finally:
            arm.close()


if __name__ == '__main__':
    unittest.main()
