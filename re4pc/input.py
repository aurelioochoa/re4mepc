"""Keep desktop press/release transitions observable by the mobile frame loop."""
from collections import deque


class DesktopInput:
    def __init__(self, touch, key, button=None):
        self.touch, self.key = touch, key
        self.button = button
        self.pending = deque()
        self.mouse_down = False
        self.position = (0, 0)
        self.keys_down = set()
        self.buttons_down = set()

    def enqueue(self, event):
        if event[0] == 'motion' and self.pending and self.pending[-1][0] == 'motion':
            self.pending[-1] = event
        else:
            self.pending.append(event)

    def flush(self):
        changed = set()
        while self.pending:
            event = self.pending[0]
            kind = event[0]
            identifier = (kind, event[2]) if kind in ('key','mouse_button') else ('mouse',)
            if kind != 'motion' and identifier in changed:
                break
            self.pending.popleft()
            if kind == 'motion':
                if self.mouse_down:
                    self.position = event[1:]
                    self.touch('move', *self.position)
            elif kind == 'touch':
                down, x, y = event[1:]
                if down == self.mouse_down:
                    continue
                self.mouse_down = down
                self.position = (x, y)
                self.touch('down' if down else 'up', x, y)
                changed.add(identifier)
            elif kind == 'key':
                down, code = event[1:]
                if down == (code in self.keys_down):
                    continue
                if down:
                    self.keys_down.add(code)
                else:
                    self.keys_down.remove(code)
                self.key(down, code)
                changed.add(identifier)
            elif kind == 'mouse_button':
                down, button = event[1:]
                if down == (button in self.buttons_down):continue
                if down:self.buttons_down.add(button)
                else:self.buttons_down.remove(button)
                if self.button is not None:self.button(down,button)
                changed.add(identifier)

    def release(self):
        self.pending.clear()
        if self.mouse_down:
            self.pending.append(('touch', False, *self.position))
        for code in sorted(self.keys_down):
            self.pending.append(('key', False, code))
        for button in sorted(self.buttons_down):
            self.pending.append(('mouse_button',False,button))
