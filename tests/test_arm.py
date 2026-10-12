import math
import tempfile
import unittest
from pathlib import Path
from re4pc.arm import ArmRuntime
from re4pc.bionic import Bionic,float_in,float_out
from re4pc.eabi import install
from re4pc.jni import JNI

class RuntimeTests(unittest.TestCase):
    def test_graphics_import_has_one_attributed_scope(self):
        from re4pc.diagnostics import Diagnostics
        diagnostics = Diagnostics()
        arm = ArmRuntime(diagnostics=diagnostics)
        try:
            address = arm.register('glDrawArrays', lambda *_: 0)
            arm.call(address)
            phases = diagnostics.metrics()['phases']
            self.assertEqual(phases['graphics_submission']['calls'], 1)
            self.assertNotIn('host_services', phases)
            upload = arm.register('glTexImage2D', lambda *_: 0)
            arm.call(upload)
            self.assertEqual(diagnostics.metrics()['phases']['graphics_upload']['calls'], 1)
        finally:
            arm.close()

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

    def test_batched_arguments_preserve_registers_and_stack_order(self):
        r=self.runtime
        observed=[]
        def invoke(*values):
            observed.append((values,r.args(0),r.args(2),r.args(8)))
            return 123
        target=r.register('arguments',invoke)
        values=(0xffffffff,0x80000000,3,4,5,6,7,8)
        self.assertEqual(r.call(target,*values),123)
        self.assertEqual(observed,[(values[:4],[],list(values[:2]),list(values))])
        self.assertIsNone(r._callback_args)
        from unicorn.arm_const import UC_ARM_REG_R0
        r.uc.reg_write(UC_ARM_REG_R0,456)
        self.assertEqual(r.args(1),[456])

    def test_failed_callback_clears_cached_arguments(self):
        r=self.runtime
        def fail(*args): raise ValueError('callback failure')
        with self.assertRaisesRegex(ValueError,'callback failure'):
            r.call(r.register('failure',fail),1)
        self.assertIsNone(r._callback_args)
        self.assertEqual(r.call(r.register('identity',lambda a,*_:a),9),9)
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

    def test_diagnostics_track_allocator_reuse_and_file_io(self):
        from re4pc.diagnostics import Diagnostics
        r=self.runtime;r.diagnostics=diagnostics=Diagnostics()
        p=r.alloc(17);q=r.alloc(64)
        r.free(p);r.free(q)
        reused=r.alloc(48)
        self.assertEqual(reused,q)
        values=diagnostics.metrics()
        self.assertEqual(values['guest_live_bytes'],64)
        self.assertEqual(values['guest_peak_bytes'],96)
        self.assertEqual(values['counters']['free_block_search_probes'],2)
        self.assertEqual(r.free_blocks,[(p,32)])
        with tempfile.TemporaryDirectory() as directory:
            b=Bionic(r,directory)
            name=r.cstring('saves/data');mode=r.cstring('wb');data=r.cstring('test')
            handle=b.fopen(name,mode);b.fwrite(data,1,4,handle);b.close()
            self.assertEqual(b.files,{})
            handle=b.fopen(name,r.cstring('rb'));target=r.alloc(16)
            self.assertEqual(b.fread(target,2,3,handle),2)
            b.close()
        values=diagnostics.metrics()
        self.assertEqual(values['counters']['file_read_bytes'],4)
        self.assertEqual(values['counters']['file_read_requested_bytes'],6)
        self.assertEqual(values['counters']['file_write_bytes'],4)
        for phase in ('file_read','file_open','file_close','file_write'):
            self.assertGreaterEqual(values['phases'][phase]['seconds'],0)

    def test_host_import_timing_and_failed_call_restore_diagnostic_stack(self):
        from re4pc.diagnostics import Diagnostics
        r=self.runtime;r.diagnostics=diagnostics=Diagnostics()
        def fail(*_): raise ValueError('diagnostic failure')
        with self.assertRaisesRegex(ValueError,'diagnostic failure'):
            r.call(r.register('diagnostic_fail',fail))
        self.assertIsNone(diagnostics.active_operation)
        self.assertEqual(diagnostics._stack,[])
        self.assertEqual(diagnostics.metrics()['phases']['host_services']['calls'],1)
        self.assertEqual(diagnostics.metrics()['phases']['native_unknown']['calls'],1)

    def test_selected_native_hooks_return_through_nested_arm_call(self):
        import struct
        from re4pc.diagnostics import Diagnostics
        r=self.runtime;r.diagnostics=diagnostics=Diagnostics(native_hooks=True)
        caller=r.base+11*1024*1024;callee=caller+64
        # push {lr}; bl callee; pop {pc}. Callee: mov r0,#7; bx lr.
        branch=0xeb000000|(((callee-(caller+4+8))//4)&0xffffff)
        r.write(caller,struct.pack('<III',0xe92d4000,branch,0xe8bd8000))
        r.write(callee,struct.pack('<II',0xe3a00007,0xe12fff1e))
        r.symbols['parser_fixture']=callee
        r.enable_native_profiles(['parser_fixture'])
        self.assertEqual(r.call(caller),7)
        phases=diagnostics.metrics()['phases']
        self.assertEqual(phases['native_parser:parser_fixture']['calls'],1)
        self.assertGreater(phases['native_parser:parser_fixture']['seconds'],0)
        self.assertIsNone(diagnostics.active_operation)
        self.assertEqual(r._profile_stack,[])
        with self.assertRaisesRegex(ValueError,'Unknown native profiling symbol'):
            r.enable_native_profiles(['missing'])

    def test_native_hooks_require_explicit_opt_in(self):
        from re4pc.diagnostics import Diagnostics
        r=self.runtime;r.diagnostics=Diagnostics()
        with self.assertRaisesRegex(ValueError,'explicitly enabled'):
            r.enable_native_profiles([])
