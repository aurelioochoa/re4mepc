import os
import struct
import unittest
import zlib

from re4pc.arm import ArmRuntime
from re4pc.native_unzip import NativeUnzip, SYMBOL


def raw_deflate(data, level=9):
    compressor = zlib.compressobj(level, zlib.DEFLATED, -zlib.MAX_WBITS)
    return compressor.compress(data) + compressor.flush()


class NativeUnzipTests(unittest.TestCase):
    def setUp(self):
        self.arm = ArmRuntime()
        self.addCleanup(self.arm.close)
        # Synthetic stand-in for the emulated decoder: movs r0, #42; bx lr.
        # Reaching it means the original guest code ran.
        self.decoder = self.arm.base + 11 * 1024 * 1024
        self.arm.write(self.decoder, bytes.fromhex('2a207047'))
        self.arm.symbols[SYMBOL] = self.decoder | 1
        self.unzip = NativeUnzip(self.arm)
        self.unzip.install()
        self.addCleanup(self.unzip.close)
        self.this = self.arm.alloc(16)
        self.arm.write(self.this, b'\xff' * 12)

    def call(self, source, dst, size=0):
        src = self.arm.alloc(len(source) + 64)
        # Bytes after the stream must not be consumed or decoded.
        self.arm.write(src, source + b'\xa5' * 64)
        return src, self.arm.call(self.decoder | 1, self.this, src, dst, size)

    def test_replaces_the_emulated_decoder_with_identical_bytes(self):
        payload = os.urandom(3000) + b'resident evil ' * 5000 + bytes(range(256)) * 40
        for level in (0, 1, 9):
            stream = raw_deflate(payload, level)
            dst = self.arm.alloc(len(payload))
            # The engine passes the size but its decoder never consults it.
            src, produced = self.call(stream, dst, size=7)
            self.assertEqual(produced, len(payload))
            self.assertEqual(self.arm.read(dst, produced), payload)
            self.assertEqual(struct.unpack('<III', self.arm.read(self.this, 12)), (src, len(stream), 0))
        self.assertEqual((self.unzip.calls, self.unzip.fallbacks), (3, 0))
        self.assertEqual(self.unzip.bytes, 3 * len(payload))

    def test_fixed_huffman_stored_and_empty_streams(self):
        for payload in (b'', b'a', b'abcabcabcabc' * 3):
            stream = raw_deflate(payload, 1)
            dst = self.arm.alloc(max(1, len(payload)))
            _, produced = self.call(stream, dst)
            self.assertEqual(self.arm.read(dst, produced), payload)
        self.assertEqual(self.unzip.fallbacks, 0)

    def test_rejected_streams_run_the_original_decoder(self):
        dst = self.arm.alloc(64)
        self.arm.write(dst, b'\x11' * 64)
        # BTYPE 3 is reserved, so zlib rejects the very first block header.
        _, produced = self.call(b'\x07' + b'\x00' * 8, dst)
        self.assertEqual(produced, 42)
        self.assertEqual(self.arm.read(dst, 64), b'\x11' * 64)
        self.assertEqual((self.unzip.calls, self.unzip.fallbacks), (0, 1))

    def test_output_beyond_guest_memory_runs_the_original_decoder(self):
        payload = b'x' * 4096
        dst = self.arm.base + self.arm.SIZE - 100
        _, produced = self.call(raw_deflate(payload), dst)
        self.assertEqual(produced, 42)
        self.assertEqual(self.unzip.fallbacks, 1)

    def test_unterminated_stream_at_the_end_of_memory_falls_back(self):
        stream = raw_deflate(os.urandom(5000))[:-20]
        src = self.arm.base + self.arm.SIZE - len(stream)
        self.arm.write(src, stream)
        produced = self.arm.call(self.decoder | 1, self.this, src, self.arm.alloc(8000), 0)
        self.assertEqual(produced, 42)
        self.assertEqual(self.unzip.fallbacks, 1)

    def test_rejects_an_arm_mode_entry(self):
        self.arm.symbols[SYMBOL] = self.decoder
        with self.assertRaises(RuntimeError):
            NativeUnzip(self.arm).install()


if __name__ == '__main__':
    unittest.main()
