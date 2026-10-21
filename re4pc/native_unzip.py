"""Inflate the engine's compressed resources with host zlib.

CMN_Unzip::GetData(this, src, dst, size) resets its bit reader and returns
_DecodeFile(dst, size): a raw RFC 1951 DEFLATE decoder that writes every
decoded byte to dst and returns the count, without consulting size. Running it
bit by bit under emulation dominates resource loading. DEFLATE output is fully
determined by its input, so zlib yields the identical bytes.

The hook replaces only a call zlib completes. Any stream zlib rejects, or
output that would leave guest memory, falls through to the original decoder.
"""
import struct
import zlib
from contextlib import nullcontext
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_LR, UC_ARM_REG_PC

SYMBOL = '_ZN9CMN_Unzip7GetDataEPhS0_l'
CHUNK = 64 * 1024


class NativeUnzip:
    def __init__(self, arm):
        self.arm = arm
        self.hook = None
        self.calls = self.fallbacks = self.bytes = 0

    def install(self):
        address = self.arm.symbols.get(SYMBOL)
        if address is None or not address & 1:
            raise RuntimeError('Unsupported native unzip entry')
        start = address & ~1
        self.hook = self.arm.uc.hook_add(UC_HOOK_CODE, self._enter, begin=start, end=start)

    def inflate(self, src):
        """Decode one raw DEFLATE stream; return (data, compressed bytes used)."""
        arm = self.arm
        decoder = zlib.decompressobj(-zlib.MAX_WBITS)
        parts, pointer = [], src
        while not decoder.eof:
            available = arm.base + arm.SIZE - pointer
            if available <= 0:
                raise ValueError('DEFLATE stream runs past guest memory')
            chunk = arm.read(pointer, min(CHUNK, available))
            parts.append(decoder.decompress(chunk))
            pointer += len(chunk)
        return b''.join(parts), pointer - src - len(decoder.unused_data)

    def _enter(self, uc, address, size, context):
        this, src, dst = (uc.reg_read(register) for register in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        diagnostics = self.arm.diagnostics
        try:
            with diagnostics.phase('native_unzip', operation='CMN_Unzip::GetData') if diagnostics else nullcontext():
                data, used = self.inflate(src)
                if not self.arm.contains(dst, len(data)) or not self.arm.contains(this, 12):
                    raise ValueError('Inflated data leaves guest memory')
                self.arm.write(dst, data)
                # Leave the reader where _DecodeFile would: source, byte
                # position and pending bit count. Every call resets them.
                self.arm.write(this, struct.pack('<III', src, used, 0))
        except (zlib.error, ValueError, RuntimeError):
            self.fallbacks += 1
            return
        self.calls += 1
        self.bytes += len(data)
        uc.reg_write(UC_ARM_REG_R0, len(data))
        # Return to the Thumb caller; LR keeps its interworking bit.
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def close(self):
        if self.hook is not None:
            self.arm.uc.hook_del(self.hook)
            self.hook = None
