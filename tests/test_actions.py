import unittest
from re4pc.actions import ActionState, MouseBindings, key_map, virtual_key
from re4pc.settings import validate


class ActionsTests(unittest.TestCase):
    def test_aliases_hold_until_last_source_releases(self):
        state=ActionState()
        self.assertEqual(state.set(('pad',1),'aim',True),[('key',True,virtual_key('aim'))])
        self.assertEqual(state.set(('pad',2),'aim',True),[])
        self.assertEqual(state.set(('pad',1),None,False),[])
        self.assertEqual(state.set(('pad',2),None,False),[('key',False,virtual_key('aim'))])

    def test_mouse_release_retains_original_action_after_remap(self):
        values=validate({})
        mouse=MouseBindings(values)
        down=mouse.event(True,3)
        values['bindings']['mouse']={'fire':[3]}
        mouse.bindings=values['bindings']['mouse']
        up=mouse.event(False,3)
        self.assertEqual(down[2],up[2])
        self.assertEqual(key_map(values)[up[2]],9)
        self.assertEqual(key_map(values)[mouse.event(True,3)[2]],8)

    def test_keyboard_aliases_and_independent_mouse_sources(self):
        values=validate({})
        values['bindings']['keyboard']['forward']=[ord('i'),1073741906]
        mapping=key_map(values)
        self.assertNotIn(ord('w'),mapping)
        self.assertEqual(mapping[ord('i')],19)
        mouse=MouseBindings(values)
        mouse_code=mouse.event(True,3)[2]
        self.assertNotEqual(mouse_code,virtual_key('aim'))
        self.assertEqual(mapping[mouse_code],9)

    def test_default_keyboard_map_preserves_existing_native_alias_codes(self):
        from re4pc.game import KEYS
        mapping=key_map()
        for code,native in KEYS.items():
            self.assertEqual(mapping[code],native)
