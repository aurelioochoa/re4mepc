"""ARM EABI loader with shared guest/host memory and strict import resolution."""
import ctypes as C
import io
import struct
from collections import Counter
from contextlib import nullcontext
import time
import sys
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_INVALID, UcError
from unicorn.arm_const import *

REGS = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)

class ArmRuntime:
    SIZE = 256 * 1024 * 1024

    def __init__(self, diagnostics=None):
        self.diagnostics = diagnostics
        self._profile_hooks = []
        self._profile_returns = {}
        self._profile_stack = []
        self._profile_names = set()
        self.libc = C.CDLL(None)
        mmap = self.libc.mmap
        mmap.argtypes = (C.c_void_p, C.c_size_t, C.c_int, C.c_int, C.c_int, C.c_long)
        mmap.restype = C.c_void_p
        self.base = mmap(None, self.SIZE, 3, 0x22 | 0x40, -1, 0)  # Linux MAP_32BIT
        if self.base is None or self.base == C.c_void_p(-1).value or self.base + self.SIZE > 0x100000000:
            raise RuntimeError('Cannot allocate ARM32 shared memory (Linux x86_64 required)')
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.uc.mem_map_ptr(self.base, self.SIZE, 7, self.base)
        self.uc.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
        self.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        self.uc.reg_write(UC_ARM_REG_SP, self.base + self.SIZE - 0x1000)
        self.heap = self.base + 16 * 1024 * 1024
        self.heap_end = self.base + self.SIZE - 2 * 1024 * 1024
        self.allocations = {}
        self.free_blocks = []
        self.trap_next = self.base + 8 * 1024 * 1024
        self.trap_end = self.trap_next + 1024 * 1024
        self.return_address = self.trap_end + 0x1000
        self.symbols = {}
        self.symbol_sizes = {}
        self.imports = {}
        self.traps = {}
        self.modules = []
        self.calls = Counter()
        self.last_call = ''
        trap = self._trap_profile if diagnostics and diagnostics.import_hooks else self._trap
        self.uc.hook_add(UC_HOOK_CODE, trap, begin=self.trap_next, end=self.trap_end)
        self.uc.hook_add(UC_HOOK_MEM_INVALID, self._invalid_memory)
        self.pending_error = None
        self.fast = None
        self.native_math = None
        self.graphics_bridge = None
        # Reuse the native register buffers instead of constructing four
        # ctypes objects and crossing the FFI four times per import.
        self._arg_registers = (C.c_int * 4)(*REGS)
        self._arg_values = (C.c_uint32 * 4)()
        self._arg_pointers = (C.c_void_p * 4)(*(C.addressof(self._arg_values)+4*i for i in range(4)))
        self._callback_args = None
        self.libc.strnlen.argtypes = (C.c_void_p,C.c_size_t)
        self.libc.strnlen.restype = C.c_size_t

    def contains(self, pointer, size=1):
        return self.base <= pointer and pointer + size <= self.base + self.SIZE

    def check(self, pointer, size=1):
        if not self.contains(pointer, size):
            raise RuntimeError(f'Invalid guest pointer 0x{pointer:x} + {size}')
        return pointer

    def read(self, pointer, size):
        return C.string_at(self.check(pointer, size), size)

    def write(self, pointer, data):
        self.check(pointer, len(data))
        C.memmove(pointer, data, len(data))

    def u32(self, pointer):
        return struct.unpack('<I', self.read(pointer, 4))[0]

    def w32(self, pointer, value):
        self.write(pointer, struct.pack('<I', value & 0xffffffff))

    def string(self, pointer):
        if not pointer:
            return ''
        self.check(pointer)
        limit = min(self.base + self.SIZE - pointer, 65536)
        length = self.libc.strnlen(pointer,limit)
        value = C.string_at(pointer,length)
        if length == limit:
            raise RuntimeError('Unterminated guest string')
        return value.decode('utf-8', 'replace')

    def alloc(self, size):
        requested = size
        size = max(16, (size + 15) & ~15)
        diagnostics = self.diagnostics
        started = time.perf_counter() if diagnostics else 0
        probes = 0
        for i, (pointer, available) in enumerate(self.free_blocks):
            probes += 1
            if available >= size:
                self.free_blocks.pop(i)
                self.allocations[pointer] = available
                if diagnostics:
                    diagnostics.allocation(requested, available, probes, time.perf_counter()-started)
                return pointer
        pointer = self.heap
        if pointer + size > self.heap_end:
            raise MemoryError('ARM heap exhausted')
        self.heap += size
        self.allocations[pointer] = size
        if diagnostics:
            diagnostics.allocation(requested, size, probes, time.perf_counter()-started)
        C.memset(pointer, 0, size)
        return pointer

    def free(self, pointer):
        if pointer:
            size = self.allocations.pop(pointer, None)
            if size is None:
                raise RuntimeError(f'Free of unknown allocation 0x{pointer:x}')
            self.free_blocks.append((pointer, size))
            if self.diagnostics:
                self.diagnostics.freed(size)

    def cstring(self, value):
        data = value.encode() if isinstance(value, str) else bytes(value)
        pointer = self.alloc(len(data) + 1)
        self.write(pointer, data + b'\0')
        return pointer

    def args(self, count=4):
        if count < 0: raise ValueError('Negative argument count')
        if self._callback_args is None:
            status = self.uc._do_reg_read_batch(self._arg_registers, self._arg_pointers, min(count, 4))
            if status: raise UcError(status)
            result = list(self._arg_values[:min(count, 4)])
        else:
            result = self._callback_args[:min(count, 4)]
        if count > 4:
            sp = self.uc.reg_read(UC_ARM_REG_SP)
            result += struct.unpack('<'+'I'*(count-4), self.read(sp,4*(count-4)))
        return result

    def register(self, name, callback):
        if name in self.imports:
            return self.imports[name]
        pointer = self.trap_next
        self.trap_next += 4
        if self.trap_next >= self.trap_end:
            raise RuntimeError('Import trampoline memory exhausted')
        self.write(pointer, b'\x1e\xff\x2f\xe1')  # ARM bx lr
        self.traps[pointer] = (name, callback)
        self.imports[name] = pointer
        return pointer

    def _trap(self, uc, address, size, context):
        try:
            name, callback = self.traps[address]
            self.last_call = name
            self.calls[name] += 1
            self._callback_args = self.args()
            if self.diagnostics:
                phase = ('graphics_upload' if name in ('glTexImage2D', 'glTexSubImage2D')
                         else 'graphics_submission' if name.startswith('gl') else 'host_services')
                if name.startswith('gl') and name != 'glCompressedTexImage2D':
                    result = self.diagnostics.graphics_service(phase, name, callback, self._callback_args)
                else:
                    with self.diagnostics.phase(phase, operation=name):
                        result = callback(*self._callback_args)
            else:
                result = callback(*self._callback_args)
            if result is not None:
                uc.reg_write(UC_ARM_REG_R0, int(result) & 0xffffffff)
        except BaseException as error:
            self.pending_error = error
            uc.emu_stop()
        finally:
            self._callback_args = None

    def _trap_profile(self, uc, address, size, context):
        diagnostics = self.diagnostics
        if diagnostics is None:
            return self._trap(uc, address, size, context)
        phase = diagnostics.phase('import_dispatch', operation=self.traps[address][0])
        phase.__enter__()
        try:
            self._trap(uc, address, size, context)
        finally:
            error = self.pending_error
            phase.__exit__(type(error) if error else None, error, None)

    def _invalid_memory(self, uc, access, address, size, value, context):
        self.pending_error = RuntimeError(
            f'ARM invalid memory access={access} address=0x{address:x} size={size} '
            f'PC=0x{uc.reg_read(UC_ARM_REG_PC):x} LR=0x{uc.reg_read(UC_ARM_REG_LR):x} '
            f'last import={self.last_call}')
        return False

    def load(self, path, offset):
        with self.diagnostics.phase('file_read', operation=str(path)) if self.diagnostics else nullcontext():
            data = path.read_bytes()
            if self.diagnostics:
                self.diagnostics.count('file_read_count')
                self.diagnostics.count('file_read_bytes', len(data))
        elf = ELFFile(io.BytesIO(data))
        if elf.elfclass != 32 or elf['e_machine'] != 'EM_ARM':
            raise ValueError(f'{path}: expected an ARM32 ELF')
        base = self.base + offset
        for segment in elf.iter_segments():
            if segment['p_type'] == 'PT_LOAD':
                self.check(base + segment['p_vaddr'], segment['p_memsz'])
                self.write(base + segment['p_vaddr'], segment.data())
        symtab = elf.get_section_by_name('.dynsym')
        for symbol in symtab.iter_symbols():
            if symbol['st_shndx'] != 'SHN_UNDEF' and symbol.name:
                self.symbols[symbol.name] = base + symbol['st_value']
                self.symbol_sizes[symbol.name] = symbol['st_size']
        module = {'elf': elf, 'base': base, 'path': path, 'symbols': symtab}
        self.modules.append(module)
        return module

    def relocate(self):
        unresolved = set()
        for module in self.modules:
            base, elf, symtab = module['base'], module['elf'], module['symbols']
            for section in elf.iter_sections():
                if section['sh_type'] != 'SHT_REL':
                    continue
                for relocation in section.iter_relocations():
                    pointer = base + relocation['r_offset']
                    addend = self.u32(pointer)
                    kind, index = relocation['r_info_type'], relocation['r_info_sym']
                    symbol = symtab.get_symbol(index)
                    if kind in (0, 23):
                        target = 0
                    elif symbol['st_shndx'] != 'SHN_UNDEF':
                        target = base + symbol['st_value']
                    else:
                        target = self.symbols.get(symbol.name, self.imports.get(symbol.name))
                        if target is None:
                            if symbol['st_info']['bind'] == 'STB_WEAK':
                                target = 0
                            else:
                                unresolved.add(symbol.name)
                                continue
                    if kind == 23:  # R_ARM_RELATIVE
                        value = base + addend
                    elif kind in (21, 22):  # GLOB_DAT, JUMP_SLOT
                        value = target
                    elif kind == 2:  # ABS32
                        value = target + addend
                    elif kind == 3:  # REL32
                        value = target + addend - pointer
                    elif kind == 0:
                        continue
                    else:
                        raise RuntimeError(f'Unsupported ARM relocation {kind}')
                    self.w32(pointer, value)
        if unresolved:
            raise RuntimeError('Unimplemented imports: ' + ', '.join(sorted(unresolved)))

    def call(self, address, *args, timeout=30, operation=None):
        operation = operation or (address if isinstance(address, str) else f'ARM 0x{address:x}')
        if isinstance(address, str):
            address = self.symbols[address]
        saved_sp = self.uc.reg_read(UC_ARM_REG_SP)
        sp = saved_sp - ((max(len(args) - 4, 0) * 4 + 7) & ~7)
        for i, value in enumerate(args):
            if i < 4:
                self.uc.reg_write(REGS[i], value & 0xffffffff)
            else:
                self.w32(sp + 4 * (i - 4), value)
        self.uc.reg_write(UC_ARM_REG_SP, sp)
        self.uc.reg_write(UC_ARM_REG_LR, self.return_address)
        self.pending_error = None
        try:
            with self.diagnostics.phase('native_unknown', operation=operation) if self.diagnostics else nullcontext():
                try:
                    self.uc.emu_start(address, self.return_address, timeout=int(timeout * 1000000))
                    if self.pending_error:
                        raise self.pending_error
                finally:
                    if self.graphics_bridge:
                        self.graphics_bridge.collect()
                    # A timeout/error can bypass selected functions' returns.
                    while self._profile_stack:
                        self._profile_stack.pop()[2].__exit__(*sys.exc_info())
        except UcError as error:
            if self.pending_error:
                raise self.pending_error from error
            raise RuntimeError(f'{error}: PC=0x{self.uc.reg_read(UC_ARM_REG_PC):x}, '
                               f'LR=0x{self.uc.reg_read(UC_ARM_REG_LR):x}, '
                               f'last import={self.last_call}') from error
        finally:
            self.uc.reg_write(UC_ARM_REG_SP, saved_sp)
        if self.pending_error:
            raise self.pending_error
        if self.fast: self.fast.check()
        if self.uc.reg_read(UC_ARM_REG_PC) != self.return_address:
            raise TimeoutError(f'ARM call 0x{address:x} timed out at PC=0x{self.uc.reg_read(UC_ARM_REG_PC):x}')
        return self.uc.reg_read(UC_ARM_REG_R0)

    def enable_native_profiles(self, names):
        """Time selected ELF functions, including nested imports, only on request.

        Entry/return hooks use LR and SP, so recursive calls sharing a return
        site remain distinct. Never enable this for a baseline overhead run.
        """
        if not self.diagnostics or not self.diagnostics.native_hooks:
            raise ValueError('Detailed native hooks must be explicitly enabled')
        for name in dict.fromkeys(names):
            if name not in self.symbols:
                raise ValueError(f'Unknown native profiling symbol: {name}')
        for name in dict.fromkeys(names):
            if name in self._profile_names:
                continue
            address = self.symbols[name] & ~1
            self._profile_hooks.append(self.uc.hook_add(UC_HOOK_CODE,
                self._profile_enter, user_data=name, begin=address, end=address))
            self._profile_names.add(name)

    def _profile_enter(self, uc, address, size, name):
        return_address = uc.reg_read(UC_ARM_REG_LR) & ~1
        sp = uc.reg_read(UC_ARM_REG_SP)
        phase = self.diagnostics.phase('native_parser:'+name, operation=name)
        phase.__enter__()
        self._profile_stack.append((return_address, sp, phase))
        if return_address not in self._profile_returns:
            self._profile_returns[return_address] = uc.hook_add(UC_HOOK_CODE,
                self._profile_return, begin=return_address, end=return_address)

    def _profile_return(self, uc, address, size, context):
        sp = uc.reg_read(UC_ARM_REG_SP)
        while self._profile_stack and self._profile_stack[-1][:2] == (address, sp):
            self._profile_stack.pop()[2].__exit__(None, None, None)

    def initialize(self):
        for module in self.modules:
            section = module['elf'].get_section_by_name('.init_array')
            if section:
                for offset in range(0, section['sh_size'], 4):
                    address = self.u32(module['base'] + section['sh_addr'] + offset)
                    if address not in (0, 0xffffffff):
                        self.call(address)

    def close(self):
        if self.graphics_bridge:
            self.graphics_bridge.close()
            self.graphics_bridge = None
        # Destroy Unicorn before releasing memory used by its translated code.
        if self.native_math:
            self.native_math.close()
            self.native_math = None
        if self.fast: self.fast.close()
        self.uc = None
        self.libc.munmap.argtypes = (C.c_void_p, C.c_size_t)
        self.libc.munmap(self.base, self.SIZE)
