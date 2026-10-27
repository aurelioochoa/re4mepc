"""Visible keyboard/controller menu replay on a fresh, isolated engine fixture."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from re4pc.game import Game
from re4pc.paths import game_dir, isolated_game, test_output
from re4pc.timing import FramePacer
from tools.benchmark import source_identity
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_R4


def check(game, output, device):
    pacer = FramePacer()
    samples = []
    sdl = game.graphics.sdl
    sdl.SDL_PushEvent.argtypes = (C.c_void_p,)
    sdl.SDL_GetWindowID.argtypes = (C.c_void_p,)
    expected = []
    sdl.SDL_JoystickAttachVirtual.argtypes = (C.c_int, C.c_int, C.c_int, C.c_int)
    sdl.SDL_JoystickAttachVirtual.restype = C.c_int
    sdl.SDL_JoystickDetachVirtual.argtypes = (C.c_int,)
    instance, virtual_index = [None], [None]
    def attach():
        index = sdl.SDL_JoystickAttachVirtual(1, 6, 15, 0)
        assert index >= 0, sdl.SDL_GetError()
        virtual_index[0] = index
        game.graphics.controller.add(index)
        assert game.graphics.controller.handles, 'Virtual controller was not recognized'
        instance[0] = next(reversed(game.graphics.controller.handles))
    attach()

    def send(event):
        # Traverse SDL polling and normal Game.event, including controller IDs.
        buffer = C.create_string_buffer(64)
        down = event[1] if len(event)>1 else False
        kind = {'key': 0x300 if down else 0x301,
                'controller_button': 0x651 if down else 0x652,
                'focus_lost': 0x200, 'controller_removed': 0x654}[event[0]]
        struct.pack_into('<I', buffer, 0, kind)
        if event[0] == 'key':
            struct.pack_into('<I', buffer, 8, sdl.SDL_GetWindowID(game.graphics.window))
            buffer[12] = bytes([event[1]])
            struct.pack_into('<i', buffer, 20, event[2])
        elif event[0] == 'controller_button':
            struct.pack_into('<i', buffer, 8, event[2])
            buffer[12], buffer[13] = bytes([event[3]]), bytes([event[1]])
        elif event[0] == 'focus_lost':
            struct.pack_into('<I', buffer, 8, sdl.SDL_GetWindowID(game.graphics.window))
            buffer[12] = b'\x0d'
        else:
            struct.pack_into('<i', buffer, 8, event[1])
        assert sdl.SDL_PushEvent(buffer) == 1
        expected.append(event)

    def advance(count=1):
        for _ in range(count):
            events = list(game.graphics.events())
            for _ in range(2):
                if all(e in events for e in expected): break
                events.extend(game.graphics.events())
            for event in list(expected):
                assert event in events, ('SDL event lost', event, events)
                game.event(event)
                expected.remove(event)
            for event in events:
                if event == ('quit',): raise RuntimeError('Menu replay interrupted')
            game.frame()
            game.present()
            pacer.wait()

    def wait(state, limit=400):
        for _ in range(limit):
            if (game.pc.active if state == 'gameplay' else game.menu.state == state):
                samples.append({'state': state, 'tick': game.frames})
                game.graphics.screenshot(output/(device+'-'+state+'.png'))
                print('MENU_STATE', device, state, game.frames, flush=True)
                return
            advance()
        raise AssertionError(('Menu state not reached', state, game.menu.state, game.frames))

    def press(down, action='confirm'):
        if device == 'keyboard':
            code = {'confirm':13, 'action':32, 'status':27, 'right':ord('d'), 'left':ord('a'),
                    'up':ord('w'), 'down':ord('s')}[action]
            send(('key', down, code))
        else:
            button = {'confirm':1, 'action':0, 'status':6, 'right':14, 'left':13, 'up':11, 'down':12}[action]
            send(('controller_button', down, instance[0], button))

    def tap(action='confirm', ticks=3):
        press(True, action)
        advance(ticks)
        press(False, action)
        advance(4)

    advance(200)
    user = game.arm.symbols['_ZZN13Bio4_UserData11GetInstanceEvE4inst']
    # Navigation fixture only: this is not natural campaign qualification.
    game.arm.call('_ZN13Bio4_UserData19SetMissionClearFlagEllb', user, 0, 0, 1)
    game.arm.call('_ZN13Bio4_UserData16SetLastMissionIDEhs', user, 0, 1)
    game.arm.call('_ZN13Bio4_UserData12SetMissionIDEs', user, 1)
    def focused(kind=None):
        target = game.menu.focused()
        assert target and game.menu.focus_rect(), ('No visible focus', game.menu.state, game.menu.targets)
        assert kind is None or target.kind == kind, ('Unexpected focus', target, kind)
        return target

    def settle(ticks=40):
        # Layout scenes animate in; let rects reach their resting place.
        advance(ticks)

    wait('title')
    assert game.menu.focus_rect() is None
    tap()
    wait('title_top')
    settle()
    start = focused('Button')
    tap('down')
    assert focused().rect[1] > start.rect[1], 'Down did not move focus'
    tap('up')
    assert focused().component == start.component, 'Up did not return focus'
    game.graphics.screenshot(output/(device+'-title-focus.png'))
    tap()
    wait('difficulty')
    settle()
    assert focused('Button').component == game.arm.u32(game.menu.task+0x0c), 'OK is not the default focus'
    counter = game.arm.u32(game.menu.task+0x18)
    getter = '_ZNK15LYT_Cmp_Counter8GetValueEv'
    initial = game.arm.call(getter, counter)
    tap('up')
    assert focused('Counter').component == counter
    game.graphics.screenshot(output/(device+'-difficulty-focus.png'))
    tap('right', 3); advance(10)
    changed = game.arm.call(getter, counter)
    tap('left', 3); advance(10)
    restored = game.arm.call(getter, counter)
    assert changed != initial and restored == initial, ('Difficulty did not change and restore', initial, changed, restored)
    tap('down')
    focused('Button')
    tap()
    wait('confirmation')
    settle()
    focused('SliderButton')
    for cancel in (('focus_lost',), ('controller_removed', instance[0])):
        press(True)
        advance()
        if cancel[0] == 'controller_removed':
            assert sdl.SDL_JoystickDetachVirtual(virtual_index[0]) == 0
            expected.append(cancel)
        else:
            send(cancel)
        advance(3)
        if device == 'keyboard' or cancel[0] != 'controller_removed':
            press(False)
        advance(4)
        assert not game.menu.gesture and not game.menu.touch_down
        assert game.menu.state == 'confirmation', ('Cancelled gesture activated confirmation', cancel)
        if cancel[0] == 'controller_removed':
            attach()
    before = game.menu.confirmations
    press(True)
    advance(30)
    assert game.menu.confirmations == before+1, 'Held confirm repeated'
    press(False)
    advance(5)
    wait('notice')
    settle()
    focused('Button')
    tap()
    wait('mission')
    settle()
    first = focused('TableViewItem')
    table = game.menu.tables[first.component]
    rows = (game.arm.u32(table+0xb8), game.arm.u32(table+0xbc))
    print('MENU_MISSION_ROWS', device, rows, flush=True)
    base = game.menu._index(first.component)
    first_top = struct.unpack('<i', game.arm.read(table+0xcc, 4))[0]
    # Walk past the last visible row so the native table scrolls, then back.
    for step in range(1, rows[1] + 2):
        tap('down'); advance(4)
        assert game.menu._index(focused('TableViewItem').component) == base + step, ('List focus/scroll', step)
    top = struct.unpack('<i', game.arm.read(table+0xcc, 4))[0]
    assert top > first_top, 'Table did not scroll'
    game.graphics.screenshot(output/(device+'-mission-scrolled.png'))
    for step in range(rows[1], -1, -1):
        tap('up'); advance(4)
        assert game.menu._index(focused('TableViewItem').component) == base + step, ('List focus/scroll back', step)
    assert struct.unpack('<i', game.arm.read(table+0xcc, 4))[0] == first_top, 'Table did not scroll back'
    game.graphics.screenshot(output/(device+'-mission-focus.png'))
    tap()
    wait('mission_description')
    settle()
    assert focused('Button').component == game.arm.u32(game.menu.task+0x20), 'Select is not the default focus'
    tap()
    # Mission preparation then the existing Space/Enter story action.
    for _ in range(500):
        if game.pc.active: break
        if game.pc.story_active or game.menu.state == 'mission_prepare':
            tap()
        else:
            advance()
    wait('gameplay')
    tap('status')
    wait('inventory')
    settle()
    # Focus and press on the native item list; ordinary engine inventory
    # handlers continue to choose/validate items and actions.
    focused('TableViewItem')
    game.graphics.screenshot(output/(device+'-inventory-focus.png'))
    tap('action')
    wait('inventory_submenu')
    settle()
    focused('Button')
    game.graphics.screenshot(output/(device+'-inventory-action.png'))
    tap('status')
    wait('inventory')
    tap('status')
    wait('gameplay')
    game.verify_save_roundtrip()
    report = {'device': device, 'source':source_identity(),
              'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'states': samples, 'difficulty': [initial, changed, restored],
              'held_confirmation_once': True, 'focus_navigation': True, 'mission_rows': rows, 'focus_and_disconnect_cancel': True,
              'inventory_back_to_gameplay':True,
              'save_roundtrip': game.save_verified, 'engine_hz': 20,
              'fixture': 'tutorial clear and mission selection set synthetically; no campaign claim'}
    (output/(device+'-evidence.json')).write_text(json.dumps(report, indent=2)+'\n')
    print('MENU_CONTROLS_PASS', device, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=game_dir())
    parser.add_argument('--output', type=Path)
    parser.add_argument('--device', choices=('keyboard', 'controller'), default='keyboard')
    parser.add_argument('--hidden', action='store_true')
    args = parser.parse_args()
    output = test_output('menu-controls', args.output)
    root = isolated_game(args.game, output)
    game = Game(root, skip_videos=True, hidden=args.hidden)
    try:
        check(game, output, args.device)
    except BaseException:
        game.graphics.screenshot(output/'failure.png')
        (output/'failure-state.json').write_text(json.dumps({'menu': game.menu.state,
            'source':source_identity(), 'tick':game.frames,
            'guest_base':hex(game.arm.base), 'menu_task':hex(game.menu.task),
            'pc':hex(game.arm.uc.reg_read(UC_ARM_REG_PC)),
            'lr':hex(game.arm.uc.reg_read(UC_ARM_REG_LR)),
            'r4':hex(game.arm.uc.reg_read(UC_ARM_REG_R4)),
            'pc_active': game.pc.active, 'story_active': game.pc.story_active, 'item_active': game.pc.item_active,
            'gl_messages': sorted(game.graphics.debug_messages)},indent=2)+'\n')
        raise
    finally:
        game.close()


if __name__ == '__main__':
    main()
