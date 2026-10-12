"""Shared action names and stable native input codes for every desktop device."""
from copy import deepcopy

NATIVE_CODES = {'forward': 19, 'backward': 20, 'left': 21, 'right': 22,
                'fire': 8, 'aim': 9, 'reload': 12, 'knife': 11,
                'action': 23, 'interact': 47, 'confirm': 66, 'status': 32, 'companion': 29}
# SDL keycodes. Aliases remain separate physical sources until released.
DEFAULT_BINDINGS = {
    'keyboard': {'forward': [119, 1073741906], 'backward': [115, 1073741905],
                 'left': [97, 1073741904], 'right': [100, 1073741903],
                 'fire': [122], 'aim': [120], 'reload': [114], 'knife': [102],
                 'action': [32], 'interact': [101], 'confirm': [13], 'status': [27], 'companion': [113]},
    'mouse': {'fire': [1], 'aim': [3]},
    'controller': {'action': ['a'], 'confirm': ['b'], 'reload': ['x'],
                   'knife': ['y'], 'status': ['start'], 'companion': ['leftshoulder'],
                   'forward': ['dpup'], 'backward': ['dpdown'],
                   'left': ['dpleft'], 'right': ['dpright'],
                   'aim': ['lefttrigger'], 'fire': ['righttrigger']}}
CONTROLLER_BUTTONS = ('a', 'b', 'x', 'y', 'back', 'guide', 'start', 'leftstick',
                      'rightstick', 'leftshoulder', 'rightshoulder', 'dpup',
                      'dpdown', 'dpleft', 'dpright')
CONTROLLER_INPUTS = set(CONTROLLER_BUTTONS) | {'lefttrigger', 'righttrigger'}
VIRTUAL_KEY_BASE = 0x20000000
MOUSE_KEY_BASE = VIRTUAL_KEY_BASE + 0x1000
RESERVED_KEYS = {9, 1073741884, 1073741893}


def defaults():
    return deepcopy(DEFAULT_BINDINGS)


def virtual_key(action):
    return VIRTUAL_KEY_BASE + NATIVE_CODES[action]


def key_map(settings=None):
    bindings = (settings or {}).get('bindings', DEFAULT_BINDINGS)
    result = {key: NATIVE_CODES[action] for action, keys in bindings['keyboard'].items()
              for key in keys}
    result.update({virtual_key(action): native for action, native in NATIVE_CODES.items()})
    result.update({MOUSE_KEY_BASE+native*8+button: native for native in NATIVE_CODES.values() for button in range(1,6)})
    return result


class ActionState:
    """Reference count held actions by source; route releases with their press."""
    def __init__(self):
        self.sources = {}

    def set(self, source, action, down):
        events = []
        old = self.sources.get(source)
        if old is not None and (not down or old != action):
            del self.sources[source]
            if old not in self.sources.values():
                events.append(('key', False, virtual_key(old)))
        if down and action is not None and self.sources.get(source) != action:
            was_held = action in self.sources.values()
            self.sources[source] = action
            if not was_held:
                events.append(('key', True, virtual_key(action)))
        return events

    def release(self, predicate=lambda source: True):
        events = []
        for source in list(self.sources):
            if predicate(source):
                events.extend(self.set(source, None, False))
        return events


class MouseBindings:
    """Map mouse buttons to stable key sources, retaining presses across remaps."""
    def __init__(self, settings=None):
        self.bindings = (settings or {}).get('bindings', DEFAULT_BINDINGS)['mouse']
        self.held = {}

    def event(self, down, button):
        if down:
            action = next((action for action, buttons in self.bindings.items() if button in buttons), None)
            if action is None:
                return None
            code = self.held.setdefault(button, MOUSE_KEY_BASE+NATIVE_CODES[action]*8+button)
        else:
            code = self.held.pop(button, None)
            if code is None:
                return None
        return ('key', down, code)

    def release(self):
        events = [('key', False, code) for code in self.held.values()]
        self.held.clear()
        return events

    def configure(self, settings):
        releases = self.release()
        self.bindings = settings['bindings']['mouse']
        return releases
