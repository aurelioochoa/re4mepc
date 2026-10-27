"""Keyboard/controller focus navigation over the engine's own layout buttons.

Every frame the drawn LYT components are observed. Enabled, visible buttons,
list rows, counters and confirmation sliders become focus targets; directions
move the focus between them by screen position and Confirm/Action presses the
focused one with an ordinary touch, exactly as a mouse click would. Gameplay
keeps its own input path. Recognized task states only add the verified
cancel actions and gesture-cancellation rules.
"""
from collections import deque, namedtuple
import re
import struct
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0

HOOKS = {
    'title': '_ZN17Bio4_CTTask_Title17_frameStepTopMainEP14Bio4_FrameWork',
    'title_top': '_ZN17Bio4_CTTask_Title18_frameStepMenuMainEP14Bio4_FrameWork',
    'difficulty': '_ZN19Bio4_CTTask_DiffTop15_Frame_StepMainEP14Bio4_FrameWork',
    'confirmation': '_ZN20Bio4_CTTask_DiffConf15_Frame_StepMainEP14Bio4_FrameWork',
    'notice': '_ZN21Bio4_CTTask_NewNotice5FrameEPv',
    'data_reset': '_ZN21Bio4_CTTask_DataReset5FrameEPv',
    'mission': '_ZN30Bio4_CTTask_MissionSelectStory14_frameStepMainEP14Bio4_FrameWork',
    'mission_description': '_ZN30Bio4_CTTask_MissionSelectStory18_frameStepDescMainEP14Bio4_FrameWork',
    'mission_prepare': '_ZN19GM_Task_Mis_Prepare13_Main_EvePlayEP11GM_CtrlMain',
    'mercenary': '_ZN34Bio4_CTTask_MissionSelectMercenary14_frameStepMainEP14Bio4_FrameWork',
    'mercenary_description': '_ZN34Bio4_CTTask_MissionSelectMercenary18_frameStepDescMainEP14Bio4_FrameWork',
    'inventory': '_ZN22Bio4_CTTask_StatusItem18_Frame_StepSelItemEP14Bio4_FrameWork',
    'inventory_submenu': '_ZN22Bio4_CTTask_StatusItem22_Frame_StepSubMenuMainEP14Bio4_FrameWork',
}
PRIORITY = tuple(reversed(tuple(HOOKS)))
CANCEL_TAP = {'inventory': (60, 340), 'inventory_submenu': (600, 265)}
# Task fields holding each screen's continue button (difficulty OK, notice
# Next, mission Select); it receives the initial focus so Enter continues.
DEFAULT_FOCUS = {'difficulty': 0x0c, 'notice': 0x0c, 'mission_description': 0x20}
DIRECTIONS = {19: (0, -1), 20: (0, 1), 21: (-1, 0), 22: (1, 0)}
MENU_CODES = set(DIRECTIONS) | {23, 66, 32}
PHASE_FIELDS = {'title': (8,4), 'title_top': (8,4), 'difficulty': (0x20,1),
                'confirmation': (0x14,1), 'notice': (0x10,1),
                'mission': (8,4), 'mission_description': (8,4),
                'mercenary': (8,4), 'mercenary_description': (8,4),
                'inventory': (0x0c,1), 'inventory_submenu': (0x0c,1)}
# Drawn components are observed through each class's own doDraw. Pure
# decoration is skipped; containers matter because a disabled table or layout
# disables the rows and buttons inside it.
DRAW_SYMBOL = re.compile(r'_ZN\d+LYT_Cmp_(\w+?)6doDrawEv$')
DECORATION = {'Image', 'String', 'FillRect', 'Temp', 'Target'}
FOCUSABLE = {'Button', 'PushButton', 'ToggleButton', 'Switch', 'SliderButton', 'TableViewItem', 'Counter'}
REPEAT_DELAY, REPEAT_EVERY = 8, 3

Target = namedtuple('Target', 'component kind rect')


def center(rect):
    x, y, w, h = rect
    return x + w / 2, y + h / 2


