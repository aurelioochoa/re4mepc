from collections import deque
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from re4pc.actions import virtual_key
from re4pc.controllers import ControllerInput
from re4pc.menu_controls import MenuControls
from re4pc.game import Game
from re4pc.input import DesktopInput


class MenuControlTests(unittest.TestCase):
    def test_inventory_cancel_clicks_verified_button_once_and_preserves_cursor(self):
        for state,position in (('inventory',(60,340)),('inventory_submenu',(600,265))):
            self.menu.cancel()
            self.touch.reset_mock()
            self.menu.state=state
            self.menu.cursor[:]=[350,120]
            self.assertTrue(self.menu.routes(32))
            for _ in range(20):
                self.menu.key(True,32)
                self.menu.tick()
            self.assertEqual(self.touch.call_args_list,[unittest.mock.call('down',*position),unittest.mock.call('up',*position)])
            self.assertEqual(self.menu.cursor,[350,120])
        self.menu.state='notice'
        self.assertFalse(self.menu.routes(32))
        self.assertNotIn('Back',self.menu.hints()[0])

    def test_pending_native_title_action_waits_for_scene_and_can_be_cancelled(self):
        self.menu.state = 'title_top'
        self.arm.u32.side_effect = lambda pointer: {104:44,108:4,180:55}.get(pointer,0)
        ready = False
        actions = []
        def call(symbol,*args):
            if symbol == '_ZNK17LAS_LytController5IsEndEv': return ready
            actions.append(symbol)
        self.arm.call.side_effect = call
        self.menu.key(True,66)
        for _ in range(20):self.menu.tick()
        self.assertEqual(actions,[])
        self.assertIsNotNone(self.menu.native_request)
        ready = True
        self.menu.tick()
        self.menu.tick()
        self.assertEqual(actions,['_ZN17Bio4_CTTask_Title7OnStartEP14LYT_CmpProductmPv'])
        self.menu.key(False,66)
        self.menu.key(True,66)
        self.menu.cancel()
        self.menu.tick()
        self.assertEqual(len(actions),1)

    def test_phase_change_or_retired_task_cancels_without_a_guessed_action(self):
        self.menu.task_stamp = (1,b'\x01\x01')
        self.menu.key(True,66)
        self.menu.tick()
        self.arm.u32.return_value = 2
        self.menu.tick()
        self.assertIsNone(self.menu.state)
        self.assertFalse(self.menu.touch_down)
        self.assertEqual([c.args[0] for c in self.touch.call_args_list],['down','up'])

    def setUp(self):
        self.touch = Mock()
        self.arm = SimpleNamespace(u32=Mock(return_value=1), call=Mock(), read=Mock(return_value=b'\x01\x01'))
        self.menu = MenuControls(self.arm, self.touch)
        self.menu.state, self.menu.task = 'confirmation', 100

    def test_confirmation_is_bounded_once_per_press_with_one_touch_release(self):
        self.menu.key(True, 66)
        for _ in range(40):
            self.menu.key(True, 66)
            self.menu.tick()
        self.assertEqual([c.args[0] for c in self.touch.call_args_list], ['down', 'move', 'move', 'up'])
        self.assertEqual(self.menu.confirmations, 1)
        self.menu.key(False, 66)
        self.menu.key(True, 66)
        self.assertEqual(self.menu.confirmations, 2)

    def test_cancel_during_each_gesture_tick_releases_only_started_touch(self):
        for ticks in range(9):
            with self.subTest(ticks=ticks):
                touch = Mock()
                menu = MenuControls(self.arm, touch)
                menu.state = 'confirmation'
                menu.key(True, 66)
                for _ in range(ticks): menu.tick()
                menu.cancel()
                for _ in range(20): menu.tick()
                events = [c.args[0] for c in touch.call_args_list]
                self.assertEqual(events.count('down'), events.count('up'))
                self.assertFalse(menu.gesture)
                self.assertFalse(menu.touch_down)

    def test_state_change_cancels_gesture_and_unknown_state_synthesizes_nothing(self):
        self.menu.key(True, 66)
        self.menu.tick()
        self.menu.begin_observation()
        self.menu.end_observation()
        self.assertEqual([c.args[0] for c in self.touch.call_args_list], ['down', 'up'])
        self.assertFalse(self.menu.active)
        for code in (19, 23, 66, 32): self.menu.key(True, code)
        self.menu.tick()
        self.assertEqual(self.touch.call_count, 2)
        self.arm.call.assert_not_called()

    def test_native_confirm_requires_recognized_and_enabled_component(self):
        self.menu.state = 'difficulty'
        self.menu.key(True, 66)
        self.menu.tick()
        self.arm.call.assert_called_once_with('_ZN19Bio4_CTTask_DiffTop11_HdlButtonsEP14LYT_CmpProductmPv', 100, 1, 1, 0)
        self.menu.cancel()
        self.arm.call.reset_mock()
        self.arm.read.return_value = b'\x00\x01'
        self.menu.key(True, 66)
        self.menu.tick()
        self.arm.call.assert_not_called()

    def test_direction_cursor_and_hints_follow_remaps(self):
        from re4pc.settings import validate
        settings = validate({})
        settings['bindings']['keyboard']['confirm'] = [ord('c')]
        settings['bindings']['controller']['confirm'] = ['x']
        self.menu.settings = settings
        self.menu.state = 'inventory'
        self.menu.key(True, 22)
        self.menu.key(True, 20)
        for _ in range(100): self.menu.tick()
        self.assertEqual(self.menu.cursor, [799, 479])
        self.assertIn('C/X: Click', self.menu.hints()[0])
        self.menu.key(False, 22)
        self.menu.key(False, 20)
        self.menu.key(True, 66)
        for _ in range(3): self.menu.tick()
        self.assertEqual(self.touch.call_args_list[-1].args, ('up', 799, 479))

    def test_controller_menu_actions_and_release_keep_original_route(self):
        pad = ControllerInput()
        pad.menu_actions = True
        pad.process(('controller_button', True, 7, 0))
        self.assertEqual(pad.tick(), [('key', True, virtual_key('action'))])
        pad.gameplay = True
        pad.process(('controller_removed', 7))
        self.assertEqual(pad.tick(gameplay=True), [('key', False, virtual_key('action'))])

    def test_game_focus_disconnect_and_quit_cancel_gesture_before_other_input(self):
        for event in (('focus_lost',), ('controller_removed', 7), ('quit',)):
            with self.subTest(event=event):
                game = Game.__new__(Game)
                game.menu = self.menu
                game.pc = SimpleNamespace(active=False, release=Mock())
                game.graphics = SimpleNamespace(controller=SimpleNamespace(release=Mock(), process=Mock(), gameplay=False))
                game.mouse_bindings = SimpleNamespace(release=Mock())
                game.desktop_input = SimpleNamespace(release=Mock())
                self.menu.state = 'confirmation'
                self.menu.key(True, 66)
                self.menu.tick()
                game.event(event)
                self.assertFalse(self.menu.touch_down)
                self.assertFalse(self.menu.gesture)
                self.assertFalse(self.menu.held)

    def test_game_releases_menu_press_on_menu_route_after_gameplay_begins(self):
        game = Game.__new__(Game)
        game.menu = self.menu
        game.pc = SimpleNamespace(enabled=True, active=False, item_active=False, key=Mock())
        game.jni = SimpleNamespace(activity=1, native=Mock())
        game.key_sources, game.key_routes, game.input_events = {}, {}, 0
        game.keymap = {13:66}
        game.key(True, 13)
        self.menu.cancel()
        self.menu.state = None
        game.pc.active = True
        game.key(False, 13)
        game.pc.key.assert_not_called()
        game.jni.native.assert_not_called()
        self.assertEqual(game.key_routes, {})
