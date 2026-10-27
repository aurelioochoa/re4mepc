"""Verify the Rust math replacements against the original ARM routines.

The Rust copy of mceUtil3D_sqrt, which distances use, is first compared with
the engine's routine on every exponent, sign and table row. Shadow mode then
runs every hooked call through the original routine and compares
its guest writes and R0 with the Rust result, from the title screen through
the existing mission-2 village fixture and gameplay movement. Every function
must be exercised with zero mismatches. Alternating runs then measure engine
work with the replacements off and on. Requires your imported game; each run
uses a fresh isolated copy with empty saves, removed after the run.
"""
import argparse
import ctypes as C
import json
import platform
import random
import shutil
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.benchmark import Replay, quantiles, source_identity
from re4pc.arm import ArmRuntime
from re4pc.eabi import install as install_soft_float
from re4pc.game import Game
from re4pc.native_math import FUNCTIONS, sqrt_entry
from re4pc.paths import native_library
from re4pc.paths import game_dir, isolated_game, test_output
from re4pc.runtime_log import configure
from re4pc.settings import validate as validate_settings


def check_sqrt(game_root, seed=7, per_exponent=400):
    """Mismatches of the Rust square root against the engine's, and the case count."""
    arm = ArmRuntime()
    try:
        arm.load(game_root / 'lib/libmc_eruption_for_android_jni.so', 0)
        install_soft_float(arm)
        entry = sqrt_entry(arm)
        lib = C.CDLL(str(native_library('libre4math.so')))
        lib.re4_math_sqrt.argtypes = (C.c_uint64, C.c_uint64, C.c_uint32, C.c_uint32, C.POINTER(C.c_uint32))
        generator = random.Random(seed)
        values = [0, 0x80000000, 0x7f800000, 0xff800000, 0x7fc00000, 0x00000001, 0x007fffff]
        for exponent in range(256):
            for sign in (0, 1 << 31):
                # Each table row's first and last fractions, then random ones.
                values += [sign | exponent << 23 | row << 20 | edge for row in range(8) for edge in (0, 0xfffff)]
                values += [sign | exponent << 23 | generator.getrandbits(23) for _ in range(per_exponent)]
        mismatches, result = [], C.c_uint32()
        for value in values:
            expected = arm.call(entry | 1, value)
            if not lib.re4_math_sqrt(arm.base, arm.SIZE, entry, value, C.byref(result)) or result.value != expected:
                mismatches.append((f'0x{value:08x}', f'0x{expected:08x}', f'0x{result.value:08x}'))
        return mismatches, len(values)
    finally:
        arm.close()


def run(game_root, output, mode, gameplay_ticks):
    root = isolated_game(game_root, output)
    game = Game(root, hidden=True, skip_videos=True, settings=validate_settings({}), native_math=mode)
    replay = Replay(game)
    try:
        started = time.monotonic()
        replay.village()
        loading = {'seconds': time.monotonic() - started, 'busy_seconds': sum(replay.work) / 1000,
                   'worst_frame_ms': max(replay.work), 'work_ms': quantiles(replay.work)}
        replay.close()
        replay.work.clear()
        # Sustained walking then tank turning, as in the benchmark.
        for key, ticks in ((ord('w'), gameplay_ticks // 2), (ord('a'), gameplay_ticks - gameplay_ticks // 2)):
            game.event(('key', True, key))
            replay.advance(ticks)
            game.event(('key', False, key))
        return {'mode': mode, 'loading': loading, 'gameplay_work_ms': quantiles(replay.work),
                'gameplay_mean_ms': sum(replay.work) / len(replay.work),
                'native_math': game.statistics()['native_math']}
    finally:
        replay.close()
        game.close()
        # Each run copies the game; keep only the report.
        shutil.rmtree(root, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=game_dir())
    parser.add_argument('--output', type=Path)
    parser.add_argument('--gameplay-ticks', type=int, default=200)
    parser.add_argument('--pairs', type=int, default=1, help='Alternating off/on timing runs after the shadow check')
    args = parser.parse_args()
    if args.gameplay_ticks < 20 or args.pairs < 0:
        parser.error('Use at least 20 gameplay ticks and a non-negative pair count')
    output = test_output('native-math', args.output)
    configure('warning')
    document = {'source': source_identity(), 'platform': platform.platform(), 'gameplay_ticks': args.gameplay_ticks}
    sqrt_mismatches, sqrt_cases = check_sqrt(args.game)
    document['sqrt'] = {'cases': sqrt_cases, 'mismatches': sqrt_mismatches[:20]}
    print('NATIVE_MATH_SQRT', sqrt_cases, 'cases', len(sqrt_mismatches), 'mismatches', flush=True)
    shadow = run(args.game, output, 'shadow', args.gameplay_ticks)
    document['shadow'] = shadow
    failures = [name for name in FUNCTIONS
                if shadow['native_math'][name]['mismatches'] or not shadow['native_math'][name]['verified']]
    if sqrt_mismatches:
        failures.append('mceUtil3D_sqrt')
    document['timing'] = []
    for pair in range(args.pairs):
        for mode in ('off', 'on'):
            record = run(args.game, output, mode, args.gameplay_ticks)
            record['pair'] = pair + 1
            document['timing'].append(record)
            print('NATIVE_MATH_TIMING', pair + 1, mode, json.dumps(record['gameplay_work_ms']),
                  f"loading_busy={record['loading']['busy_seconds']:.2f}s", flush=True)
    (output / 'results.json').write_text(json.dumps(document, indent=2))
    for name in FUNCTIONS:
        print('NATIVE_MATH_SHADOW', name, json.dumps(shadow['native_math'][name]))
    if failures:
        print('NATIVE_MATH_FAIL:', ', '.join(failures), '— see', output / 'results.json')
        sys.exit(1)
    print('NATIVE_MATH_PASS:', output / 'results.json')


if __name__ == '__main__':
    main()
