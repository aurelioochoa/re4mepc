"""SDL2 controller lifecycle and simulation-tick desktop event translation."""
import ctypes as C
from collections import deque
from .actions import ActionState, CONTROLLER_BUTTONS, virtual_key
from .settings import validate


class ControllerInput:
    def __init__(self, sdl=None, settings=None):
        self.sdl = sdl
        self.settings = validate(settings or {})
        self.handles = {}
        self.axes = {}
        self.buttons = {}
        self.pending = deque()
        self.actions = ActionState()
        self.sent_keys = set()
        self.sent_touch = False
        self.cursor = [400.0, 240.0]
        self.touch_sources = set()
        self.gameplay = False
        self.menu_actions = False
        if sdl is not None:
            signatures = {'SDL_NumJoysticks': (C.c_int, ()),
                          'SDL_IsGameController': (C.c_int, (C.c_int,)),
                          'SDL_GameControllerOpen': (C.c_void_p, (C.c_int,)),
                          'SDL_GameControllerClose': (None, (C.c_void_p,)),
                          'SDL_GameControllerGetJoystick': (C.c_void_p, (C.c_void_p,)),
                          'SDL_JoystickInstanceID': (C.c_int, (C.c_void_p,))}
            for name, (result, args) in signatures.items():
                function = getattr(sdl, name)
                function.restype, function.argtypes = result, args
            for index in range(sdl.SDL_NumJoysticks()):
                self.add(index)

    def add(self, index):
        if self.sdl is None or not self.sdl.SDL_IsGameController(index):
            return
        handle = self.sdl.SDL_GameControllerOpen(index)
        if handle:
            instance = self.sdl.SDL_JoystickInstanceID(self.sdl.SDL_GameControllerGetJoystick(handle))
            if instance in self.handles:
                self.sdl.SDL_GameControllerClose(handle)
            else:
                self.handles[instance] = handle

    def _queue(self, events, source):
        self.pending.extend((event, source) for event in events)

    def _action(self, identifier):
        return next((action for action, values in self.settings['bindings']['controller'].items()
                     if identifier in values), None)

    def _button(self, instance, identifier, down):
        source = ('controller', instance, identifier)
        if down == (source in self.buttons):
            return
        if down:
            action = self._action(identifier)
            self.buttons[source] = action
            # Menus can contain touch-only confirmation sliders. The action
            # button holds a virtual cursor; B/confirm retains keyboard menus.
            if not self.gameplay and not self.menu_actions and action == 'action':
                if not self.touch_sources:
                    self._queue([('touch', True, *map(round, self.cursor))], source)
                self.touch_sources.add(source)
            else:
                self._queue(self.actions.set(source, action, True), source)
        else:
            self.buttons.pop(source, None)
            if source in self.touch_sources:
                self.touch_sources.remove(source)
                if not self.touch_sources:
                    self._queue([('touch', False, *map(round, self.cursor))], source)
            self._queue(self.actions.set(source, None, False), source)

    def process(self, event):
        kind = event[0]
        if kind == 'controller_added':
            self.add(event[1])
        elif kind == 'controller_removed':
            self.release(event[1])
            handle = self.handles.pop(event[1], None)
            if handle and self.sdl:
                self.sdl.SDL_GameControllerClose(handle)
        elif kind == 'controller_axis':
            _, instance, axis, value = event
            if 0 <= axis < 6:
                self.axes.setdefault(instance, [0.0] * 6)[axis] = max(-1.0, min(1.0, value / 32767))
        elif kind == 'controller_button':
            _, down, instance, button = event
            if 0 <= button < len(CONTROLLER_BUTTONS):
                self._button(instance, CONTROLLER_BUTTONS[button], down)
        elif kind == 'focus_lost':
            self.release()
        else:
            return False
        return True

    def _axis(self, value):
        dead = self.settings['stick_dead_zone']
        return (abs(value) - dead) / (1 - dead) * (1 if value > 0 else -1) if abs(value) > dead else 0.0

    def tick(self, dt=0.05, gameplay=False):
        # Releases retain the route selected by their original press; never
        # reinterpret a held menu touch as a gameplay action after transition.
        self.gameplay = gameplay
        for instance, axes in self.axes.items():
            x, y, rx, ry = map(self._axis, axes[:4])
            for action, held in (('left', x < -0.15), ('right', x > 0.15),
                                 ('forward', y < -0.15), ('backward', y > 0.15)):
                source = ('stick', instance, action)
                self._queue(self.actions.set(source, action, held), source)
            for axis, identifier in ((4, 'lefttrigger'), (5, 'righttrigger')):
                self._button(instance, identifier, axes[axis] > 0.35)
            if gameplay:
                # Keep controller scaling separate from mouse sensitivity;
                # both devices still use the audited native camera bridge.
                scale = 600 * self.settings['controller_sensitivity'] * dt
                if rx or ry:
                    self._queue([('controller_look', rx * scale, ry * scale)], ('stick', instance, 'look'))
            elif rx or ry:
                self.cursor[0] = max(0, min(799, self.cursor[0] + rx * 600 * dt))
                self.cursor[1] = max(0, min(479, self.cursor[1] + ry * 600 * dt))
                if self.touch_sources:
                    self._queue([('motion', *map(round, self.cursor))], ('stick', instance, 'cursor'))
        events = [event for event, source in self.pending]
        self.pending.clear()
        for event in events:
            if event[0] == 'key':
                if event[1]:
                    self.sent_keys.add(event[2])
                else:
                    self.sent_keys.discard(event[2])
            elif event[0] == 'touch':
                self.sent_touch = event[1]
        return events

    def _reconcile(self):
        # A shared action's only queued down may belong to the removed pad.
        # Compare the remaining queue with the last emitted state so another
        # still-held source receives its down and removed sources get an up.
        keys, touch = set(self.sent_keys), self.sent_touch
        for event, source in self.pending:
            if event[0] == 'key':
                if event[1]:
                    keys.add(event[2])
                else:
                    keys.discard(event[2])
            elif event[0] == 'touch':
                touch = event[1]
        held = {virtual_key(action) for action in self.actions.sources.values()}
        for code in sorted(keys ^ held):
            self._queue([('key',code in held,code)], ('release',None))
        if touch != bool(self.touch_sources):
            self._queue([('touch',bool(self.touch_sources),*map(round,self.cursor))], ('release',None))

    def release(self, instance=None):
        matches = lambda source: instance is None or source[1] == instance
        # Discard pending downs for disconnected devices and regenerate only
        # held releases. Existing short taps already sent to DesktopInput are
        # protected by its transition queue.
        if instance is None:
            self.pending.clear()
        else:
            self.pending = deque((event, source) for event, source in self.pending if source[1] != instance)
        for source in list(self.buttons):
            if matches(source):
                self._button(source[1], source[2], False)
        self._queue(self.actions.release(matches), ('release', instance))
        self._reconcile()
        if instance is None:
            self.axes.clear()
        else:
            self.axes.pop(instance, None)

    def configure(self, settings):
        self.release()
        self.settings = validate(settings)

    def close(self):
        self.release()
        if self.sdl:
            for handle in self.handles.values():
                self.sdl.SDL_GameControllerClose(handle)
        self.handles.clear()