class MenuControls:
    def __init__(self, arm, touch, *, enabled=True, settings=None, gameplay=lambda: False):
        self.arm, self.touch, self.enabled = arm, touch, enabled
        self.settings = settings or {}
        self.gameplay = gameplay
        self.state, self.task = None, 0
        self.task_stamp = None
        self.observed = {}
        self.drawn = {}
        self.targets = []
        self.panels = []
        self.counters = {}
        self.tables = {}
        self.focus = None
        self.focus_visible = True
        self.pending_index = None
        self.held = set()
        self.repeat = None
        self.gesture = deque()
        self.touch_down = False
        self.touch_position = (0, 0)
        self.native_request = None
        self.hooks = []
        self.confirmations = 0

    @property
    def active(self):
        return self.enabled and (self.state is not None or (bool(self.targets) and not self.gameplay()))

    def install(self):
        if not self.enabled:
            return
        for state, symbol in HOOKS.items():
            if symbol not in self.arm.symbols:
                continue
            address = self.arm.symbols[symbol] & ~1
            self.hooks.append(self.arm.uc.hook_add(UC_HOOK_CODE, self._observe,
                user_data=state, begin=address, end=address))
        draws = {}
        for symbol, address in self.arm.symbols.items():
            match = DRAW_SYMBOL.match(symbol)
            if match and match.group(1) not in DECORATION:
                draws[address & ~1] = match.group(1)
        for address, kind in draws.items():
            self.hooks.append(self.arm.uc.hook_add(UC_HOOK_CODE, self._draw,
                user_data=kind, begin=address, end=address))

    def _observe(self, uc, address, size, state):
        try:
            task = uc.reg_read(UC_ARM_REG_R0)
            self.observed[state] = (task, self._stamp(state, task))
        except BaseException as error:
            self.arm.pending_error = error
            uc.emu_stop()

    def _draw(self, uc, address, size, kind):
        self.drawn[uc.reg_read(UC_ARM_REG_R0)] = kind

    def _stamp(self, state, task):
        offset, size = PHASE_FIELDS.get(state, (0,0))
        return self.arm.u32(task), self.arm.read(task + offset, size) if size else b''

    def begin_observation(self):
        self.observed.clear()
        self.drawn.clear()

    def end_observation(self):
        state = next((name for name in PRIORITY if name in self.observed), None)
        task, stamp = self.observed.get(state, (0, None))
        if state and self._stamp(state, task) != stamp:
            state, task, stamp = None, 0, None
        if state == 'title':
            step = self.arm.u32(task + 8)
            if step != 1:
                state, task = None, 0
        if (state, task, stamp) != (self.state, self.task, self.task_stamp):
            self.cancel()
            self.state, self.task = state, task
            self.task_stamp = stamp
            self.focus = None
        self._collect()

    def _children(self, component):
        count = self.arm.u32(component + 0x18)
        if not 0 < count <= 256:
            return ()
        start = self.arm.u32(component + 0x0c)
        return struct.unpack(f'<{count}I', self.arm.read(start, 4 * count)) if start else ()

    def _descendants(self, component):
        found, stack = set(), [component]
        while stack and len(found) < 1024:
            for child in self._children(stack.pop()):
                if child and child not in found:
                    found.add(child)
                    stack.append(child)
        return found

    def _enabled(self, component):
        return self.arm.read(component + 0x50, 2) == b'\x01\x01'

    def _collect(self):
        targets, self.panels, self.counters, self.tables = [], [], {}, {}
        if not self.enabled:
            self.targets = targets
            return
        disabled = set()
        for component in self.drawn:
            if not self._enabled(component):
                disabled.add(component)
                disabled |= self._descendants(component)
        nested = set()
        for component, kind in self.drawn.items():
            if component in disabled:
                continue
            if kind == 'Counter':
                inside = self._descendants(component)
                nested |= inside
                self.counters[component] = sorted(
                    (center(self._rect(child, 'PushButton'))[0], child) for child in inside
                    if self.drawn.get(child) == 'PushButton' and child not in disabled)
            elif kind == 'TableView':
                for child in self._descendants(component):
                    self.tables[child] = component
            elif kind == 'InputPanel':
                self.panels.append(self._rect(component, kind))
        for component, kind in self.drawn.items():
            if kind not in FOCUSABLE or component in disabled or component in nested:
                continue
            if kind == 'TableViewItem' and struct.unpack('<i', self.arm.read(component + 0x98, 4))[0] < 0:
                continue  # an empty row past either end of the list
            rect = self._rect(component, kind)
            x, y, w, h = rect
            visible = max(0, min(x + w, 800) - max(x, 0)) * max(0, min(y + h, 480) - max(y, 0))
            if w >= 16 and h >= 16 and visible >= 0.6 * w * h:
                targets.append(Target(component, kind, rect))
        self.targets = targets
        if self.pending_index is not None:
            table, index = self.pending_index
            row = next((t for t in targets if self.tables.get(t.component) == table and
                        self._index(t.component) == index), None)
            if row:
                self.focus, self.pending_index = row.component, None
        if not any(t.component == self.focus for t in targets):
            self.focus = self._default()

    def _rect(self, component, kind):
        # A plain button's touch area can be inset from its frame (round icons).
        return struct.unpack('<4i', self.arm.read(component + (0xb8 if kind == 'Button' else 0x3c), 16))

    def _index(self, component):
        return struct.unpack('<i', self.arm.read(component + 0x98, 4))[0]

    def _default(self):
        if not self.targets:
            return None
        if self.state in DEFAULT_FOCUS:
            preferred = self.arm.u32(self.task + DEFAULT_FOCUS[self.state])
            if any(t.component == preferred for t in self.targets):
                return preferred
        # The largest control is the screen's main choice; ties go to the
        # top, then to the right (where Next sits on the round-button screens).
        return min(self.targets, key=lambda t: (-t.rect[2] * t.rect[3], t.rect[1], -t.rect[0])).component

    def focused(self):
        return next((t for t in self.targets if t.component == self.focus), None)

    def focus_rect(self):
        target = self.focused()
        return target.rect if target and self.active and self.focus_visible else None

    def pointer_moved(self):
        """Mouse input hides the focus until the next key or button press."""
        self.focus_visible = False

    def cancel(self):
        self.gesture.clear()
        self.native_request = None
        self.pending_index = None
        self.held.clear()
        self.repeat = None
        if self.touch_down:
            self.touch('up', *self.touch_position)
            self.touch_down = False

    def _tap(self, position):
        x, y = map(round, position)
        self.gesture.extend((('down', x, y), None, ('up', x, y)))

    def _move(self, code):
        current = self.focused()
        if current is None:
            return
        dx, dy = DIRECTIONS[code]
        if current.kind == 'Counter' and dx:
            buttons = self.counters.get(current.component)
            if buttons and not self.gesture:
                child = buttons[0 if dx < 0 else -1][1]
                self._tap(center(self._rect(child, 'PushButton')))
            return
        cx, cy = center(current.rect)
        x, y, w, h = current.rect
        best = None
        for target in self.targets:
            if target.component == current.component:
                continue
            tx, ty = center(target.rect)
            primary = (tx - cx) * dx + (ty - cy) * dy
            if primary <= 4:
                continue
            ox, oy, ow, oh = target.rect
            overlap = (oy < y + h and y < oy + oh) if dx else (ox < x + w and x < ox + ow)
            # Controls in line with the focus win over nearer diagonal ones.
            score = (not overlap, primary + (0 if overlap else 3 * abs((ty - cy) if dx else (tx - cx))))
            if best is None or score < best[0]:
                best = (score, target.component)
        if best:
            self.focus = best[1]
        elif dy and current.kind == 'TableViewItem':
            self._scroll(current, dy)

    def _scroll(self, row, dy):
        table = self.tables.get(row.component)
        if not table or self.gesture:
            return
        index = self._index(row.component) + dy
        count = struct.unpack('<i', self.arm.read(table + 0xb8, 4))[0]
        top = struct.unpack('<i', self.arm.read(table + 0xcc, 4))[0]
        if not 0 <= index < count:
            return
        self.arm.call('_ZN17LYT_Cmp_TableView18Select_ViewTopItemEl', table, max(0, top + dy))
        self.arm.call('_ZN17LYT_Cmp_TableView11UpdateItemsEv', table)
        self.pending_index = (table, index)

    def _press(self):
        target = self.focused()
        if target is None:
            # A full-screen input panel (the title's "touch the screen").
            if self.panels and not self.targets:
                self._tap(center(max(self.panels, key=lambda r: r[2] * r[3])))
                self.confirmations += 1
            return
        if target.kind == 'Counter':
            return
        x, y, w, h = target.rect
        if target.kind == 'SliderButton':
            # One bounded drag along the slider track; the original
            # replay-verified path was 240 -> 550 on its 192..606 track.
            cy = round(y + h / 2)
            start, end = round(x + w * 0.116), round(x + w * 0.865)
            self.gesture.extend([('down', start, cy), None, None,
                                 ('move', (start + end) // 2, cy), None, ('move', end, cy), None,
                                 ('up', end, cy)])
        else:
            self._tap(center(target.rect))
        self.confirmations += 1

    def key(self, down, code):
        if not down:
            self.held.discard(code)
            if self.repeat and self.repeat[0] == code:
                self.repeat = None
            return
        if not self.active or code not in MENU_CODES or code in self.held:
            return
        self.held.add(code)
        if code in DIRECTIONS:
            if self.focus_visible:
                self._move(code)
            self.focus_visible = True
            self.repeat = [code, 0]
            return
        if self.gesture or self.native_request:
            return
        if code == 32:
            if self.state == 'data_reset':
                self.native_request = ('reset_cancel', code)
            elif self.state in CANCEL_TAP:
                self._tap(CANCEL_TAP[self.state])
            else:
                # Cancel remains the engine's real key callback; Game routes
                # this code natively when the menu has no verified cancel.
                self.held.discard(code)
            return
        self.focus_visible = True
        self._press()

    def routes(self, code):
        return self.active and code in MENU_CODES and (code != 32 or self.state == 'data_reset' or self.state in CANCEL_TAP)

    def tick(self):
        if self.state is not None and self.task_stamp is not None and self._stamp(self.state, self.task) != self.task_stamp:
            self.cancel()
            self.state, self.task, self.task_stamp = None, 0, None
        if not self.active:
            self.cancel()
            return
        if self.native_request:
            self.native_request = None
            self.arm.call('_ZN21Bio4_CTTask_DataReset4OnNoEP14LYT_CmpProductmPv', self.task, 0, 1, 0)
        if self.repeat and self.repeat[0] in self.held:
            self.repeat[1] += 1
            if self.repeat[1] >= REPEAT_DELAY and (self.repeat[1] - REPEAT_DELAY) % REPEAT_EVERY == 0:
                self._move(self.repeat[0])
        if self.gesture:
            entry = self.gesture.popleft()
            if entry:
                action, x, y = entry
                self.touch(action, x, y)
                self.touch_position = (x, y)
                self.touch_down = action != 'up'
