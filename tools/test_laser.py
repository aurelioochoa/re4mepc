"""Compare customized sights against the native draw in a private mission fixture.

User-imported game data is required. Endpoint visibility is injected only for
positive controls; game files and user saves are never changed.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import ImageChops
from unicorn import UC_HOOK_CODE
from re4pc.game import Game
from re4pc.graphics import SIGNATURES
from re4pc.paths import game_dir, isolated_game, test_output
from tools.benchmark import Replay


def check(game, replay, output):
    arm, graphics, sight = game.arm, game.graphics, game.graphics.laser
    gl = graphics.gl
    address = arm.symbols[sight.SYMBOL] & ~1
    laser = arm.u32(game.pc.player+4)
    phase = [None]
    observation = [None]
    fixture = {'endpoint': False, 'hidden': False, 'alpha': 1}
    results, originals, hooks = {}, {}, []

    def integer(parameter):
        value = C.c_int()
        gl.glGetIntegerv(parameter, C.byref(value))
        return value.value

    def floats(parameter, count):
        value = (C.c_float*count)()
        gl.glGetFloatv.argtypes = (C.c_uint, C.c_void_p)
        gl.glGetFloatv(parameter, value)
        return list(value)

    def pointer(parameter):
        value = C.c_void_p()
        gl.glGetPointerv.argtypes = (C.c_uint, C.c_void_p)
        gl.glGetPointerv(parameter, C.byref(value))
        return value.value

    def snapshot():
        gl.glIsEnabled.argtypes, gl.glIsEnabled.restype = (C.c_uint,), C.c_uint
        return {'model': floats(0x0ba6, 16), 'projection': floats(0x0ba7, 16),
                'texture_matrix': floats(0x0ba8, 16), 'color': floats(0x0b00, 4),
                'vertex': pointer(0x808e), 'uv': pointer(0x8092),
                'integers': [integer(p) for p in (0x84e0, 0x84e1, 0x0ba0, 0x8069,
                                                 0x0b72, 0x0b74, 0x0be0, 0x0be1)],
                'enabled': [gl.glIsEnabled(p) for p in (0x0b71, 0x0be2, 0x0bc0, 0x8074, 0x8076, 0x8078)]}

    def geometry(values):
        count = values[1] if len(values) == 4 else values[2]
        if len(values) == 4:
            fmt, size = {0x1401: ('B', 1), 0x1403: ('H', 2), 0x1405: ('I', 4)}[values[2]]
            indices = arm.read(values[3], count*size)
            vertices = max(struct.unpack('<'+fmt*count, indices))+1
        else:
            indices, vertices = b'', values[1]+count
        stride = integer(0x807c) or 12
        vertex = pointer(0x808e)
        data = b''.join(arm.read(vertex+i*stride, 12) for i in range(vertices))
        return hashlib.sha256(data+indices).hexdigest()

    def projected_width(state):
        # Native endpoint quad is one world unit wide and billboarded by the
        # engine. Observe its own camera matrix instead of assigning a host size.
        model, projection = state['model'], state['projection']
        w = sum(projection[i*4+3]*model[12+i] for i in range(4))
        return abs(projection[0]*model[0]/w)*graphics.width/2 if w > 0 else 0

    for name in ('glDrawArrays', 'glDrawElements'):
        location = arm.imports[name]
        originals[location] = arm.traps[location]
        native = getattr(gl, name)
        context = [None]

        def submit(*values, native=native, context=context):
            expected, record = context[0]
            actual = snapshot()
            assert geometry(values) == record['geometry'], 'Custom sight changed native vertices/indices'
            model = list(expected['model'])
            if phase[0] == 'dot' and sight.custom:
                model[:12] = [v*sight.scale for v in model[:12]]
            assert actual['model'] == model, 'Custom sight changed native positioning or size'
            assert actual['projection'] == expected['projection'], 'Custom sight changed the native projection'
            assert actual['vertex'] == expected['vertex']
            assert actual['integers'][4:] == expected['integers'][4:], 'Custom sight changed native depth/blending'
            assert actual['enabled'][:5] == expected['enabled'][:5], 'Custom sight changed native render tests'
            assert actual['color'][3] == expected['color'][3], 'Custom sight changed native alpha'
            assert abs(max(actual['color'][:3])-max(expected['color'][:3])) < 1e-6, 'Native fade lost'
            return native(*values)

        forward = graphics.forward(name, SIGNATURES[name], submit)

        def observe(*args, forward=forward, context=context, name=name):
            if observation[0] is None or phase[0] is None:
                return originals[arm.imports[name]][1](*args)
            values = arm.args(len(SIGNATURES[name]))
            if phase[0] == 'dot' and fixture['alpha'] != 1:
                color = floats(0x0b00, 4)
                gl.glColor4f(*color[:3], color[3]*fixture['alpha'])
            expected = snapshot()
            before = graphics.capture_image()
            record = {'phase': phase[0], 'geometry': geometry(values),
                      'width': projected_width(expected) if phase[0] == 'dot' else None}
            context[0] = (expected, record)
            result = forward(*args)
            assert snapshot() == expected, 'Custom sight leaked OpenGL state'
            after = graphics.capture_image()
            diff = ImageChops.difference(before, after)
            record['pixels'] = sum(max(pixel) > 2 for pixel in diff.getdata())
            record['bounds'] = diff.getbbox()
            record['energy'] = sum(sum(pixel) for pixel in diff.getdata())
            observation[0]['draws'].append(record)
            if phase[0] == 'dot':
                after.save(output/(observation[0]['label']+'.png'))
            return result or 0
        arm.traps[location] = (name, observe)

    def begin(uc, address, size, context):
        phase[0] = 'beam'
        if fixture['hidden']:
            arm.write(laser+0x124, struct.pack('<f', 0))

    def endpoint(uc, address, size, context):
        phase[0] = 'dot'
        if fixture['endpoint']:
            arm.write(laser, b'\x01')
            point = struct.unpack('<3f', arm.read(laser+0x118, 12))
            arm.write(laser+0x98, struct.pack('<3f', *(v/256 for v in point)))

    def end(uc, address, size, context):
        phase[0] = None

    for offset, callback in ((0, begin), (0x40, endpoint), (0x98, end)):
        hooks.append(arm.uc.hook_add(UC_HOOK_CODE, callback, begin=address+offset, end=address+offset))
    arm.uc.ctl_remove_cache(address, address+160)

    def measure(label, shape='original', color='#ff0000', scale=1, endpoint=True, hidden=False, alpha=1):
        fixture.update(endpoint=endpoint, hidden=hidden, alpha=alpha)
        sight.configure({'laser_shape': shape, 'laser_color': color, 'laser_size': scale})
        record = {'label': label, 'draws': []}
        observation[0] = record
        try:
            replay.advance()
        finally:
            observation[0] = None
        assert gl.glGetError() == 0, label
        assert sight.stage is None and phase[0] is None
        results[label] = record
        print('LASER_CASE', label, json.dumps(record), flush=True)
        return [draw for draw in record['draws'] if draw['phase'] == 'dot']

    try:
        game.event(('mouse_button', True, 3))
        replay.advance(45)
        native = measure('native-default')
        assert len(native) == 1 and native[0]['pixels'] > 0
        native_geometry = native[0]['geometry']
        natural = measure('native-visibility', endpoint=False)
        for shape in ('circle', 'predator', 'black_matter'):
            dots = measure(shape, shape, '#00ffcc')
            assert len(dots) == 1 and dots[0]['pixels'] > 0, (shape, dots)
            assert dots[0]['geometry'] == native_geometry
            assert abs(dots[0]['width']-native[0]['width']) < .01
            hidden = measure(shape+'-hidden', shape, '#00ffcc', hidden=True)
            assert not hidden and not results[shape+'-hidden']['draws']
            unforced = measure(shape+'-visibility', shape, '#00ffcc', endpoint=False)
            assert len(unforced) == len(natural), 'Custom pointer changed native visibility'
            transparent = measure(shape+'-transparent', shape, '#00ffcc', alpha=0)
            assert len(transparent) == 1 and transparent[0]['pixels'] == 0
        before = measure('predator-before-aim', 'predator', '#00ffcc')[0]
        game.event(('mouse_delta', 150, -60))
        replay.advance(8)
        moved = measure('predator-after-aim', 'predator', '#00ffcc')[0]
        assert abs(moved['width']-before['width']) > 1, 'Native aim distance did not affect the marker'
        native_moved = measure('native-after-aim')[0]
        assert abs(moved['width']-native_moved['width']) < 1
        measure('predator-size-control', 'predator', '#00ffcc', scale=2)
        return results
    finally:
        for location, original in originals.items():
            arm.traps[location] = original
        for hook in hooks:
            arm.uc.hook_del(hook)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=game_dir())
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = test_output('laser', args.output)
    checkout = Path(__file__).resolve().parents[1]
    if output.resolve() == checkout or checkout in output.resolve().parents:
        parser.error('Keep game fixtures and captures outside the checkout')
    game = Game(isolated_game(args.game, output), hidden=True, skip_videos=True, diagnostics=False)
    replay = Replay(game)
    try:
        replay.advance(200)
        replay.village()
        replay.close()
        results = check(game, replay, output)
        (output/'results.json').write_text(json.dumps(results, indent=2)+'\n')
        print('LASER_REGRESSION_PASS', output/'results.json', flush=True)
    finally:
        replay.close()
        game.close()


if __name__ == '__main__':
    main()
