import math
import tempfile
import unittest
from pathlib import Path
from re4pc.arm import ArmRuntime
from re4pc.bionic import Bionic,float_in,float_out
from re4pc.eabi import install
from re4pc.jni import JNI

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.runtime=ArmRuntime()
    def tearDown(self):
        self.runtime.close()
    def test_arm_thumb_interwork_and_import_return(self):
        r=self.runtime;target=r.register('add',lambda a,b,*_:a+b)
        self.assertEqual(r.call(target,40,2),42)
        # Hand-written synthetic Thumb function: movs r0, #7; bx lr.
        thumb=r.base+11*1024*1024;r.write(thumb,bytes.fromhex('07207047'))
        self.assertEqual(r.call(thumb|1),7)
    def test_math_helpers_execute_and_handle_unordered_comparisons(self):
        r=self.runtime;install(r)
        for name,value in [('fadd',8),('fsub',4),('fmul',12),('fdiv',3)]:
            result=r.call(r.imports['__aeabi_'+name],float_out(6),float_out(2))
            self.assertEqual(float_in(result),value)
        for name in ('fcmpeq','fcmplt','fcmple','fcmpge','fcmpgt'):
            self.assertEqual(r.call(r.imports['__aeabi_'+name],float_out(math.nan),float_out(2)),0)
    def test_realloc_preserves_bytes(self):
        r=self.runtime;b=Bionic(r,Path('.'));p=r.alloc(16);r.write(p,b'preserve')
        q=b.realloc(p,1000,0,0);self.assertEqual(r.read(q,8),b'preserve')
        self.assertNotIn(p,r.allocations)
    def test_save_io_persists_across_handles_and_paths_are_confined(self):
        r=self.runtime
        with tempfile.TemporaryDirectory() as directory:
            b=Bionic(r,directory);name=r.cstring('saves/save.dat');data=r.cstring('persist')
            handle=b.fopen(name,r.cstring('wb'));self.assertEqual(b.fwrite(data,1,7,handle),7);b.fclose(handle)
            handle=b.fopen(name,r.cstring('rb'));out=r.alloc(16)
            self.assertEqual(b.fread(out,1,7,handle),7);b.fclose(handle)
            self.assertEqual(r.read(out,7),b'persist')
            with self.assertRaises(ValueError):b.path('../../outside')
    def test_jni_varargs_align_longs_and_promote_floats_to_double(self):
        import struct
        r=self.runtime;j=JNI(r,Path('.'),800,480)
        p=r.alloc(32);r.w32(p,9);r.w32(p+4,123)
        r.write(p+8,struct.pack('<Q',0x100000002));r.write(p+16,struct.pack('<d',0.5))
        self.assertEqual(j.arguments('(ILjava/lang/String;JF)V',1,p),[9,123,0x100000002,0.5])

    def test_native_memory_bridge_preserves_overlapping_bytes(self):
        from re4pc.fast import Fast
        r=self.runtime; fast=Fast(r); p=r.alloc(32)
        r.write(p,b'abcdef\0')
        self.assertEqual(r.call(r.imports['memmove'],p+2,p,6),p+2)
        self.assertEqual(r.read(p,8),b'ababcdef')
        r.call(r.imports['memset'],p+8,0,1)
        self.assertEqual(r.call(r.imports['strlen'],p),8)
        self.assertGreaterEqual(fast.calls(),3)

    def test_native_memory_bridge_rejects_unmapped_pointers(self):
        from re4pc.fast import Fast
        r=self.runtime;Fast(r)
        with self.assertRaisesRegex(RuntimeError,'outside guest memory'):
            r.call(r.imports['memcpy'],r.alloc(16),1,8)
