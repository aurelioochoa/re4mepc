"""Final presentation filters from the logical surface texture to the window.

Programs belong to the context that first presents with them. The engine
never uses programs, so presentation unbinds its program after each pass.
"""
import ctypes as C

VERTEX = b'''#version 120
varying vec2 uv;
void main() { uv = gl_MultiTexCoord0.xy; gl_Position = gl_Vertex; }
'''

HEADER = b'''#version 120
uniform sampler2D source;
uniform vec2 source_size;
uniform vec2 output_size;
uniform vec2 logical_size;
varying vec2 uv;
vec3 tap(vec2 offset) { return texture2D(source, uv + offset / source_size).rgb; }
'''

FRAGMENTS = {
    # AMD FidelityFX CAS-style contrast-adaptive sharpening.
    'sharpen': b'''
void main() {
    vec3 a = tap(vec2(0.0, -1.0)), b = tap(vec2(-1.0, 0.0)), c = tap(vec2(0.0));
    vec3 d = tap(vec2(1.0, 0.0)), e = tap(vec2(0.0, 1.0));
    vec3 low = min(min(min(a, b), min(d, e)), c);
    vec3 high = max(max(max(a, b), max(d, e)), c);
    vec3 amount = sqrt(clamp(min(low, 1.0 - high) / max(high, vec3(1e-4)), 0.0, 1.0));
    vec3 weight = amount * -0.2;
    gl_FragColor = vec4(clamp((c + (a + b + d + e) * weight) / (1.0 + 4.0 * weight), 0.0, 1.0), 1.0);
}
''',
    # FXAA 3.x console-quality edge search on the supersampled surface.
    'fxaa': b'''
void main() {
    vec3 luma = vec3(0.299, 0.587, 0.114);
    vec3 m = tap(vec2(0.0));
    float nw = dot(tap(vec2(-1.0, -1.0)), luma), ne = dot(tap(vec2(1.0, -1.0)), luma);
    float sw = dot(tap(vec2(-1.0, 1.0)), luma), se = dot(tap(vec2(1.0, 1.0)), luma);
    float lm = dot(m, luma);
    float low = min(lm, min(min(nw, ne), min(sw, se)));
    float high = max(lm, max(max(nw, ne), max(sw, se)));
    vec2 direction = vec2(-((nw + ne) - (sw + se)), (nw + sw) - (ne + se));
    float reduce = max((nw + ne + sw + se) * 0.03125, 1.0 / 128.0);
    float scale = 1.0 / (min(abs(direction.x), abs(direction.y)) + reduce);
    direction = clamp(direction * scale, vec2(-8.0), vec2(8.0));
    vec3 near = 0.5 * (tap(direction * (1.0 / 3.0 - 0.5)) + tap(direction * (2.0 / 3.0 - 0.5)));
    vec3 far = near * 0.5 + 0.25 * (tap(direction * -0.5) + tap(direction * 0.5));
    float lf = dot(far, luma);
    gl_FragColor = vec4((lf < low || lf > high) ? near : far, 1.0);
}
''',
    # Sharp bilinear: integer nearest prescale, then bilinear only at edges.
    'pixel': b'''
void main() {
    vec2 texel = uv * source_size;
    vec2 scale = max(floor(output_size / source_size), vec2(1.0));
    vec2 offset = fract(texel) - 0.5;
    vec2 range = 0.5 - 0.5 / scale;
    vec2 blend = (offset - clamp(offset, -range, range)) * scale + 0.5;
    gl_FragColor = vec4(texture2D(source, (floor(texel) + blend) / source_size).rgb, 1.0);
}
''',
    # Scanlines on original 480-line rows with a soft aperture-grille mask.
    'crt': b'''
void main() {
    vec3 color = texture2D(source, uv).rgb;
    // Beam peaks a quarter line in, so even a 2x output alternates bright/dark.
    float row = fract(uv.y * logical_size.y);
    float beam = mix(0.70, 1.0, 0.5 + 0.5 * cos(6.2831853 * (row - 0.25)));
    float column = mod(gl_FragCoord.x, 3.0);
    vec3 mask = vec3(column < 1.0 ? 1.06 : 0.94, column >= 1.0 && column < 2.0 ? 1.06 : 0.94, column >= 2.0 ? 1.06 : 0.94);
    gl_FragColor = vec4(clamp(color * beam * mask * 1.12, 0.0, 1.0), 1.0);
}
''',
}

