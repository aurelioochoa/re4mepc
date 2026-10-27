"""Host display quality: render scale, MSAA, texture filtering and widescreen.

The engine always sees an 800x480 surface. Supersampling multiplies the host
framebuffer; widescreen widens perspective projections into side margins
while orthographic HUD and menu layers keep the original centered 5:3 area.
"""
import ctypes as C
from .paths import native_library

RENDER_SCALES = (1, 2, 3, 4)
MSAA_SAMPLES = (0, 2, 4, 8)
TEXTURE_FILTERS = ('original', 'trilinear', 'anisotropic')
DISPLAY_FILTERS = ('bilinear', 'sharpen', 'fxaa', 'pixel', 'crt')
ASPECT_RATIOS = {'original': None, '16:9': (16, 9), '21:9': (21, 9)}
MAX_ANISOTROPY = 16.0


def surface_width(aspect, logical=(800, 480)):
    """Logical surface width including equal widescreen margins."""
    ratio = ASPECT_RATIOS[aspect]
    if not ratio:
        return logical[0]
    width = round(logical[1] * ratio[0] / ratio[1])
    return max(logical[0], width + (width - logical[0]) % 2)


class Display:
    REPLACEMENTS = {'glViewport': 're4_display_viewport', 'glScissor': 're4_display_scissor',
                    'glMatrixMode': 're4_display_matrix_mode', 'glLoadMatrixf': 're4_display_load_matrix',
                    'glTexParameterf': 're4_display_tex_parameter'}

    def __init__(self, settings=None, logical=(800, 480)):
        settings = settings or {}
        self.scale = settings.get('render_scale', 1)
        self.samples = settings.get('msaa', 0)
        self.texture_filtering = settings.get('texture_filtering', 'original')
        self.filter = settings.get('display_filter', 'bilinear')
        self.aspect_ratio = settings.get('aspect_ratio', 'original')
        if (self.scale not in RENDER_SCALES or self.samples not in MSAA_SAMPLES or
                self.texture_filtering not in TEXTURE_FILTERS or self.filter not in DISPLAY_FILTERS or
                self.aspect_ratio not in ASPECT_RATIOS):
            raise ValueError('Unsupported display quality settings')
        self.logical = logical
        self.surface_width = surface_width(self.aspect_ratio, logical)
        self.margin = (self.surface_width - logical[0]) // 2
        self.lib = C.CDLL(str(native_library('libre4fast.so')))
        int4 = (C.c_int,)*4
        for name, args in (('re4_display_configure', (C.c_int,)*5 + (C.c_float,)),
                           ('re4_display_viewport', int4), ('re4_display_scissor', int4),
                           ('re4_display_matrix_mode', (C.c_uint,)),
                           ('re4_display_load_matrix', (C.c_void_p,)),
                           ('re4_display_tex_parameter', (C.c_uint, C.c_uint, C.c_float)),
                           ('re4_display_map', (C.c_int, C.POINTER(C.c_int), C.POINTER(C.c_int))),
                           ('re4_display_projection', (C.POINTER(C.c_float), C.POINTER(C.c_float))),
                           ('re4_display_cover', (C.c_int, C.c_int, C.c_uint, C.c_void_p)),
                           ('re4_display_cover_end', ())):
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, C.c_int if name in ('re4_display_projection', 're4_display_cover') else None
        self.anisotropy = 1.0
        self.configure()

    @property
    def mipmaps(self):
        return self.texture_filtering != 'original'

    @property
    def identity(self):
        return self.scale == 1 and not self.samples and not self.margin

    def configure(self, max_anisotropy=MAX_ANISOTROPY):
        """Reset the engine context's mapping; call once per engine context."""
        self.anisotropy = min(MAX_ANISOTROPY, max(1.0, max_anisotropy))
        self.lib.re4_display_configure(self.scale, self.logical[0], self.logical[1], self.surface_width,
                                       TEXTURE_FILTERS.index(self.texture_filtering), self.anisotropy)

    def replacement(self, name):
        """Display-aware function with the same GL import signature, if any."""
        symbol = self.REPLACEMENTS.get(name)
        return getattr(self.lib, symbol) if symbol else None

    def cover(self, name, values):
        """Stretch an untextured full-screen orthographic draw over widescreen margins."""
        if not self.margin:
            return False
        if name == 'glDrawElements':
            return bool(self.lib.re4_display_cover(0, values[1], values[2], values[3]))
        return bool(self.lib.re4_display_cover(values[1], values[2], 0, None))

    def cover_end(self):
        self.lib.re4_display_cover_end()

    def viewport(self, x, y, w, h):
        self.lib.re4_display_viewport(x, y, w, h)

    def map(self, rect, wide=False):
        """Host framebuffer rectangle for a logical engine rectangle."""
        source, result = (C.c_int*4)(*rect), (C.c_int*4)()
        self.lib.re4_display_map(int(wide), source, result)
        return tuple(result)

    def projection(self, matrix):
        source, result = (C.c_float*16)(*matrix), (C.c_float*16)()
        perspective = self.lib.re4_display_projection(source, result)
        return bool(perspective), tuple(result)

    def describe(self):
        return {'render_scale': self.scale, 'msaa': self.samples, 'texture_filtering': self.texture_filtering,
                'anisotropy': self.anisotropy if self.texture_filtering == 'anisotropic' else 1.0,
                'display_filter': self.filter, 'aspect_ratio': self.aspect_ratio,
                'surface_size': [self.surface_width, self.logical[1]]}
