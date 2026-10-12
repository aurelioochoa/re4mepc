import unittest
from types import SimpleNamespace
from re4pc.game import Game
from re4pc.input import DesktopInput


class KeyRoutingTests(unittest.TestCase):
    def test_controller_look_bypasses_mouse_scale_and_requires_gameplay(self):
        from unittest.mock import Mock
        self.game.pc.move=Mock()
        self.game.event(('controller_look',30,10))
        self.game.pc.move.assert_called_once_with(30,10,sensitivity=1.0)
        self.game.pc.active=False
        self.game.event(('controller_look',30,10))
        self.assertEqual(self.game.pc.move.call_count,1)

    def setUp(self):
        self.pc_events = []
        self.native_events = []
        self.game = Game.__new__(Game)
        self.game.pc = SimpleNamespace(enabled=True, active=True,
            item_active=False, story_active=False,
            key=lambda down, code: self.pc_events.append((down, code)))
        self.game.media = SimpleNamespace(video=None)
        self.game.jni = SimpleNamespace(activity=1,
            native=lambda *args: self.native_events.append(args))
        self.game.key_sources = {}
        self.game.key_routes = {}
        self.game.input_events = 0
        self.input = DesktopInput(lambda *args: None, self.game.key)
        self.game.desktop_input = self.input

    def test_alias_release_keeps_other_direction_held(self):
        for event in [('key', True, ord('w')), ('key', True, 1073741906),
                      ('key', False, ord('w'))]:
            self.input.enqueue(event)
        self.input.flush()
        self.input.flush()
        self.assertEqual(self.pc_events, [(True, 19)])
        self.input.enqueue(('key', False, 1073741906))
        self.input.flush()
        self.assertEqual(self.pc_events, [(True, 19), (False, 19)])
        self.assertEqual(self.native_events, [])

    def test_release_uses_press_route_after_menu_opens(self):
        self.game.key(True, ord('x'))
        self.game.pc.active = False
        self.game.key(False, ord('x'))
        self.assertEqual(self.pc_events, [(True, 9), (False, 9)])
        self.assertEqual(self.native_events, [])

    def test_menu_keys_use_native_handler(self):
        self.game.pc.active = False
        self.game.key(True, 13)
        self.game.pc.active = True
        self.game.key(False, 13)
        self.assertEqual([event[0] for event in self.native_events],
                         ['native_onKeyDown', 'native_onKeyUp'])
        self.assertEqual(self.pc_events, [])

    def test_pickup_space_bypasses_story_close_button_and_native_keys(self):
        self.game.pc.active = False
        self.game.pc.story_active = True
        self.game.pc.item_active = True
        self.game.event(('key', True, 32))
        # Use the same queued input path as a real game frame.
        self.input.flush()
        self.game.pc.item_active = False
        self.game.event(('key', False, 32))
        self.input.flush()
        self.assertEqual(self.pc_events, [(True, 23), (False, 23)])
        self.assertEqual(self.native_events, [])

    def test_focus_loss_releases_all_aliases(self):
        self.input.enqueue(('key', True, ord('w')))
        self.input.enqueue(('key', True, 1073741906))
        self.input.flush()
        self.input.release()
        self.input.flush()
        self.assertEqual(self.pc_events, [(True, 19), (False, 19)])

    def test_already_released_controller_source_does_not_reroute_native_up(self):
        self.game.key(True, ord('w'))
        self.game.key(False, ord('w'))
        self.game.pc.active = False
        self.game.key(False, ord('w'))
        self.assertEqual(self.pc_events, [(True, 19), (False, 19)])
        self.assertEqual(self.native_events, [])

    def test_story_press_releases_touch_on_original_route_after_dialog_closes(self):
        touch = []
        self.game.pc.active = False
        self.game.pc.story_active = True
        self.game.desktop_input = DesktopInput(lambda *event:touch.append(event), self.game.key)
        self.game.event(('key', True, 13))
        self.game.desktop_input.flush()
        self.game.pc.story_active = False
        self.game.event(('key', False, 13))
        self.game.desktop_input.flush()
        self.assertEqual(touch, [('down',742,416), ('up',742,416)])
        self.assertEqual(self.native_events, [])
