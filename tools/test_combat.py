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
        # Known negative control: native Extreme deliberately suppresses the
        # beam. Re-enable only its visibility query for the PC comparison.
        pc.enabled = False
        assert arm.call(query, params) == 1
        arm.call(visibility, laser, 1)
        hidden = measure('native-extreme-hidden')
        assert hidden == 0, ('Negative laser control drew pixels', hidden)
        pc.enabled = True
        assert arm.call(query, params) == 0
        # Leaving touch mode releases the desktop capture and its held inputs.
        # Re-enter aim through the normal event route before measuring PC mode.
        replay.advance()
        event('mouse_button', True, 3)
        replay.advance(45)
        arm.call(visibility, laser, 1)
        visible = measure('pc-extreme-visible')
        assert visible >= 20, ('PC laser is not visible', visible)
        assert arm.call(difficulty, params) == 4
        record('extreme_laser', {'native_pixels': hidden, 'pc_pixels': visible,
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
        assert not game.graphics.debug_messages, sorted(game.graphics.debug_messages)
        return report
    finally:
        pc.enabled = True
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
