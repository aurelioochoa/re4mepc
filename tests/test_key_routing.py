import unittest
from types import SimpleNamespace
from re4pc.game import Game
from re4pc.input import DesktopInput


class KeyRoutingTests(unittest.TestCase):
    def setUp(self):
        self.pc_events = []
        self.native_events = []
        self.game = Game.__new__(Game)
        self.game.pc = SimpleNamespace(enabled=True, active=True,
            key=lambda down, code: self.pc_events.append((down, code)))
        self.game.jni = SimpleNamespace(activity=1,
            native=lambda *args: self.native_events.append(args))
        self.game.key_sources = {}
        self.game.key_routes = {}
        self.game.input_events = 0
        self.input = DesktopInput(lambda *args: None, self.game.key)

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

    def test_focus_loss_releases_all_aliases(self):
        self.input.enqueue(('key', True, ord('w')))
        self.input.enqueue(('key', True, 1073741906))
        self.input.flush()
        self.input.release()
        self.input.flush()
        self.assertEqual(self.pc_events, [(True, 19), (False, 19)])
