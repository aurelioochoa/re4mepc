"""Run component assertions and emit a success marker only after they pass."""
import sys
import unittest
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root))
suite=unittest.defaultTestLoader.discover(str(root/'tests'))
result=unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful(): sys.exit(1)
print('COMPONENT_TESTS_PASS')
