"""Recognized native menu states and bounded desktop confirmation gestures.

Only hash-validated engine symbols are observed. Unknown states retain the
original input path and never receive a synthesized click or drag.
"""
from collections import deque
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0
from .actions import DEFAULT_BINDINGS

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
DEFAULT_CURSOR = {'title': (400, 390), 'title_top': (400, 128), 'difficulty': (400, 415),
                  'confirmation': (240, 320), 'notice': (742, 416), 'data_reset': (400, 405),
                  'mission': (400, 200), 'mission_description': (60, 240), 'mission_prepare': (60, 416),
                  'inventory': (350, 120)}
DIRECTIONS = {19, 20, 21, 22}
MENU_CODES = DIRECTIONS | {23, 66, 32}
PHASE_FIELDS = {'title': (8,4), 'title_top': (8,4), 'difficulty': (0x20,1),
                'confirmation': (0x14,1), 'notice': (0x10,1),
                'mission': (8,4), 'mission_description': (8,4),
                'mercenary': (8,4), 'mercenary_description': (8,4),
                'inventory': (0x0c,1), 'inventory_submenu': (0x0c,1)}


def key_name(code):
    names = {13: 'Enter', 32: 'Space', 27: 'Esc', 1073741906: 'Up',
             1073741905: 'Down', 1073741904: 'Left', 1073741903: 'Right'}
    return names.get(code, chr(code).upper() if 33 <= code <= 126 else str(code))


def binding_label(settings, action):
    bindings = settings.get('bindings', DEFAULT_BINDINGS)
    keyboard = bindings['keyboard'].get(action, [])
    controller = bindings['controller'].get(action, [])
    return '/'.join(([key_name(keyboard[0])] if keyboard else []) +
                    ([controller[0].replace('dp', 'D-pad ').title()] if controller else [])) or 'Unbound'


