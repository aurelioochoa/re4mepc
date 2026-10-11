import unittest
from re4pc.input import DesktopInput


class InputTests(unittest.TestCase):
    def setUp(self):
        self.pressed = set()
        self.moves = []
        def touch(action, x, y):
            if action == 'down': self.pressed.add('mouse')
            elif action == 'up': self.pressed.discard('mouse')
            else: self.moves.append((x, y))
        def key(down, code):
            if down: self.pressed.add(code)
            else: self.pressed.discard(code)
        self.input = DesktopInput(touch, key)

    def test_fast_click_survives_frame_sampling(self):
        self.input.enqueue(('touch', True, 400, 390))
        self.input.enqueue(('touch', False, 400, 390))
        self.input.flush()
        self.assertIn('mouse', self.pressed)
        self.input.flush()
        self.assertNotIn('mouse', self.pressed)

    def test_fast_key_tap_and_simultaneous_action_keys(self):
        for event in [('key', True, 9), ('key', True, 8), ('key', False, 8), ('key', False, 9)]:
            self.input.enqueue(event)
        self.input.flush()
        self.assertEqual(self.pressed, {9, 8})
        self.input.flush()
        self.assertEqual(self.pressed, set())

    def test_drag_moves_while_pressed_and_releases_at_endpoint(self):
        for event in [('touch', True, 100, 350), ('motion', 110, 330),
                      ('motion', 130, 300), ('touch', False, 130, 300)]:
            self.input.enqueue(event)
        self.input.flush()
        self.assertEqual(self.moves, [(130, 300)])
        self.assertIn('mouse', self.pressed)
        self.input.flush()
        self.assertEqual(self.input.position, (130, 300))
        self.assertEqual(self.pressed, set())

    def test_focus_loss_releases_held_inputs_and_discards_queued_clicks(self):
        self.input.enqueue(('touch', True, 100, 350))
        self.input.enqueue(('key', True, 19))
        self.input.flush()
        self.input.enqueue(('motion', 200, 350))
        self.input.release()
        self.input.flush()
        self.assertEqual(self.pressed, set())
        self.assertEqual(self.moves, [])

    def test_fast_fire_click_and_focus_release(self):
        held=set()
        self.input.button=lambda down,button: held.add(button) if down else held.discard(button)
        self.input.enqueue(('mouse_button',True,1))
        self.input.enqueue(('mouse_button',False,1))
        self.input.flush()
        self.assertEqual(held,{1})
        self.input.release()
        self.input.flush()
        self.assertEqual(held,set())
