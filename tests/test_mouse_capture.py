"""Captured fire, released UI clicks and background recapture stay separate."""
from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call

from re4pc.actions import MouseBindings, key_map
from re4pc.game import Game
from re4pc.input import DesktopInput


class MouseCaptureTests(unittest.TestCase):
    def setUp(self):
        self.game = game = Game.__new__(Game)
        game.pc = SimpleNamespace(enabled=True, active=True, story_active=False,
                                  item_active=False, key=Mock(), release=Mock(), move=Mock(),
                                  pointer_target=Mock(return_value=False))
        game.graphics = SimpleNamespace(controller=Mock(), capture_mouse=Mock())
        game.media = SimpleNamespace(video=None)
        game.jni = SimpleNamespace(activity=1, native=Mock())
        game.menu = SimpleNamespace(active=False, cancel=Mock(), routes=lambda code: False)
        game.keymap = key_map()
        game.mouse_bindings = MouseBindings()
        game.key_sources, game.key_routes = {}, {}
        game.mouse_captured = game.mouse_released = game.recapture_click = False
        game.skipping_touch = False
        game.touch_previous = (0, 0)
        game.input_events = 0
        game.phase = lambda *args: nullcontext()
        game.desktop_input = DesktopInput(game.touch, game.key)
        game.update_mouse_capture()

    def flush(self):
        while self.game.desktop_input.pending:
            self.game.desktop_input.flush()

    def test_fire_at_hidden_button_positions_never_calls_touchscreen(self):
        for x, y in ((742,416), (100,400), (799,0), (400,240)):
            self.game.event(('touch', True, x, y))
            self.game.event(('motion', x+10, y+10))
            self.game.event(('touch', False, x+10, y+10))
            self.flush()
        self.assertEqual(self.game.pc.key.call_args_list,
                         [call(True,8), call(False,8)]*4)
        self.game.jni.native.assert_not_called()
        self.game.menu.cancel.assert_not_called()

    def test_tab_and_recapture_are_immediate_and_recapture_does_not_fire(self):
        self.game.event(('mouse_button', True, 3))
        self.flush()
        self.game.event(('key', True, 9))
        self.assertFalse(self.game.mouse_captured)
        self.game.graphics.capture_mouse.assert_called_with(False)
        self.game.event(('mouse_delta', 200, 100))
        self.game.pc.move.assert_not_called()
        self.game.event(('touch', True, 742, 416))
        self.assertTrue(self.game.mouse_captured)
        self.game.graphics.capture_mouse.assert_called_with(True)
        self.game.event(('mouse_button', False, 1))
        self.flush()
        self.assertEqual(self.game.pc.key.call_args_list, [call(True,9), call(False,9)])
        self.game.jni.native.assert_not_called()
        # The next click is a normal gameplay shot.
        self.game.event(('mouse_button', True, 1))
        self.game.event(('mouse_button', False, 1))
        self.flush()
        self.game.pc.key.assert_called_with(False, 8)

    def test_tab_toggle_twice_without_a_frame_restores_capture(self):
        self.game.event(('key', True, 9))
        self.game.event(('key', True, 9))
        self.assertTrue(self.game.mouse_captured)
        self.game.graphics.capture_mouse.assert_called_with(True)

    def test_released_ui_click_and_drag_stay_native_without_recapturing(self):
        self.game.pc.pointer_target.side_effect = lambda x, y: x < 100 and y < 80
        self.game.event(('key', True, 9))
        self.game.event(('touch', True, 40, 30))
        self.game.event(('motion', 45, 35))
        self.game.event(('touch', False, 45, 35))
        self.flush()
        self.assertTrue(self.game.mouse_released)
        self.assertFalse(self.game.mouse_captured)
        self.assertEqual([c.args[0] for c in self.game.jni.native.call_args_list],
                         ['native_onTouchBegan', 'native_onTouchMoved', 'native_onTouchEnded'])
        self.game.pc.key.assert_not_called()

    def test_ui_release_stays_native_after_inventory_opens(self):
        self.game.pc.pointer_target.return_value = True
        self.game.event(('key', True, 9))
        self.game.event(('touch', True, 40, 30))
        self.flush()
        self.game.pc.active = False
        self.game.menu.active = True
        self.game.update_mouse_capture()
        self.game.event(('touch', False, 40, 30))
        self.flush()
        self.assertEqual([c.args[0] for c in self.game.jni.native.call_args_list],
                         ['native_onTouchBegan', 'native_onTouchEnded'])
        self.assertFalse(self.game.gameplay_click)
        self.game.pc.key.assert_not_called()

    def test_tab_during_ui_press_releases_touch_and_cancels_drag(self):
        self.game.pc.pointer_target.return_value = True
        self.game.event(('key', True, 9))
        self.game.event(('touch', True, 40, 30))
        self.flush()
        self.game.event(('key', True, 9))
        self.flush()
        self.assertTrue(self.game.mouse_captured)
        self.assertFalse(self.game.gameplay_click)
        self.assertFalse(self.game.native_touch_down)
        self.assertEqual([c.args[0] for c in self.game.jni.native.call_args_list],
                         ['native_onTouchBegan', 'native_onTouchEnded'])

    def test_focus_loss_releases_capture_and_mouse_actions_immediately(self):
        self.game.event(('mouse_button', True, 3))
        self.flush()
        self.game.event(('focus_lost',))
        self.assertFalse(self.game.mouse_captured)
        self.game.event(('mouse_button', True, 3))
        self.game.event(('mouse_delta', 100, 100))
        self.flush()
        self.assertEqual(self.game.pc.key.call_args_list, [call(True,9), call(False,9)])
        self.game.pc.move.assert_not_called()
        self.game.jni.native.assert_not_called()

    def test_queued_touch_and_direct_moves_cannot_activate_gameplay_buttons(self):
        self.game.desktop_input.enqueue(('touch', True, 742, 416))
        self.game.desktop_input.enqueue(('motion', 700, 400))
        self.game.desktop_input.enqueue(('touch', False, 700, 400))
        self.flush()
        self.game.touch('move', 742, 416)
        self.game.jni.native.assert_not_called()

    def test_menus_and_touch_mode_keep_native_clicks(self):
        for touch_mode in (False, True):
            with self.subTest(touch_mode=touch_mode):
                self.game.pc.enabled = not touch_mode
                self.game.pc.active = touch_mode
                self.game.update_mouse_capture()
                self.game.event(('touch', True, 400, 240))
                self.game.event(('touch', False, 400, 240))
                self.flush()
                self.assertEqual([call.args[0] for call in self.game.jni.native.call_args_list],
                                 ['native_onTouchBegan', 'native_onTouchEnded'])
                self.game.jni.native.reset_mock()

    def test_controller_activity_does_not_undo_tab_release(self):
        self.game.event(('key', True, 9))
        self.game.event(('controller_axis', 7, 2, 300))
        self.game.update_mouse_capture()
        self.assertTrue(self.game.mouse_released)
        self.assertFalse(self.game.mouse_captured)

    def test_recapture_release_cannot_select_menu_that_opens_during_click(self):
        self.game.event(('key', True, 9))
        self.game.event(('touch', True, 742, 416))
        self.game.pc.active = False
        self.game.update_mouse_capture()
        self.game.event(('touch', False, 742, 416))
        self.flush()
        self.game.jni.native.assert_not_called()
        self.assertFalse(self.game.recapture_click)

    def test_capture_finishes_an_existing_native_menu_touch_once(self):
        self.game.pc.active = False
        self.game.update_mouse_capture()
        self.game.event(('touch', True, 400, 240))
        self.flush()
        self.game.pc.active = True
        self.game.update_mouse_capture()
        self.flush()
        self.game.event(('mouse_button', False, 1))
        self.flush()
        self.assertEqual([entry.args[0] for entry in self.game.jni.native.call_args_list],
                         ['native_onTouchBegan', 'native_onTouchEnded'])
