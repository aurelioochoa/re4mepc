"""Exercise native laser visibility and buffered fire in a private game fixture.

Uses the established synthetic mission-2 replay. No campaign completion or
physical controller qualification is implied. All engine artifacts stay outside
the checkout; the user's installation and saves are only read.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import ImageChops
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0
from re4pc.game import Game
from re4pc.paths import game_dir, isolated_game, test_output
from tools.benchmark import Replay, source_identity


def check(game, replay, output):
    arm, pc = game.arm, game.pc
    report = {'source': source_identity(), 'cases': {}}
    hooks = []
    observe = [None]
    before = [None]
    pixels = {}
    laser = arm.u32(pc.player+4)
    params = arm.call('_ZN12GM_CtrlParam8Get_InstEv')
    difficulty = '_ZN12GM_CtrlParam12Get_DiffModeEv'
    query = '_ZN12GM_CtrlParam28Get_Diff_LaserSiteNonDrawFlgEv'
    visibility = '_ZN20GM_CtrlSub_LaserSite16Set_LaserDrawFlgEb'

    def state():
        return struct.unpack('<h', arm.read(pc.player+0x36, 2))[0]

    def ammo():
        return arm.call('_ZN16Bio4_AttacheCase16GetLoadBulletNumEl', params,
                        arm.read(pc.player+0x5e, 1)[0])

    def event(*value):
        game.event(value)

    def click():
        # Down/up in one poll must survive both desktop and weapon sampling.
        event('touch', True, 400, 240)
        event('touch', False, 400, 240)

    def tap(key):
        event('key', True, ord(key))
        event('key', False, ord(key))

    def enter(uc, address, size, context):
        if observe[0] is not None:
            before[0] = game.graphics.capture_image()

    def leave(uc, address, size, context):
        if observe[0] is not None and before[0] is not None:
            after = game.graphics.capture_image()
            diff = ImageChops.difference(before[0], after)
            changed = sum(max(pixel) > 4 for pixel in diff.getdata())
            pixels[observe[0]] = changed
            after.save(output/(observe[0]+'.png'))
            observe[0] = None
            before[0] = None

    def measure(label):
        observe[0] = label
        replay.advance()
        assert observe[0] is None, ('Laser draw was not observed', label)
        return pixels[label]

    def record(label, value):
        report['cases'][label] = value
        print('COMBAT_PASS', label, json.dumps(value), flush=True)

    symbol = '_ZN20GM_CtrlSub_LaserSite4DrawEP11GM_CtrlMain'
    address = arm.symbols[symbol] & ~1
    end = address+arm.symbol_sizes[symbol]-8  # Thumb pop {r4,pc}
    hooks.append(arm.uc.hook_add(UC_HOOK_CODE, enter, begin=address, end=address))
    hooks.append(arm.uc.hook_add(UC_HOOK_CODE, leave, begin=end, end=end))
    # Hooks added after mission entry must invalidate already translated code.
    arm.uc.ctl_remove_cache(address, address+arm.symbol_sizes[symbol])
    try:
        replay.advance(30)
        assert arm.call(difficulty, params) == 4, 'Fixture did not enter Extreme difficulty'
        event('mouse_button', True, 3)
        replay.advance(30)
        assert state() == 2 and pc.last_sample['aiming']
        # Extreme suppresses the sight in every input mode, as on mobile.
        # Request the draw explicitly so only the difficulty flag can hide
        # it, for the original and a custom sight alike.
        assert arm.call(query, params) == 1
        sight = game.graphics.laser
        hidden = {}
        for shape, color in (('original', '#ff0000'), ('predator', '#00ffcc')):
            sight.configure({'laser_shape': shape, 'laser_color': color, 'laser_size': 1.0})
            arm.call(visibility, laser, 1)
            hidden[shape] = measure('extreme-hidden-'+shape)
            assert hidden[shape] == 0, ('Extreme laser drew pixels', shape, hidden[shape])
        sight.configure(game.settings)
        # Fixture only: the angle checks below need a drawn sight, so report
        # this mission as one whose difficulty shows it.
        query_start = arm.symbols[query] & ~1
        query_end = query_start+arm.symbol_sizes[query]-4
        hooks.append(arm.uc.hook_add(UC_HOOK_CODE, lambda uc, *rest: uc.reg_write(UC_ARM_REG_R0, 0),
                                     begin=query_end, end=query_end))
        arm.uc.ctl_remove_cache(query_start, query_start+arm.symbol_sizes[query])
        assert arm.call(query, params) == 0
        arm.call(visibility, laser, 1)
        visible = measure('fixture-visible')
        assert visible >= 20, ('Laser positive control is not visible', visible)
        assert arm.call(difficulty, params) == 4
        record('extreme_laser', {'hidden_pixels': hidden, 'fixture_pixels': visible,
                                'difficulty': 4})

        for label, dx, dy in (('up', 0, -100), ('down', 0, 200),
                               ('level', 0, -100), ('left', 200, 0),
                               ('right', -400, 0), ('return', 200, 0)):
            event('mouse_delta', dx, dy)
            replay.advance(8)
            assert measure('laser-'+label) >= 8, ('Laser disappeared', label, pixels)
        record('aim_angles', pixels.copy())

        event('mouse_button', False, 3)
        replay.advance(45)
        assert state() == 0
        bullets = ammo()
        event('mouse_button', True, 3)
        replay.advance()
        assert state() == 1
        click()
        replay.advance(30)
        assert ammo() == bullets-1, ('Startup click lost or duplicated', bullets, ammo())
        record('startup_click', {'before': bullets, 'after': ammo()})

        bullets = ammo()
        click()
        # Queue another click during the actual native shot lifecycle.
        for _ in range(8):
            replay.advance()
            if state() == 6 and ammo() < bullets:
                break
        assert state() == 6 and ammo() == bullets-1
        click()
        replay.advance(45)
        assert ammo() == bullets-2, ('Recoil click lost or duplicated', bullets, ammo())
        record('recoil_click', {'before': bullets, 'after': ammo()})

        event('mouse_button', False, 3)
        replay.advance(45)
        bullets = ammo()
        event('key', True, ord('x'))
        replay.advance()
        tap('z')
        replay.advance(30)
        assert ammo() == bullets-1, ('Keyboard startup click failed', bullets, ammo())
        tap('r')
        replay.advance(90)
        assert ammo() > bullets-1
        record('keyboard_and_reload', {'before': bullets, 'reloaded': ammo()})

        # A pending click must be discarded before holstering or focus loss.
        event('key', False, ord('x'))
        replay.advance(45)
        for label, cancel in (('aim_release', ('mouse_button', False, 3)),
                               ('focus_loss', ('focus_lost',))):
            bullets = ammo()
            event('mouse_button', True, 3)
            replay.advance()
            click()
            replay.advance()
            event(*cancel)
            replay.advance(45)
            assert ammo() == bullets, (label, 'Unexpected delayed shot', bullets, ammo())
            assert not pc.last_sample['aiming']
            record(label, {'ammunition': ammo(), 'aiming': False})

        # Double taps reuse the touch pad's flick: a sidestep while
        # aiming, then aim again; down while moving plays the quick turn.
        def pose():
            body = arm.u32(arm.u32(pc.player)+0x120)
            return (struct.unpack('<fff', arm.read(body+0x34, 12)),
                    struct.unpack('<f', arm.read(body+0xa4, 4))[0])

        def double_tap(key, frames=45, between=None):
            start = pose()
            tap(key)
            replay.advance(2)
            tap(key)
            seen = set()
            for frame in range(frames):
                replay.advance()
                seen.add((state(), struct.unpack('<h', arm.read(pc.player+0x64, 2))[0]))
                if between and frame == 3: between()
            end = pose()
            moved = sum((a-b)**2 for a, b in zip(start[0], end[0]))**0.5
            turned = abs((end[1]-start[1]+32768) % 65536-32768)
            return seen, round(moved, 3), round(turned)

        # The focus-loss case released the mouse; this click only recaptures.
        click()
        replay.advance(45)
        event('mouse_button', True, 3)
        replay.advance(45)
        steps = {}
        for key in 'wasd':
            assert state() == 2, ('Not aiming before sidestep', key, state())
            seen, moved, _ = double_tap(key)
            assert (33, 1) in seen and state() == 2, ('Sidestep failed', key, seen, state())
            assert moved > 0, ('Sidestep did not move', key)
            steps[key] = moved
        record('aim_sidesteps', steps)
        seen, _, _ = double_tap('a', between=lambda: event('mouse_button', False, 3))
        replay.advance(45)
        assert (33, 1) in seen and state() == 0 and not pc.last_sample['aiming'], (
            'Aim released during sidestep stayed raised', seen, state())
        record('aim_release_during_sidestep', {'state': state()})
        replay.advance(10)
        seen, _, turned = double_tap('s')
        assert (33, 0) in seen and state() == 0, ('Quick turn failed', seen, state())
        assert abs(turned-32768) < 4096, ('Quick turn did not face backward', turned)
        record('quick_turn', {'turned_degrees': round(turned*360/65536)})
        assert not game.graphics.debug_messages, sorted(game.graphics.debug_messages)
        return report
    finally:
        for hook in hooks:
            arm.uc.hook_del(hook)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=game_dir())
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = test_output('combat', args.output)
    checkout = Path(__file__).resolve().parents[1]
    if output.resolve() == checkout or checkout in output.resolve().parents:
        parser.error('Keep game fixtures and captures outside the checkout')
    game = Game(isolated_game(args.game, output), hidden=True, skip_videos=True,
                diagnostics=False)
    replay = Replay(game)
    try:
        replay.advance(200)
        user = game.arm.symbols['_ZZN13Bio4_UserData11GetInstanceEvE4inst']
        # Fixture setup only; the real title/mission lifecycle loads its rules.
        game.arm.call('_ZN13Bio4_UserData20SetMissionDifficultyEh', user, 4)
        replay.village()
        replay.close()
        report = check(game, replay, output)
        (output/'results.json').write_text(json.dumps(report, indent=2)+'\n')
        print('COMBAT_REGRESSION_PASS', output/'results.json', flush=True)
    finally:
        replay.close()
        game.close()


if __name__ == '__main__':
    main()
