"""Verify smooth snapshot history while native camera culling changes draws.

Uses fresh isolated game saves. Optionally capture the same native submissions
with a pre-change libre4fast.so for paired presentation timings and eligibility.
No presentation thread runs during image comparisons. Runtime/timing evidence
is saved outside the checkout; this synthetic village fixture is not campaign
or physical-display qualification.
"""
import argparse
import ctypes as C
import hashlib
import json
import platform
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from re4pc.game import Game
from re4pc.paths import game_dir, isolated_game, test_output
from re4pc import render_stream
from re4pc.runtime_log import configure
from re4pc.settings import validate
from tools.benchmark import Replay, quantiles, source_identity


class CapturePair:
    """Feed immutable copies of the same native draw to both renderers."""
    def __init__(self, current, baseline):
        self.current, self.baseline = current, baseline

    def __getattr__(self, name):
        if name in ('begin', 'end', 'clear', 'draw', 'dirty', 'reset', 'close'):
            def both(*args):
                getattr(self.baseline, name)(*args)
                return getattr(self.current, name)(*args)
            return both
        return getattr(self.current, name)


def guest_digest(game):
    return hashlib.sha256((C.c_ubyte * game.arm.SIZE).from_address(game.arm.base)).hexdigest()


def verify(game, replay, output, ticks, baseline=None):
    stream = game.graphics.render_stream
    if baseline:
        resolver = render_stream.native_library
        try:
            render_stream.native_library = lambda name: baseline
            previous = render_stream.RenderStream()
        finally:
            render_stream.native_library = resolver
        game.graphics.render_stream = CapturePair(stream, previous)
    else:
        previous = None
    replay.advance(3)
    samples = []
    began = time.perf_counter()
    for tick in range(ticks):
        # Sweep both ways at 330 degrees/second, with changes in pitch and aim.
        if tick == ticks // 3: game.event(('mouse_button', True, 3))
        if tick == 2 * ticks // 3: game.event(('mouse_button', False, 3))
        game.pc.move(110 if tick % 40 < 20 else -110, 3 if tick % 20 < 10 else -3)
        before = stream.metrics()
        game.frame()
        native = game.graphics.capture_image()
        memory, calls, frames = guest_digest(game), game.arm.calls.copy(), game.frames
        assert stream.render(1), ('Missing gameplay snapshot', tick)
        assert game.graphics.capture_image().tobytes() == native.tobytes(), ('Endpoint mismatch', tick)
        current_ms = baseline_ms = 0
        results = {}
        order = [('current', stream), ('baseline', previous)]
        if tick % 2: order.reverse()
        for label, renderer in order:
            if renderer:
                start = time.perf_counter()
                results[label] = renderer.render(.5)
                cost = (time.perf_counter() - start) * 1000
                if label == 'current': current_ms = cost
                else: baseline_ms = cost
        stream.render(.5)
        intermediate = game.graphics.capture_image()
        assert guest_digest(game) == memory, ('Presentation changed guest bytes', tick)
        assert game.arm.calls == calls and game.frames == frames, ('Presentation advanced simulation', tick)
        assert not game.graphics.gl.glGetError(), ('GL error', tick)
        after = stream.metrics()
        sample = {'tick': tick, 'work_ms': game.frame_times[-1] * 1000,
                  'draw_count_changed': after['changed_sequences'] > before['changed_sequences'],
                  'matched_draws': after['matched_draws'] - before['matched_draws'],
                  'unmatched_draws': after['unmatched_draws'] - before['unmatched_draws'],
                  'current_result': results['current'], 'current_replay_ms': current_ms,
                  'distinct_intermediate': intermediate.tobytes() != native.tobytes(),
                  'baseline_result': results.get('baseline'), 'baseline_replay_ms': baseline_ms}
        if sample['draw_count_changed'] and sample['distinct_intermediate'] and not (output/'turn-native.png').exists():
            native.save(output/'turn-native.png')
            intermediate.save(output/'turn-intermediate.png')
        samples.append(sample)
        if tick % 20 == 0:
            print('CAMERA_TURN_SAMPLE', json.dumps(sample), flush=True)
    changed = [s for s in samples if s['draw_count_changed']]
    smooth = [s for s in changed if s['current_result'] == 2 and s['matched_draws'] > 0 and s['distinct_intermediate']]
    result = {'samples': samples, 'draw_count_changes': len(changed),
              'changes_with_interpolation': len(smooth), 'metrics': stream.metrics(),
              'work_ms': quantiles([s['work_ms'] for s in samples]),
              'current_replay_ms': quantiles([s['current_replay_ms'] for s in samples]),
              'baseline_replay_ms': quantiles([s['baseline_replay_ms'] for s in samples]) if previous else None,
              'all_guest_bytes_unchanged': True, 'all_endpoints_exact': True,
              'comparison_seconds': time.perf_counter() - began}
    # Write the measured samples even if a performance assertion fails.
    (output/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')
    assert len(changed) >= 5, ('Fixture did not exercise visibility changes', len(changed))
    assert len(smooth) >= .8 * len(changed), ('Visibility changes lost interpolation', len(smooth), len(changed))
    if previous:
        assert all(s['baseline_result'] == 1 for s in changed), 'Baseline unexpectedly interpolated changed sequences'
        game.graphics.render_stream = stream
        previous.close()
    return result


def threaded(game, replay, ticks):
    """Measure the normal paced worker without readback or memory hashing."""
    game.start_presentation()
    worker = game.presenter
    before = game.frames
    started = time.monotonic()
    try:
        for tick in range(ticks):
            game.pc.move(110 if tick % 40 < 20 else -110, 0)
            replay.advance()
        worker.check()
        # The worker retains the most recent 240 timestamps, about four seconds
        # at 60 FPS. Report interval statistics for that bounded window.
        timestamps = tuple(worker.timestamps)
        assert len(timestamps) > 1, 'Worker did not present gameplay'
        gaps = [(b-a)*1000 for a, b in zip(timestamps, timestamps[1:])]
        result = {'seconds': time.monotonic()-started, 'simulation_ticks': game.frames-before,
                  'worker': worker.metrics(), 'refresh_gap_ms': quantiles(gaps), 'max_gap_ms': max(gaps)}
        assert game.frames-before == ticks, 'Unexpected simulation tick count'
        assert worker.frames >= ticks * 2, ('Worker fell below 40 presentations per simulated second', result)
        assert not game.graphics.debug_messages, ('GL debug messages', game.graphics.debug_messages)
        return result
    finally:
        worker.close()
        game.presenter = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=game_dir())
    parser.add_argument('--output', type=Path)
    parser.add_argument('--ticks', type=int, default=120)
    parser.add_argument('--baseline-library', type=Path)
    args = parser.parse_args()
    if args.ticks < 60: parser.error('Use at least 60 camera-turn ticks')
    checkout = Path(__file__).resolve().parents[1]
    if args.output and args.output.resolve().is_relative_to(checkout):
        parser.error('Store gameplay artifacts outside the source checkout')
    output = test_output('camera-turns', args.output)
    configure('warning')
    document = {'source': source_identity(), 'platform': platform.platform(), 'passed': False}
    if args.baseline_library:
        document['baseline_library_sha256'] = hashlib.sha256(args.baseline_library.read_bytes()).hexdigest()
    root = isolated_game(args.game, output)
    game = replay = None
    try:
        game = Game(root, hidden=True, skip_videos=True, settings=validate({'presentation_rate': 60}))
        replay = Replay(game)
        replay.village()
        replay.close()
        document['result'] = verify(game, replay, output, args.ticks, args.baseline_library)
        document['threaded'] = threaded(game, replay, args.ticks)
        document['passed'] = True
    finally:
        if replay: replay.close()
        if game: game.close()
        shutil.rmtree(root)
        (output/'results.json').write_text(json.dumps(document, indent=2)+'\n')
    print('CAMERA_TURNS_PASS', output/'results.json')


if __name__ == '__main__':
    main()
