"""The engine's imported Bionic libc and ARM EABI operations."""
import ctypes as C
import math
import re
from .runtime_log import log
import struct
from contextlib import nullcontext
from pathlib import Path
from unicorn.arm_const import UC_ARM_REG_R1


def signed(value):
    return value if value < 0x80000000 else value - 0x100000000


def float_in(value):
    return struct.unpack('<f', struct.pack('<I', value))[0]


def float_out(value):
    try:
        return struct.unpack('<I', struct.pack('<f', value))[0]
    except OverflowError:
        return 0x7f800000 if value > 0 else 0xff800000


class Bionic:
    def __init__(self, arm, root, diagnostics=None):
        self.arm, self.root = arm, Path(root).resolve()
        self.diagnostics = diagnostics if diagnostics is not None else getattr(arm, 'diagnostics', None)
        self.files = {}
        self.keys = {}
        self.key_next = 1
        self.file_next = 0x1000
        guard = arm.alloc(4)
        arm.w32(guard, 0x5eaf1337)
        arm.symbols['__stack_chk_guard'] = guard
        self.install()

    def reg(self, name, callback):
        self.arm.register(name, callback)

    def install(self):
        a = self.arm
        self.reg('malloc', lambda n, *_: a.alloc(n))
        self.reg('free', lambda p, *_: a.free(p) or 0)
        self.reg('realloc', self.realloc)
        for name in ('memcpy', 'memmove'):
            self.reg(name, lambda dst, src, n, _: (C.memmove(a.check(dst, n), a.check(src, n), n) if n else dst))
        self.reg('memset', lambda dst, v, n, _: (C.memset(a.check(dst, n), v, n) if n else dst))
        a.libc.memcmp.argtypes = (C.c_void_p,C.c_void_p,C.c_size_t)
        a.libc.memcmp.restype = C.c_int
        self.reg('memcmp',lambda p,q,n,_: a.libc.memcmp(a.check(p,n),a.check(q,n),n) if n else 0)
        self.reg('strlen', lambda p, *_: len(a.string(p).encode()))
        self.reg('wcslen', self.wcslen)
        self.reg('strcmp', lambda p, q, *_: (a.string(p) > a.string(q)) - (a.string(p) < a.string(q)))
        self.reg('strncmp', lambda p, q, n, _: (a.string(p)[:n] > a.string(q)[:n]) - (a.string(p)[:n] < a.string(q)[:n]))
        self.reg('strcpy', lambda p, q, *_: a.write(p, a.string(q).encode() + b'\0') or p)
        self.reg('strncpy', self.strncpy)
        self.reg('atoi', lambda p, *_: int(re.match(r'\s*([+-]?\d+)', a.string(p)).group(1)))
        self.reg('strtoul', self.strtoul)
        self.reg('strtod', self.strtod)
        self.reg('fopen', self.fopen)
        self.reg('fclose', self.fclose)
        self.reg('fread', self.fread)
        self.reg('fwrite', self.fwrite)
        self.reg('fseek', self.fseek)
        self.reg('ftell', lambda f, *_: self.files[f].tell())
        self.reg('fgetpos', lambda f, p, *_: a.w32(p, self.files[f].tell()) or 0)
        self.reg('puts', lambda p, *_: log.debug('[game] %s', a.string(p).rstrip()) or 0)
        self.reg('printf', lambda *v: log.debug('[game] %s', self.format(v[0], list(v[1:]) + a.args(16)[4:]).rstrip()) or 0)
        self.reg('sprintf', lambda *v: self.sprintf(v[0], v[1], list(v[2:]) + a.args(20)[4:]))
        self.reg('vsprintf', lambda dst, fmt, va, _: self.sprintf(dst, fmt, [a.u32(va + i * 4) for i in range(24)]))
        self.reg('__android_log_print', lambda *v: log.log({4:20,5:30,6:40,7:50}.get(v[0],10), '[android] %s', self.format(v[2], [v[3]] + a.args(16)[4:]).rstrip()) or 0)
        for name in ('__cxa_atexit', '__aeabi_atexit', '__cxa_finalize', '__gnu_Unwind_Find_exidx',
                     '__aeabi_unwind_cpp_pr0', '__aeabi_unwind_cpp_pr1'):
            self.reg(name, lambda *_: 0)
        for name in ('abort', 'exit', '__stack_chk_fail', '__cxa_pure_virtual', 'raise'):
            self.reg(name, self.fatal(name))
        for name in ('pthread_mutex_init', 'pthread_mutex_lock', 'pthread_mutex_unlock',
                     'pthread_mutex_destroy', 'pthread_cond_broadcast'):
            self.reg(name, lambda *_: 0)  # No pthread_create is imported: engine runs on one thread.
        self.reg('pthread_cond_wait', self.fatal('unexpected blocking condition wait'))
        self.reg('pthread_key_create', self.key_create)
        self.reg('pthread_getspecific', lambda key, *_: self.keys.get(key, 0))
        self.reg('pthread_setspecific', lambda key, val, *_: self.keys.__setitem__(key, val) or 0)
        self.reg('sqrtf', lambda x, *_: float_out(math.sqrt(float_in(x))))
        self.reg('log', self.log)
        for name, operation in (('fadd', lambda x,y:x+y), ('fsub', lambda x,y:x-y),
                                ('fmul', lambda x,y:x*y), ('fdiv', lambda x,y:x/y if y else math.copysign(math.inf,x))):
            self.reg('__aeabi_' + name, lambda x, y, *_, op=operation: float_out(op(float_in(x), float_in(y))))
        for name, operation in (('fcmpeq', lambda x,y:x==y), ('fcmplt', lambda x,y:x<y),
                                ('fcmple', lambda x,y:x<=y), ('fcmpge', lambda x,y:x>=y), ('fcmpgt', lambda x,y:x>y)):
            self.reg('__aeabi_' + name, lambda x, y, *_, op=operation: int(op(float_in(x), float_in(y))))
        self.reg('__aeabi_f2iz', lambda x, *_: int(float_in(x)))
        self.reg('__aeabi_i2f', lambda x, *_: float_out(signed(x)))
        self.reg('__aeabi_ui2f', lambda x, *_: float_out(x))
        self.reg('__aeabi_f2d', self.f2d)
        for name in ('uidiv', 'idiv', 'uidivmod', 'idivmod'):
            self.reg('__aeabi_' + name, self.divide(name))
        for name in ('AndroidBitmap_lockPixels', 'AndroidBitmap_unlockPixels',
                     'eglCreatePbufferSurface', 'eglDestroySurface', 'eglMakeCurrent', 'eglGetConfigAttrib', 'eglGetError'):
            self.reg(name, self.fatal('unimplemented Android offscreen rendering: ' + name))

    def fatal(self, name):
        def fail(*args):
            raise RuntimeError(f'Engine called {name}: {args}')
        return fail

    def realloc(self, pointer, size, *_):
        if not pointer:
            return self.arm.alloc(size)
        if not size:
            self.arm.free(pointer)
            return 0
        available = self.arm.allocations[pointer]
        if size <= available:
            return pointer
        result = self.arm.alloc(size)
        C.memmove(result, pointer, available)
        self.arm.free(pointer)
        return result

    def wcslen(self, pointer, *_):
        n = 0
        while self.arm.u32(pointer + n * 4):
            n += 1
        return n

    def strncpy(self, dst, src, n, _):
        self.arm.write(dst, self.arm.string(src).encode()[:n].ljust(n, b'\0'))
        return dst

    def strtoul(self, pointer, end, base, _):
        value = self.arm.string(pointer)
        match = re.match(r'\s*[+-]?(?:0[xX][0-9a-fA-F]+|[0-9a-fA-F]+)', value)
        if end:
            self.arm.w32(end, pointer + (match.end() if match else 0))
        return int(match.group(), base or 0) if match else 0

    def double_return(self, value):
        bits = struct.unpack('<Q', struct.pack('<d', value))[0]
        self.arm.uc.reg_write(UC_ARM_REG_R1, bits >> 32)
        return bits & 0xffffffff

    def strtod(self, pointer, end, *_):
        value = self.arm.string(pointer)
        match = re.match(r'\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?', value)
        if end:
            self.arm.w32(end, pointer + (match.end() if match else 0))
        return self.double_return(float(match.group()) if match else 0)

    def f2d(self, value, *_):
        return self.double_return(float_in(value))

    def log(self, low, high, *_):
        value = struct.unpack('<d', struct.pack('<II', low, high))[0]
        return self.double_return(math.log(value))

    def divide(self, name):
        def operation(x, y, *_):
            if name.startswith('i'):
                x, y = signed(x), signed(y)
            if not y:
                raise ZeroDivisionError('ARM EABI division by zero')
            q = (abs(x) // abs(y)) * (-1 if (x < 0) != (y < 0) else 1)
            if name.endswith('mod'):
                self.arm.uc.reg_write(UC_ARM_REG_R1, (x - q*y) & 0xffffffff)
            return q
        return operation

    def key_create(self, pointer, *_):
        key = self.key_next
        self.key_next += 1
        self.arm.w32(pointer, key)
        return 0

    def path(self, value):
        value = value.replace('\\', '/')
        if '/data/monhun/' in value:
            value = 'data/monhun/' + value.split('/data/monhun/', 1)[1]
        elif '/data/bmptest/' in value:
            value = 'data/bmptest/' + value.split('/data/bmptest/', 1)[1]
        elif '/save/' in value:
            value = 'saves/' + value.split('/save/', 1)[1]
        value = value.removesuffix('.png')
        candidate = (self.root / value).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError(f'Engine path outside game directory: {value}')
        return candidate

    def fopen(self, filename, mode, *_):
        name, flags = self.arm.string(filename), self.arm.string(mode)
        path = self.path(name)
        try:
            if any(flag in flags for flag in 'wa+'):
                path.parent.mkdir(parents=True, exist_ok=True)
            with self.diagnostics.phase('file_open', operation=str(path)) if self.diagnostics else nullcontext():
                stream = path.open(flags if 'b' in flags else flags + 'b')
            if self.diagnostics:
                self.diagnostics.count('file_open_count')
        except OSError as error:
            log.debug('[file] cannot open %s: %s', name, error)
            return 0
        handle = self.file_next
        self.file_next += 1
        self.files[handle] = stream
        return handle

    def fclose(self, handle, *_):
        stream = self.files.pop(handle)
        with self.diagnostics.phase('file_close', operation=str(stream.name)) if self.diagnostics else nullcontext():
            stream.close()
        return 0

    def fread(self, pointer, size, count, handle):
        if not size:
            return 0
        stream = self.files[handle]
        with self.diagnostics.phase('file_read', operation=str(stream.name)) if self.diagnostics else nullcontext():
            data = stream.read(size * count)
        if self.diagnostics:
            self.diagnostics.count('file_read_count')
            self.diagnostics.count('file_read_requested_bytes', size*count)
            self.diagnostics.count('file_read_bytes', len(data))
        self.arm.write(pointer, data)
        return len(data) // size

    def fwrite(self, pointer, size, count, handle):
        if not size:
            return 0
        stream = self.files[handle]
        data = self.arm.read(pointer, size*count)
        with self.diagnostics.phase('file_write', operation=str(stream.name)) if self.diagnostics else nullcontext():
            written = stream.write(data)
        if self.diagnostics:
            self.diagnostics.count('file_write_count')
            self.diagnostics.count('file_write_bytes', written)
        return written // size

    def fseek(self, handle, offset, whence, _):
        stream = self.files[handle]
        with self.diagnostics.phase('file_seek', operation=str(stream.name)) if self.diagnostics else nullcontext():
            stream.seek(signed(offset), whence)
        return 0

    def close(self):
        """Flush every native file before releasing the installation save lock."""
        first_error = None
        for handle in list(self.files):
            try:
                self.fclose(handle)
            except OSError as error:
                first_error = first_error or error
        if first_error is not None:
            raise first_error

    def format(self, pointer, args):
        text, index = self.arm.string(pointer), 0
        pattern = re.compile(r'%([-+ #0]*)(\d*)(?:\.(\d+))?([hlz]*)([diuoxXscfegp%])')
        def replace(match):
            nonlocal index
            flags, width, precision, length, kind = match.groups()
            if kind == '%':
                return '%'
            value = args[index]
            index += 1
            if kind == 's':
                value = self.arm.string(value)
            elif kind == 'p':
                return f'0x{value:x}'
            elif kind in 'feg':
                if index % 2 == 0:
                    index += 1  # doubles are aligned to even ARM argument slots; refined per caller below
                high = args[index]
                index += 1
                value = struct.unpack('<d', struct.pack('<II', value, high))[0]
            elif kind in 'di':
                value = signed(value)
            spec = '%' + flags + width + ('.' + precision if precision else '') + ('d' if kind == 'u' else kind)
            return spec % value
        return pattern.sub(replace, text)

    def sprintf(self, dst, fmt, args):
        value = self.format(fmt, args).encode()
        self.arm.write(dst, value + b'\0')
        return len(value)
