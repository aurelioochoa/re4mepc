from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.build_native import build


class NativeBuildTests(unittest.TestCase):
    def test_failed_compile_keeps_previous_helpers_and_success_preserves_open_inodes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);out=root/'build';out.mkdir()
            package=root/'package';(package/'lib').mkdir(parents=True)
            (package/'lib/libunicorn.so.2').write_bytes(b'new Unicorn')
            names=('libre4audio.so','libre4fast.so','libunicorn.so.2')
            for name in names:(out/name).write_bytes(b'original library')
            def compile(command, **kwargs):
                target=Path(command[command.index('-o')+1]);target.write_bytes(b'new helper')
                if target.name=='libre4fast.so':raise subprocess.CalledProcessError(1,command)
            with patch('tools.build_native.subprocess.check_output',return_value=''),patch('tools.build_native.subprocess.run',side_effect=compile):
                with self.assertRaises(subprocess.CalledProcessError):build(root,package)
            self.assertTrue(all((out/name).read_bytes()==b'original library' for name in names))
            self.assertFalse(list(out.glob('.native-*')))
            streams=[(out/name).open('rb') for name in names]
            try:
                def successful(command, **kwargs):Path(command[command.index('-o')+1]).write_bytes(b'new helper')
                with patch('tools.build_native.subprocess.check_output',return_value=''),patch('tools.build_native.subprocess.run',side_effect=successful):build(root,package)
                self.assertTrue(all(stream.read()==b'original library' for stream in streams))
                self.assertEqual((out/'libunicorn.so.2').read_bytes(),b'new Unicorn')
                self.assertTrue(all((out/name).read_bytes()==b'new helper' for name in names[:2]))
            finally:
                for stream in streams:stream.close()