class MenuControls:
    def __init__(self, arm, touch, *, enabled=True, cursor=None, settings=None):
        self.arm, self.touch, self.enabled = arm, touch, enabled
        self.cursor = cursor if cursor is not None else [400.0, 240.0]
        self.settings = settings or {}
        self.state, self.task = None, 0
        self.task_stamp = None
        self.observed = {}
        self.held = set()
        self.gesture = deque()
        self.touch_down = False
        self.touch_position = (0, 0)
        self.native_request = None
        self.native_age = 0
        self.hooks = []
        self.confirmations = 0

    @property
    def active(self):
        return self.enabled and self.state is not None

    def install(self):
        if not self.enabled:
            return
        for state, symbol in HOOKS.items():
            if symbol not in self.arm.symbols:
                continue
            address = self.arm.symbols[symbol] & ~1
            self.hooks.append(self.arm.uc.hook_add(UC_HOOK_CODE, self._observe,
                user_data=state, begin=address, end=address))

    def _observe(self, uc, address, size, state):
        try:
            task = uc.reg_read(UC_ARM_REG_R0)
            self.observed[state] = (task, self._stamp(state, task))
        except BaseException as error:
            self.arm.pending_error = error
            uc.emu_stop()

    def _stamp(self, state, task):
        offset, size = PHASE_FIELDS.get(state, (0,0))
        return self.arm.u32(task), self.arm.read(task + offset, size) if size else b''

    def begin_observation(self):
        self.observed.clear()

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
            if state in DEFAULT_CURSOR:
                self.cursor[:] = DEFAULT_CURSOR[state]

    def cancel(self):
        self.gesture.clear()
        self.native_request = None
        self.native_age = 0
        self.held.clear()
        if self.touch_down:
            self.touch('up', *self.touch_position)
            self.touch_down = False

    def _click(self):
        x, y = map(round, self.cursor)
        self.gesture.extend((('down', x, y), None, ('up', x, y)))

    def key(self, down, code):
        if not down:
            self.held.discard(code)
            return
        if not self.active or code not in MENU_CODES or code in self.held:
            return
        self.held.add(code)
        if code in DIRECTIONS:
            if self.state == 'difficulty' and code in (21, 22):
                self.native_request = ('difficulty_change', code)
            return
        if self.gesture or self.native_request:
            return
        if code == 32:
            if self.state == 'data_reset':
                self.native_request = ('reset_cancel', code)
            else:
                # Cancel remains the engine's real key callback; Game routes
                # this code natively when the menu has no verified cancel.
                self.held.discard(code)
            return
        if code == 66 and self.state == 'confirmation':
            # Eight authoritative ticks, using the already replay-verified
            # logical 800x480 slider path. Holding confirm cannot repeat it.
            self.gesture.extend([('down', 240, 320), None, None,
                                 ('move', 395, 320), None, ('move', 550, 320), None,
                                 ('up', 550, 320)])
        elif code == 66 and self.state in ('title_top', 'difficulty', 'notice', 'mission_description'):
            self.native_request = ('confirm', code)
            self.native_age = 0
        else:
            self._click()
        self.confirmations += 1

    def routes(self, code):
        return self.active and code in MENU_CODES and (code != 32 or self.state == 'data_reset')

    def _component_enabled(self, component):
        return bool(component and self.arm.read(component + 0x50, 2) == b'\x01\x01')

    def _native(self, kind, code):
        task = self.task
        if kind == 'reset_cancel':
            self.arm.call('_ZN21Bio4_CTTask_DataReset4OnNoEP14LYT_CmpProductmPv', task, 0, 1, 0)
        elif self.state == 'title_top':
            if self.arm.u32(task + 8) == 4 and self.arm.u32(task + 0x50):
                self.arm.call('_ZN17Bio4_CTTask_Title7OnStartEP14LYT_CmpProductmPv', task, 0, 1, 0)
        elif kind == 'difficulty_change':
            counter = self.arm.u32(task + 0x18)
            if not self._component_enabled(counter):
                return
            current = self.arm.call('_ZNK15LYT_Cmp_Counter8GetValueEv', counter)
            minimum = self.arm.call('_ZNK15LYT_Cmp_Counter9GetMinValEv', counter)
            maximum = self.arm.call('_ZNK15LYT_Cmp_Counter9GetMaxValEv', counter)
            target = max(minimum, min(maximum, current + (1 if code == 22 else -1)))
            if target != current:
                self.arm.call('_ZN15LYT_Cmp_Counter8SetValueEl', counter, target)
                self.arm.call('_ZN19Bio4_CTTask_DiffTop10_HdlNumSelEP14LYT_CmpProductmPv', task, counter, 2, 0)
        elif self.state in ('difficulty', 'notice'):
            component = self.arm.u32(task + 0x0c)
            if self._component_enabled(component):
                symbol = ('_ZN19Bio4_CTTask_DiffTop11_HdlButtonsEP14LYT_CmpProductmPv'
                          if self.state == 'difficulty' else '_ZN21Bio4_CTTask_NewNotice11_HdlButtonsEP14LYT_CmpProductmPv')
                self.arm.call(symbol, task, component, 1, 0)
        elif self.state == 'mission_description' and self.arm.u32(task + 8) == 11:
            component = self.arm.u32(task + 0x28)
            if self._component_enabled(component):
                self.arm.call('_ZN30Bio4_CTTask_MissionSelectStory8OnSelectEP14LYT_CmpProductmPv', task, component, 1, 0)

    def tick(self):
        if self.active and self.task_stamp is not None and self._stamp(self.state, self.task) != self.task_stamp:
            self.cancel()
            self.state, self.task, self.task_stamp = None, 0, None
        if not self.active:
            self.cancel()
            return
        if self.native_request:
            # The title's MenuMain starts its scene on the first tick. A
            # visible layout alone is insufficient to authorize its action;
            # wait for the same IsEnd condition checked by the native task.
            ready = True
            if self.state == 'title_top':
                layout = self.arm.u32(self.task + 4)
                ready = bool(layout and self.arm.call('_ZNK17LAS_LytController5IsEndEv', layout))
            self.native_age += 1
            if ready:
                request, self.native_request = self.native_request, None
                self._native(*request)
            elif self.native_age >= 80:
                self.native_request = None
        dx = (22 in self.held) - (21 in self.held)
        dy = (20 in self.held) - (19 in self.held)
        if self.state == 'difficulty':
            dx = 0
        self.cursor[0] = max(0, min(799, self.cursor[0] + dx * 8))
        self.cursor[1] = max(0, min(479, self.cursor[1] + dy * 8))
        if self.gesture:
            entry = self.gesture.popleft()
            if entry:
                action, x, y = entry
                self.touch(action, x, y)
                self.touch_position = (x, y)
                self.touch_down = action != 'up'

    def hints(self):
        if not self.active:
            return ()
        settings = self.settings
        confirm = 'Confirm slider' if self.state == 'confirmation' else 'Continue' if self.state in ('title_top', 'difficulty', 'notice', 'mission_description') else 'Click'
        directions = ','.join(binding_label(settings, action) for action in ('forward', 'backward', 'left', 'right'))
        return (f"{binding_label(settings, 'confirm')}: {confirm}   {binding_label(settings, 'action')}: Click   {binding_label(settings, 'status')}: Back",
                f"{directions}: {'Difficulty / cursor' if self.state == 'difficulty' else 'Cursor'}   Right stick: Cursor")
