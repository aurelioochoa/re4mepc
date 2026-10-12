"""Minimal JNI ABI used by the original libraries; unknown services fail visibly."""
import struct
import time
from pathlib import Path
from .bionic import float_in
from .runtime_log import log
from unicorn.arm_const import UC_ARM_REG_R1

class JNI:
    def __init__(self, arm, root, width, height, trace=False):
        self.arm, self.root = arm, Path(root).resolve()
        self.width, self.height, self.trace = width, height, trace
        self.objects = {}
        self.methods = {}
        self.class_cache = {}
        self.method_cache = {}
        self.singletons = {}
        self.natives = {}
        self.started = time.monotonic()
        self.table = arm.alloc(240 * 4)
        self.env = arm.alloc(4)
        arm.w32(self.env, self.table)
        self.vm_table = arm.alloc(8 * 4)
        self.vm = arm.alloc(4)
        arm.w32(self.vm, self.vm_table)
        self.activity = self.object('activity')
        # Derive slot order from the public JNI C ABI, not platform addresses.
        self.slots = {
            4: ('GetVersion', lambda *_: 0x10004),
            6: ('FindClass', self.find_class),
            10: ('GetSuperclass', lambda _, obj, *__: self.object('java/lang/Object')),
            15: ('ExceptionOccurred', lambda *_: 0),
            17: ('ExceptionClear', lambda *_: 0),
            21: ('NewGlobalRef', lambda _, obj, *__: obj),
            22: ('DeleteGlobalRef', lambda *_: 0),
            23: ('DeleteLocalRef', lambda *_: 0),
            24: ('IsSameObject', lambda _, x, y, __: int(x == y)),
            25: ('NewLocalRef', lambda _, obj, *__: obj),
            28: ('NewObject', self.new_object), 29: ('NewObjectV', self.new_object), 30: ('NewObjectA', self.new_object),
            31: ('GetObjectClass', lambda _, obj, *__: self.object(self.objects.get(obj, {}).get('class', 'java/lang/Object'))),
            32: ('IsInstanceOf', lambda *_: 1),
            33: ('GetMethodID', self.get_method), 113: ('GetStaticMethodID', self.get_method),
            94: ('GetFieldID', self.get_method), 144: ('GetStaticFieldID', self.get_method),
            163: ('NewString', self.new_string),
            164: ('GetStringLength', lambda _, s, *__: len(arm.string(s))),
            165: ('GetStringChars', self.string_chars),
            166: ('ReleaseStringChars', lambda *_: 0),
            167: ('NewStringUTF', lambda _, p, *__: arm.cstring(arm.string(p))),
            168: ('GetStringUTFLength', lambda _, s, *__: len(arm.string(s).encode())),
            169: ('GetStringUTFChars', lambda _, s, *__: s),
            170: ('ReleaseStringUTFChars', lambda *_: 0),
            171: ('GetArrayLength', lambda _, obj, *__: self.objects[obj]['length']),
            176: ('NewByteArray', self.byte_array),
            184: ('GetByteArrayElements', lambda _, obj, *__: self.objects[obj]['data']),
            192: ('ReleaseByteArrayElements', lambda *_: 0),
            200: ('GetByteArrayRegion', self.get_byte_region),
            208: ('SetByteArrayRegion', self.set_byte_region),
            215: ('RegisterNatives', self.register_natives),
            219: ('GetJavaVM', lambda _, out, *__: arm.w32(out, self.vm) or 0),
            228: ('ExceptionCheck', lambda *_: 0),
        }
        for begin, static in ((34, False), (114, True)):
            for category in range(10):
                for variant in range(3):
                    slot = begin + category * 3 + variant
                    self.slots[slot] = (f'Call{"Static" if static else ""}{category}Method{variant}',
                                        self.invoke(variant))
        for slot in range(4, 234):
            name, callback = self.slots.get(slot, (f'UnknownJNI{slot}', self.unknown(slot)))
            arm.w32(self.table + slot * 4, arm.register('JNI.' + name, callback))
        for slot in (4, 6):
            arm.w32(self.vm_table + slot * 4, arm.register(f'JavaVM.GetEnv{slot}', self.get_env))

    def unknown(self, slot):
        def fail(*args):
            raise RuntimeError(f'Unimplemented JNI slot {slot}, args={args}')
        return fail

    def object(self, class_name, **properties):
        pointer = self.arm.alloc(16)
        self.objects[pointer] = {'class': class_name, **properties}
        return pointer

    def get_env(self, vm, out, version, _):
        self.arm.w32(out, self.env)
        return 0

    def find_class(self, env, name, *_):
        value = self.arm.string(name)
        if value.startswith('jp/co/sharp/android/stereo3d/'):
            return 0
        if self.trace:
            log.info('[jni] class %s', value)
        if value not in self.class_cache: self.class_cache[value]=self.object(value)
        return self.class_cache[value]

    def get_method(self, env, clazz, name, signature):
        value, sig = self.arm.string(name), self.arm.string(signature)
        key=(self.objects[clazz]['class'],value,sig)
        if key in self.method_cache: return self.method_cache[key]
        pointer = self.arm.alloc(4)
        self.methods[pointer] = key
        self.method_cache[key] = pointer
        if self.trace:
            log.info('[jni] method %s', self.methods[pointer])
        return pointer

    def new_object(self, env, clazz, method, args):
        return self.object(self.objects[clazz]['class'])

    def register_natives(self, env, clazz, methods, count):
        class_name = self.objects[clazz]['class']
        for i in range(count):
            p = methods + i * 12
            name = self.arm.string(self.arm.u32(p))
            sig = self.arm.string(self.arm.u32(p + 4))
            target = self.arm.u32(p + 8)
            self.natives[(class_name, name)] = (target, sig)
            if class_name.endswith('Bio4PreActivity'):
                self.natives[name] = (target, sig)
            if self.trace:
                log.info('[jni] native %s %s %s %#x', class_name, name, sig, target)
        return 0

    def new_string(self, env, pointer, length, _):
        value = self.arm.read(pointer, length * 2).decode('utf-16-le')
        return self.arm.cstring(value)

    def string_chars(self, env, value, *_):
        data = self.arm.string(value).encode('utf-16-le') + b'\0\0'
        pointer = self.arm.alloc(len(data))
        self.arm.write(pointer, data)
        return pointer

    def byte_array(self, env, length, *_):
        return self.object('[B', length=length, data=self.arm.alloc(length))

    def get_byte_region(self, env, obj, start, length):
        out = self.arm.args(5)[4]
        if start + length > self.objects[obj]['length']:
            raise IndexError('JNI byte array region out of bounds')
        self.arm.write(out, self.arm.read(self.objects[obj]['data'] + start, length))
        return 0

    def set_byte_region(self, env, obj, start, length):
        source = self.arm.args(5)[4]
        if start + length > self.objects[obj]['length']:
            raise IndexError('JNI byte array region out of bounds')
        self.arm.write(self.objects[obj]['data'] + start, self.arm.read(source, length))
        return 0

    def arguments(self, signature, variant, argument):
        import re
        types = re.findall(r'\[*(?:L[^;]+;|[ZBCSIJFD])', signature.split(')')[0][1:])
        values = []
        if variant == 0:
            raw, index = self.arm.args(32), 3
        else:
            index = argument
        for kind in types:
            wide = kind in ('J', 'D') or (kind == 'F' and variant != 2)
            if variant == 0:
                if wide: index = (index + 1) & ~1
                value = raw[index]
                if wide: value |= raw[index + 1] << 32
                index += 2 if wide else 1
            else:
                if variant == 1 and wide: index = (index + 7) & ~7
                value = self.arm.u32(index)
                if wide: value |= self.arm.u32(index + 4) << 32
                index += 8 if variant == 2 or wide else 4
            if kind == 'F': value = struct.unpack('<d', struct.pack('<Q', value))[0] if wide else float_in(value)
            elif kind == 'D': value = struct.unpack('<d', struct.pack('<Q', value))[0]
            values.append(value)
        return values

    def invoke(self, variant):
        def call(env, obj, method, argument):
            class_name, name, signature = self.methods[method]
            args = self.arguments(signature, variant, argument)
            if self.trace:
                log.info('[jni] call %s %s %s %s', class_name, name, signature, args)
            result = self.service(class_name, name, signature, args)
            if signature.endswith(')J'):
                self.arm.uc.reg_write(UC_ARM_REG_R1, (int(result) >> 32) & 0xffffffff)
            return result
        return call

    def service(self, class_name, name, signature, args):
        if class_name == 'com/eruption/util/VideoAdapter':
            return self.media.video_service(name, args, self.arm)
        if class_name.endswith('/AudioPlayer') and name != 'getInstance':
            return self.media.audio_service(name, args, self.arm)
        if name == 'setViewMode':
            return 0  # Standard monoscopic display.
        if name == 'SetInputGrav':
            return 0  # Desktop input has no accelerometer.
        if name in ('createFile', 'deleteFile'):
            path = Path(self.arm.string(args[0])).resolve()
            if not path.is_relative_to(self.root / 'saves'):
                raise ValueError('Save path outside save directory')
            if name == 'createFile':
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch(exist_ok=True)
                return 1
            path.unlink(missing_ok=True)
            return 0
        if name == 'getDpyFormat':
            return 1  # Android PixelFormat.RGBA_8888
        if name == 'hasSystemFeature':
            return 0  # This desktop has no stereoscopic Android display.
        if name == 'getPackageManager':
            return self.object('android/content/pm/PackageManager')
        if name == 'getPackageName':
            return self.arm.cstring('jjp.co.capcom.android.googleplay.bio4')
        if name == 'getInstance':
            if class_name not in self.singletons: self.singletons[class_name]=self.object(class_name)
            return self.singletons[class_name]
        if name.lower() in ('getmilliseconds', 'getmillisecond', 'currenttimemillis'):
            return int((time.monotonic() - self.started) * 1000)
        if name in ('getWidth', 'getDisplayWidth', 'getScreenWidth'):
            return self.width
        if name in ('getHeight', 'getDisplayHeight', 'getScreenHeight'):
            return self.height
        if name in ('getdownloadDataPath', 'getDataPath'):
            return self.arm.cstring(str(self.root / 'data' / 'monhun') + '/')
        if name == 'getFilePath':
            return self.arm.cstring(str(self.root / 'saves') + '/')
        if name == 'calcInfo':
            filename = self.arm.string(args[0]).removesuffix('.png')
            self.current_asset = self.root / 'data' / 'monhun' / Path(filename).name
            log.debug('[asset] %s exists=%s', filename, self.current_asset.exists())
            return int(self.current_asset.is_file())
        if name == 'getPackagePath':
            return self.arm.cstring(str(self.current_asset))
        if name == 'getStartOffset':
            return 0
        if name == 'getLength':
            return self.current_asset.stat().st_size
        raise RuntimeError(f'Unimplemented Android service: {class_name}.{name}{signature}, args={args}')

    def native(self, name, *args):
        address, signature = self.natives[name]
        result = self.arm.call(address, self.env, self.activity, *args, operation=name)
        return result
