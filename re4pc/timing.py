"""Pace the frame-driven engine at its original simulation rate."""
import time

# GM_MisConduct::Frame increments/decrements mission seconds every 20 ticks.
# PLT_Application::Check_FpsUpDate always returns true: every draw advances
# gameplay. Raising the presentation rate therefore speeds up the simulation.
ENGINE_HZ = 20


class FramePacer:
    def __init__(self, clock=time.monotonic, sleep=time.sleep):
        self.clock, self.sleep = clock, sleep
        self.interval = 1 / ENGINE_HZ
        self.deadline = clock()
        self.overruns = 0

    def wait(self, due=None, between=None):
        """Sleep until the next tick; ``between`` runs whenever ``due()`` passes.

        Movies use this to present at their source rate without advancing the
        20 Hz simulation, as Android drew them on a separate surface.
        """
        self.deadline += self.interval
        now = self.clock()
        if now > self.deadline:
            self.overruns += 1
            # Loading, video startup and focus stalls must not cause a burst
            # of accelerated updates when the engine becomes responsive.
            if now - self.deadline >= self.interval:
                self.deadline = now
            return
        while now < self.deadline:
            when = due() if due else None
            if when is not None and when <= now:
                between()
                now = self.clock()
                when = due()
                # A decoder that has fallen behind is polled, not spun on.
                if when is not None and when <= now: when = now + 0.002
            target = self.deadline if when is None else min(when, self.deadline)
            if target > now: self.sleep(target - now)
            now = self.clock()