FUNCTIONS = {
    'glCreateShader': (C.c_uint, (C.c_uint,)),
    'glShaderSource': (None, (C.c_uint, C.c_int, C.POINTER(C.c_char_p), C.c_void_p)),
    'glCompileShader': (None, (C.c_uint,)),
    'glGetShaderiv': (None, (C.c_uint, C.c_uint, C.POINTER(C.c_int))),
    'glGetShaderInfoLog': (None, (C.c_uint, C.c_int, C.c_void_p, C.c_char_p)),
    'glDeleteShader': (None, (C.c_uint,)),
    'glCreateProgram': (C.c_uint, ()),
    'glAttachShader': (None, (C.c_uint, C.c_uint)),
    'glLinkProgram': (None, (C.c_uint,)),
    'glGetProgramiv': (None, (C.c_uint, C.c_uint, C.POINTER(C.c_int))),
    'glGetProgramInfoLog': (None, (C.c_uint, C.c_int, C.c_void_p, C.c_char_p)),
    'glDeleteProgram': (None, (C.c_uint,)),
    'glUseProgram': (None, (C.c_uint,)),
    'glGetUniformLocation': (C.c_int, (C.c_uint, C.c_char_p)),
    'glUniform1i': (None, (C.c_int, C.c_int)),
    'glUniform2f': (None, (C.c_int, C.c_float, C.c_float)),
    'glTexCoord2f': (None, (C.c_float, C.c_float)),
    'glVertex2f': (None, (C.c_float, C.c_float)),
    'glBegin': (None, (C.c_uint,)),
    'glEnd': (None, ()),
}


class PostProcess:
    def __init__(self, gl, name):
        if name not in FRAGMENTS:
            raise ValueError('Unknown display filter: ' + str(name))
        self.gl, self.name, self.program = gl, name, 0
        for function, (result, args) in FUNCTIONS.items():
            target = getattr(gl, function)
            target.restype, target.argtypes = result, args

    def _shader(self, kind, source):
        gl = self.gl
        shader = gl.glCreateShader(kind)
        text = C.c_char_p(source)
        gl.glShaderSource(shader, 1, C.byref(text), None)
        gl.glCompileShader(shader)
        status = C.c_int()
        gl.glGetShaderiv(shader, 0x8b81, C.byref(status))  # COMPILE_STATUS
        if not status.value:
            log = C.create_string_buffer(4096)
            gl.glGetShaderInfoLog(shader, len(log), None, log)
            gl.glDeleteShader(shader)
            raise RuntimeError(f'{self.name} shader failed: {log.value.decode(errors="replace")}')
        return shader

    def compile(self):
        gl = self.gl
        shaders = (self._shader(0x8b31, VERTEX), self._shader(0x8b30, HEADER + FRAGMENTS[self.name]))
        program = gl.glCreateProgram()
        for shader in shaders:
            gl.glAttachShader(program, shader)
        gl.glLinkProgram(program)
        for shader in shaders:
            gl.glDeleteShader(shader)
        status = C.c_int()
        gl.glGetProgramiv(program, 0x8b82, C.byref(status))  # LINK_STATUS
        if not status.value:
            log = C.create_string_buffer(4096)
            gl.glGetProgramInfoLog(program, len(log), None, log)
            gl.glDeleteProgram(program)
            raise RuntimeError(f'{self.name} program failed: {log.value.decode(errors="replace")}')
        self.program = program
        self.uniforms = {name: gl.glGetUniformLocation(program, name.encode())
                         for name in ('source', 'source_size', 'output_size', 'logical_size')}

    def draw(self, texture, source_size, output_rect, logical_size):
        """Draw `texture` into the bound draw framebuffer's `output_rect`.

        The caller saves and restores fixed-function state around this pass.
        """
        gl = self.gl
        if not self.program:
            self.compile()
        x, y, w, h = output_rect
        gl.glViewport(x, y, w, h)
        for cap in (0x0b71, 0x0bc0, 0x0be2, 0x0b44, 0x0b60, 0x0b50, 0x0b90, 0x0c11):
            gl.glDisable(cap)  # depth, alpha, blend, cull, fog, lighting, stencil, scissor
        gl.glActiveTexture(0x84c0)
        gl.glBindTexture(0x0de1, texture)
        gl.glUseProgram(self.program)
        u = self.uniforms
        gl.glUniform1i(u['source'], 0)
        gl.glUniform2f(u['source_size'], float(source_size[0]), float(source_size[1]))
        gl.glUniform2f(u['output_size'], float(w), float(h))
        gl.glUniform2f(u['logical_size'], float(logical_size[0]), float(logical_size[1]))
        gl.glBegin(0x0007)  # GL_QUADS; texture row 0 is the bottom of the image
        for s, t in ((0, 0), (1, 0), (1, 1), (0, 1)):
            gl.glTexCoord2f(float(s), float(t))
            gl.glVertex2f(s * 2.0 - 1.0, t * 2.0 - 1.0)
        gl.glEnd()
        gl.glUseProgram(0)

    def close(self):
        if self.program:
            self.gl.glDeleteProgram(self.program)
            self.program = 0
