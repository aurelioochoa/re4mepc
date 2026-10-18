"""Procedural sight artwork and a draw-scoped native laser customization bridge.

No game textures or binaries are modified. Native collision, billboard matrices
and visibility decide where and whether the sight renders.
"""
import colorsys
import ctypes as C
import math

SHAPE_LABELS = {'original': 'Original', 'circle': 'Circle', 'predator': 'Predator', 'black_matter': 'Black Matter'}


def sight_image(shape, color, size=96, phase=0):
    """Shared launcher/runtime artwork; phase is a looping fraction of a turn."""
    from PIL import Image, ImageDraw
    rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
    image = Image.new('RGBA', (size, size))
    draw = ImageDraw.Draw(image)
    c = (size-1)/2
    if shape in ('original', 'circle', 'predator'):
        centers = [(c, c)] if shape != 'predator' else [(c, size*.25), (size*.28, size*.64), (size*.72, size*.64)]
        radius = size*({'original': .06, 'circle': .38, 'predator': .105}[shape])
        for x, y in centers:
            for step in range(12, 0, -1):
                r = radius*(1+step*(.02 if shape == 'circle' else .1))
                draw.ellipse((x-r, y-r, x+r, y+r), fill=(*rgb, round(80*(1-step/13))))
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(*rgb, 255))
            r = radius*.35
            draw.ellipse((x-r, y-r, x+r, y+r), fill=tuple(round(v*.35+255*.65) for v in rgb)+(255,))
    elif shape == 'black_matter':
        # A flowing nebula with electric veins, a dark core and the chosen
        # accent color. Trigonometric fields loop without random frame flicker.
        pixels = image.load()
        for y in range(size):
            for x in range(size):
                nx, ny = (x-c)/(size*.43), (y-c)/(size*.43)
                radius = math.hypot(nx, ny)
                if radius > 1:
                    continue
                angle = math.atan2(ny, nx)
                flow = math.sin(13*radius-3*angle+math.tau*phase)
                veins = max(0, math.sin(23*nx+9*math.sin(5*ny+math.tau*phase)))**12
                hue = (.73+.13*flow+.06*math.sin(4*angle-math.tau*phase)) % 1
                nebula = colorsys.hsv_to_rgb(hue, .82, .48+.45*veins)
                accent = veins*.55
                values = tuple(round(v*255*(1-accent)+a*accent) for v, a in zip(nebula, rgb))
                if radius < .24:
                    values = (9, 3, 18)
                alpha = round(255*min(1, (1-radius)*12))
                pixels[x, y] = (*values, alpha)
    else:
        raise ValueError('Unknown sight shape: '+str(shape))
    return image


