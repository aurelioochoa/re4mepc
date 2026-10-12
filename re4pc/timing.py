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

    def wait(self):
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
            self.sleep(self.deadline - now)
            now = self.clock()
