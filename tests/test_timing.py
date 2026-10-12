"""Frame pacing follows the native simulation cadence without drift/bursts."""
import unittest
from re4pc.timing import ENGINE_HZ, FramePacer


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []
        self.oversleep = 0.0

    def time(self): return self.now

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration + self.oversleep


class TimingTests(unittest.TestCase):
    def test_fast_frames_follow_native_seconds(self):
        self.assertEqual(ENGINE_HZ, 20)
        clock = Clock()
        pacer = FramePacer(clock.time, clock.sleep)
        for _ in range(200):
            clock.now += 0.003
            pacer.wait()
        self.assertAlmostEqual(clock.now, 110.0)
        self.assertEqual(pacer.overruns, 0)

    def test_sleep_overshoot_does_not_accumulate(self):
        clock = Clock()
        clock.oversleep = 0.002
        pacer = FramePacer(clock.time, clock.sleep)
        for _ in range(100):
            clock.now += 0.020
            pacer.wait()
        self.assertAlmostEqual(clock.now, 105.002)

    def test_long_transition_discards_backlog(self):
        clock = Clock()
        pacer = FramePacer(clock.time, clock.sleep)
        clock.now += 5.0
        pacer.wait()
        self.assertEqual(clock.sleeps, [])
        self.assertEqual(pacer.overruns, 1)
        for _ in range(20):
            clock.now += 0.004
            pacer.wait()
        self.assertAlmostEqual(clock.now, 106.0)

    def test_small_overrun_recovers_original_cadence(self):
        clock = Clock()
        pacer = FramePacer(clock.time, clock.sleep)
        clock.now += 0.060
        pacer.wait()
        clock.now += 0.010
        pacer.wait()
        self.assertAlmostEqual(clock.now, 100.100)

    def test_early_wakeup_waits_remaining_budget(self):
        clock = Clock()
        early = [True]
        def sleep(duration):
            if early[0]:
                early[0] = False
                clock.now += duration / 2
            else: clock.sleep(duration)
        FramePacer(clock.time, sleep).wait()
        self.assertAlmostEqual(clock.now, 100.05)