class LaserSight:
    SYMBOL = '_ZN20GM_CtrlSub_LaserSite4DrawEP11GM_CtrlMain'

    def __init__(self, graphics, settings):
        self.graphics, self.arm, self.gl = graphics, graphics.arm, graphics.gl
        self.stage = None
        self.textures = []
        self.configure(settings)

    def configure(self, settings):
        self.close()
        self.shape = settings.get('laser_shape', 'original')
        self.color = settings.get('laser_color', '#ff0000')
        self.scale = settings.get('laser_size', 1.0)
        self.rgb = tuple(int(self.color[i:i+2], 16)/255 for i in (1, 3, 5))
        self.custom = (self.shape, self.color, self.scale) != ('original', '#ff0000', 1.0)
        self.stage = None

    def install(self):
        from unicorn import UC_HOOK_CODE
        # These boundaries were checked against REA/Ghidra and Capstone for
        # the hash-validated engine: beam call, billboard phase, common exit.
        start = self.arm.symbols[self.SYMBOL] & ~1
        if self.arm.symbol_sizes[self.SYMBOL] != 160:
            raise RuntimeError('Unsupported native laser draw layout')
        for offset, callback in ((0, self._begin), (0x40, self._dot), (0x98, self._end)):
            self.arm.uc.hook_add(UC_HOOK_CODE, callback, begin=start+offset, end=start+offset)

    def _begin(self, uc, address, size, context):
        self.stage = 'beam' if self.custom else None

    def _dot(self, uc, address, size, context):
        if self.stage:
            self.stage = 'dot'

    def _end(self, uc, address, size, context):
        self.stage = None

    def _native_color(self, tint):
        # The supported native beam and endpoint disable color arrays and use
        # current color. Preserve both its animated intensity and its alpha.
        current = (C.c_float*4)()
        self.gl.glGetFloatv.argtypes = (C.c_uint, C.c_void_p)
        self.gl.glGetFloatv(0x0b00, current)
        intensity = max(current[:3])
        self.gl.glColor4f(*(value*intensity for value in tint), current[3])

    def draw(self, function, values):
        """Reskin native submissions without introducing additional sight draws."""
        if (values[1] if len(values) == 4 else values[2]) == 0:
            return function(*values)
        if self.stage == 'dot':
            return self._draw_marker(function, values)
        if self.color == '#ff0000':
            return function(*values)
        gl = self.gl
        gl.glPushAttrib.argtypes = (C.c_uint,)
        gl.glPushAttrib(0xfffff)
        try:
            self._native_color(self.rgb)
            return function(*values)
        finally:
            gl.glPopAttrib()

    def _texture(self):
        if not self.textures:
            gl = self.gl
            frames = 20 if self.shape == 'black_matter' else 1
            ids = (C.c_uint*frames)()
            gl.glGenTextures(frames, ids)
            self.textures = list(ids)
            gl.glPixelStorei(0x0cf5, 1)
            for parameter in (0x0cf2, 0x0cf3, 0x0cf4):
                gl.glPixelStorei(parameter, 0)
            for frame, texture in enumerate(self.textures):
                image = sight_image(self.shape, self.color, phase=frame/frames)
                data = C.create_string_buffer(image.tobytes())
                gl.glBindTexture(0x0de1, texture)
                gl.glTexImage2D(0x0de1, 0, 0x1908, image.width, image.height, 0, 0x1908, 0x1401, C.addressof(data))
                for parameter, value in ((0x2801, 0x2601), (0x2800, 0x2601), (0x2802, 0x812f), (0x2803, 0x812f)):
                    gl.glTexParameterf(0x0de1, parameter, value)
        import time
        return self.textures[int(time.monotonic()*10) % len(self.textures)]

    def _marker_uv(self, values):
        """Map procedural artwork to the native endpoint's existing quad."""
        import struct
        gl = self.gl
        if len(values) == 4:
            count, kind, pointer = values[1:]
            formats = {0x1401: ('B', 1), 0x1403: ('H', 2), 0x1405: ('I', 4)}
            fmt, size = formats[kind]
            indices = struct.unpack('<'+fmt*count, self.arm.read(pointer, count*size))
            vertices = max(indices)+1
        else:
            vertices = values[1]+values[2]
        pointer = C.c_void_p()
        gl.glGetPointerv.argtypes = (C.c_uint, C.c_void_p)
        gl.glGetPointerv(0x808e, C.byref(pointer))
        layout = []
        for parameter in (0x807a, 0x807b, 0x807c):
            value = C.c_int()
            gl.glGetIntegerv(parameter, C.byref(value))
            layout.append(value.value)
        components, kind, stride = layout
        if components != 3 or kind != 0x1406:
            raise RuntimeError('Unsupported native sight vertex layout')
        stride = stride or 12
        self.arm.check(pointer.value, (vertices-1)*stride+12)
        points = [struct.unpack('<3f', self.arm.read(pointer.value+index*stride, 12))
                  for index in range(vertices)]
        left, right = min(v[0] for v in points), max(v[0] for v in points)
        bottom, top = min(v[1] for v in points), max(v[1] for v in points)
        uv = (C.c_float*(vertices*2))()
        for index, point in enumerate(points):
            uv[index*2] = (point[0]-left)/(right-left) if right != left else .5
            uv[index*2+1] = (top-point[1])/(top-bottom) if top != bottom else .5
        return uv

    def _draw_marker(self, function, values):
        gl = self.gl
        gl.glPushAttrib.argtypes = (C.c_uint,)
        gl.glPushClientAttrib.argtypes = (C.c_uint,)
        gl.glPushAttrib(0xfffff)
        gl.glPushClientAttrib(3)  # pixel-store and vertex-array state
        pushed = []
        mode = C.c_int()
        gl.glGetIntegerv(0x0ba0, C.byref(mode))
        try:
            # Original uses the engine's own untextured endpoint. Shapes replace
            # only its artwork; vertices, indices and all render tests stay native.
            if self.shape == 'original':
                self._native_color(self.rgb)
            else:
                uv = self._marker_uv(values)
                gl.glActiveTexture(0x84c0)
                gl.glClientActiveTexture(0x84c0)
                gl.glMatrixMode(0x1702)
                gl.glPushMatrix()
                pushed.append(0x1702)
                gl.glLoadIdentity()
                gl.glEnable(0x0de1)
                gl.glBindTexture(0x0de1, self._texture())
                gl.glTexEnvf(0x2300, 0x2200, 0x2100)  # MODULATE native fade/alpha
                gl.glTexCoordPointer(2, 0x1406, 0, C.addressof(uv))
                gl.glEnableClientState(0x8078)
                self._native_color((1, 1, 1))
            if self.scale != 1:
                gl.glMatrixMode(0x1700)
                gl.glPushMatrix()
                pushed.append(0x1700)
                gl.glScalef.argtypes = (C.c_float,)*3
                gl.glScalef(self.scale, self.scale, self.scale)
            gl.glMatrixMode(mode.value)
            return function(*values)
        finally:
            for matrix in reversed(pushed):
                gl.glMatrixMode(matrix)
                gl.glPopMatrix()
            gl.glPopClientAttrib()
            gl.glPopAttrib()

    def close(self):
        if self.textures:
            ids = (C.c_uint*len(self.textures))(*self.textures)
            self.gl.glDeleteTextures(len(ids), ids)
            self.textures = []
