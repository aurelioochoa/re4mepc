import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from re4pc.menu_controls import MenuControls
from re4pc.game import Game


class FakeArm:
    """Guest memory holding just the LYT fields focus navigation reads."""
    def __init__(self):
        self.memory = bytearray(0x40000)
        self.call = Mock()
        self.next = 0x1000

    def read(self, address, size):
        return bytes(self.memory[address:address+size])

    def u32(self, address):
        return struct.unpack_from('<I', self.memory, address)[0]

    def put(self, address, fmt, *values):
        struct.pack_into(fmt, self.memory, address, *values)

    def component(self, rect, *, enabled=True, children=(), index=0, touch=None):
        address = self.next
        self.next += 0x200
        self.memory[address+0x50:address+0x52] = b'\x01\x01' if enabled else b'\x00\x01'
        self.put(address+0x3c, '<4i', *rect)
        self.put(address+0xb8, '<4i', *(touch or rect))
        self.put(address+0x98, '<i', index)
        if children:
            vector = self.next
            self.next += 0x200
            self.put(vector, f'<{len(children)}I', *children)
            self.put(address+0x0c, '<I', vector)
            self.put(address+0x18, '<I', len(children))
        return address


class MenuControlTests(unittest.TestCase):
    def setUp(self):
        self.touch = Mock()
        self.arm = FakeArm()
        self.menu = MenuControls(self.arm, self.touch)

    def frame(self, drawn, state=None, task=0):
        self.menu.begin_observation()
        self.menu.drawn.update(drawn)
        self.menu.state, self.menu.task = state, task
        self.menu._collect()

    def press(self, code, ticks=3):
        self.menu.key(True, code)
        for _ in range(ticks): self.menu.tick()
        self.menu.key(False, code)

    def taps(self):
        return [c.args for c in self.touch.call_args_list if c.args[0] == 'up']

    def title_menu(self):
        arm = self.arm
        self.start = arm.component((192, 102, 414, 57))
        self.coin = arm.component((192, 192, 414, 57))
        self.history = arm.component((192, 282, 414, 57))
        self.back = arm.component((15, 369, 96, 96), touch=(22, 376, 81, 81))
        self.options = arm.component((688, 369, 96, 96), touch=(695, 376, 81, 81))
        self.frame({c: 'Button' for c in (self.start, self.coin, self.history, self.back, self.options)})

    def test_focus_starts_on_main_choice_and_moves_by_screen_position(self):
        self.title_menu()
        self.assertTrue(self.menu.active)
        self.assertEqual(self.menu.focus, self.start)
        self.assertEqual(self.menu.focus_rect(), (192, 102, 414, 57))
        self.press(20)
        self.assertEqual(self.menu.focus, self.coin)
        self.press(20); self.press(20)
        self.assertEqual(self.menu.focus, self.back)
        self.press(22)
        self.assertEqual(self.menu.focus, self.options)
        self.press(22)
        self.assertEqual(self.menu.focus, self.options)
        self.press(19)
        self.assertEqual(self.menu.focus, self.history)
        self.assertEqual(self.touch.call_count, 0)

    def test_confirm_and_action_tap_the_focused_touch_area_once(self):
        self.title_menu()
        self.press(20)
        self.press(66)
        self.assertEqual([c.args for c in self.touch.call_args_list], [('down', 399, 220), ('up', 399, 220)])
        self.menu.focus = self.options
        self.press(23)
        self.assertEqual(self.taps()[-1], ('up', 736, 416))
        self.assertEqual(self.menu.confirmations, 2)

    def test_held_direction_repeats_after_a_delay(self):
        rows = [self.arm.component((195, 84 * i, 408, 84), index=i) for i in range(1, 5)]
        self.frame({row: 'TableViewItem' for row in rows})
        self.assertEqual(self.menu.focus, rows[0])
        self.menu.key(True, 20)
        self.assertEqual(self.menu.focus, rows[1])
        for _ in range(7): self.menu.tick()
        self.assertEqual(self.menu.focus, rows[1])
        self.menu.tick()
        self.assertEqual(self.menu.focus, rows[2])
        for _ in range(3): self.menu.tick()
        self.assertEqual(self.menu.focus, rows[3])
        self.menu.key(False, 20)
        for _ in range(10): self.menu.tick()
        self.assertEqual(self.menu.focus, rows[3])

    def test_mouse_hides_focus_and_first_key_only_reveals_it(self):
        self.title_menu()
        self.menu.pointer_moved()
        self.assertIsNone(self.menu.focus_rect())
        self.press(20)
        self.assertEqual(self.menu.focus, self.start)
        self.assertIsNotNone(self.menu.focus_rect())
        self.press(20)
        self.assertEqual(self.menu.focus, self.coin)

    def test_disabled_containers_and_empty_rows_are_not_focusable(self):
        rows = [self.arm.component((157, 83 + 84 * i, 408, 84), index=i) for i in range(3)]
        spacer = self.arm.component((157, 81, 408, 2), index=-1)
        empty = self.arm.component((157, 335, 408, 84), index=-1)
        table = self.arm.component((136, -1, 450, 504), enabled=False, children=(spacer, *rows, empty))
        use = self.arm.component((414, 85, 381, 66))
        drop = self.arm.component((414, 160, 381, 66))
        hidden = self.arm.component((300, 300, 100, 60), enabled=False)
        offscreen = self.arm.component((633, 3, 501, 66))
        drawn = {table: 'TableView', use: 'Button', drop: 'Button', hidden: 'Button', offscreen: 'Button',
                 spacer: 'TableViewItem', empty: 'TableViewItem', **{row: 'TableViewItem' for row in rows}}
        self.frame(drawn)
        self.assertEqual({t.component for t in self.menu.targets}, {use, drop})
        self.assertEqual(self.menu.focus, use)
        self.arm.memory[table+0x50] = 1
        self.frame(drawn)
        self.assertEqual({t.component for t in self.menu.targets}, {use, drop, *rows})

    def test_counter_owns_its_arrows_and_left_right_tap_them(self):
        arm = self.arm
        left = arm.component((166, 117, 85, 85))
        right = arm.component((546, 117, 85, 85))
        counter = arm.component((166, 117, 465, 85), children=(arm.component((0, 0, 1, 1), children=(left, right)),))
        ok = arm.component((192, 388, 414, 57))
        task = arm.component((0, 0, 0, 0))
        arm.put(task+0x0c, '<I', ok)
        self.frame({left: 'PushButton', right: 'PushButton', counter: 'Counter', ok: 'Button'},
                   state='difficulty', task=task)
        self.assertEqual({t.component for t in self.menu.targets}, {counter, ok})
        self.assertEqual(self.menu.focus, ok, 'Enter keeps continuing from the difficulty screen')
        self.press(19)
        self.assertEqual(self.menu.focus, counter)
        self.press(22)
        self.press(21)
        self.assertEqual(self.taps(), [('up', 588, 160), ('up', 208, 160)])
        self.press(66)
        self.assertEqual(len(self.taps()), 2, 'Confirm on a counter presses nothing')
        self.press(20)
        self.assertEqual(self.menu.focus, ok)

    def slider(self):
        self.slide = self.arm.component((192, 295, 414, 57))
        self.cancel_button = self.arm.component((192, 378, 414, 57))
        self.frame({self.slide: 'SliderButton', self.cancel_button: 'Button'}, state='confirmation', task=0x100)

    def test_confirmation_slider_is_one_bounded_drag_per_press(self):
        self.slider()
        self.assertEqual(self.menu.focus, self.slide)
        self.menu.key(True, 66)
        for _ in range(40):
            self.menu.key(True, 66)
            self.menu.tick()
        self.assertEqual([c.args for c in self.touch.call_args_list],
                         [('down', 240, 324), ('move', 395, 324), ('move', 550, 324), ('up', 550, 324)])
        self.assertEqual(self.menu.confirmations, 1)
        self.menu.key(False, 66)
        self.menu.key(True, 66)
        self.assertEqual(self.menu.confirmations, 2)

    def test_cancel_during_each_gesture_tick_releases_only_started_touch(self):
        for ticks in range(9):
            with self.subTest(ticks=ticks):
                self.touch = Mock()
                self.menu = MenuControls(self.arm, self.touch)
                self.slider()
                self.menu.key(True, 66)
                for _ in range(ticks): self.menu.tick()
                self.menu.cancel()
                for _ in range(20): self.menu.tick()
                events = [c.args[0] for c in self.touch.call_args_list]
                self.assertEqual(events.count('down'), events.count('up'))
                self.assertFalse(self.menu.gesture)
                self.assertFalse(self.menu.touch_down)

    def test_state_change_cancels_gesture(self):
        self.slider()
        self.menu.key(True, 66)
        self.menu.tick()
        self.menu.begin_observation()
        self.menu.end_observation()
        self.assertEqual([c.args[0] for c in self.touch.call_args_list], ['down', 'up'])
        self.assertIsNone(self.menu.state)

    def test_gameplay_and_empty_screens_synthesize_nothing(self):
        pause = self.arm.component((3, 3, 111, 78))
        self.menu.gameplay = lambda: True
        self.frame({pause: 'Button'})
        self.assertFalse(self.menu.active)
        self.assertIsNone(self.menu.focus_rect())
        for code in (19, 23, 66, 32): self.menu.key(True, code)
        self.menu.tick()
        self.menu.gameplay = lambda: False
        self.frame({})
        self.assertFalse(self.menu.active)
        self.menu.held.clear()
        for code in (19, 23, 66, 32): self.menu.key(True, code)
        self.menu.tick()
        self.touch.assert_not_called()
        self.arm.call.assert_not_called()

    def test_title_input_panel_is_tapped_when_no_button_exists(self):
        panel = self.arm.component((0, 0, 799, 480))
        self.frame({panel: 'InputPanel'}, state='title', task=0x100)
        self.assertIsNone(self.menu.focus_rect())
        self.press(66)
        self.assertEqual(self.taps(), [('up', 400, 240)])

    def test_list_scrolls_natively_past_its_last_visible_row(self):
        rows = [self.arm.component((195, 84 * i, 408, 84), index=i - 1) for i in range(1, 5)]
        table = self.arm.component((174, 0, 450, 504), children=rows)
        self.arm.put(table+0xb8, '<i', 10)
        drawn = {table: 'TableView', **{row: 'TableViewItem' for row in rows}}
        self.frame(drawn)
        self.menu.focus = rows[-1]
        self.press(20)
        self.assertEqual([c.args for c in self.arm.call.call_args_list],
                         [('_ZN17LYT_Cmp_TableView18Select_ViewTopItemEl', table, 1),
                          ('_ZN17LYT_Cmp_TableView11UpdateItemsEv', table)])
        for offset, row in enumerate(rows):
            self.arm.put(row+0x98, '<i', offset + 1)
        self.frame(drawn)
        self.assertEqual(self.menu.focus, rows[-1])
        self.assertEqual(self.menu._index(self.menu.focus), 4)
        self.arm.call.reset_mock()
        self.arm.put(rows[-1]+0x98, '<i', 9)
        self.frame(drawn)
        self.press(20)
        self.arm.call.assert_not_called()

    def test_inventory_cancel_taps_verified_button_once(self):
        for state, position in (('inventory', (60, 340)), ('inventory_submenu', (600, 265))):
            self.menu.cancel()
            self.touch.reset_mock()
            self.menu.state = state
            self.assertTrue(self.menu.routes(32))
            for _ in range(20):
                self.menu.key(True, 32)
                self.menu.tick()
            self.assertEqual(self.touch.call_args_list, [unittest.mock.call('down', *position), unittest.mock.call('up', *position)])
        self.menu.state = 'notice'
        self.assertFalse(self.menu.routes(32))

    def test_data_reset_cancel_uses_native_handler(self):
        self.menu.state, self.menu.task = 'data_reset', 0x100
        self.assertTrue(self.menu.routes(32))
        self.press(32, ticks=1)
        self.arm.call.assert_called_once_with('_ZN21Bio4_CTTask_DataReset4OnNoEP14LYT_CmpProductmPv', 0x100, 0, 1, 0)

    def test_retired_task_cancels_pending_gesture(self):
        self.slider()
        self.menu.task_stamp = (0, b'\x00')
        self.menu.key(True, 66)
        self.menu.tick()
        self.arm.put(0x100, '<I', 2)
        self.menu.tick()
        self.assertIsNone(self.menu.state)
        self.assertFalse(self.menu.touch_down)
        self.assertEqual([c.args[0] for c in self.touch.call_args_list], ['down', 'up'])

    def test_game_focus_disconnect_and_quit_cancel_gesture_before_other_input(self):
        for event in (('focus_lost',), ('controller_removed', 7), ('quit',)):
            with self.subTest(event=event):
                game = Game.__new__(Game)
                game.menu = self.menu
                game.pc = SimpleNamespace(active=False, release=Mock())
                game.graphics = SimpleNamespace(controller=SimpleNamespace(release=Mock(), process=Mock(), gameplay=False))
                game.mouse_bindings = SimpleNamespace(release=Mock())
                game.desktop_input = SimpleNamespace(release=Mock())
                self.slider()
                self.menu.key(True, 66)
                self.menu.tick()
                game.event(event)
                self.assertFalse(self.menu.touch_down)
                self.assertFalse(self.menu.gesture)
                self.assertFalse(self.menu.held)

    def test_game_mouse_motion_hides_focus(self):
        self.title_menu()
        game = Game.__new__(Game)
        game.menu = self.menu
        game.pc = SimpleNamespace(enabled=True, active=False)
        game.mouse_captured = game.skipping_touch = False
        game.desktop_input = SimpleNamespace(enqueue=Mock())
        game.event(('motion', 10, 10))
        self.assertIsNone(self.menu.focus_rect())
        game.desktop_input.enqueue.assert_called_once_with(('motion', 10, 10))

    def test_game_releases_menu_press_on_menu_route_after_gameplay_begins(self):
        self.title_menu()
        game = Game.__new__(Game)
        game.menu = self.menu
        game.pc = SimpleNamespace(enabled=True, active=False, item_active=False, key=Mock())
        game.jni = SimpleNamespace(activity=1, native=Mock())
        game.key_sources, game.key_routes, game.input_events = {}, {}, 0
        game.keymap = {13:66}
        game.key(True, 13)
        self.menu.cancel()
        self.frame({})
        game.pc.active = True
        game.key(False, 13)
        game.pc.key.assert_not_called()
        game.jni.native.assert_not_called()
        self.assertEqual(game.key_routes, {})
