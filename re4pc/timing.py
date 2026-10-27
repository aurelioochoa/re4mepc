"""Pace the frame-driven engine at its original simulation rate."""
import time

# GM_MisConduct::Frame increments/decrements mission seconds every 20 ticks.
# PLT_Application::Check_FpsUpDate always returns true: every draw advances
# gameplay. Raising the presentation rate therefore speeds up the simulation.
ENGINE_HZ = 20
PRESENTATION_RATES = (20, 30, 60, 90, 120, 144, 165, 240, 0)


class PresentationClock:
    """Independent deadlines; slow renders drop work instead of queuing bursts.

    Uncapped presentation yields a short poll interval so input and movies
    remain serviced, rather than making the 20 Hz simulation a busy loop.
    """
    def __init__(self, rate, clock=time.monotonic):
        if type(rate) is not int or rate not in PRESENTATION_RATES:
            raise ValueError('Unsupported presentation rate')
        self.clock = clock
        self.interval = 1/rate if rate else 0.001
        self.deadline = clock()

    def reset(self):
        self.deadline = self.clock()

    def presented(self):
        self.deadline = max(self.deadline+self.interval, self.clock())


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
