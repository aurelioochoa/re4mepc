"""Qualify independent geometry presentation in isolated supported-engine data.

The synthetic Extreme mission fixture is shared with the combat regression.
Snapshots must reproduce native endpoint pixels, produce distinct intermediate
pixels, preserve every guest byte and avoid native/host service calls. Benchmarks
toggle only import slots in one live scene, with no native instruction hooks.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import ImageChops
from re4pc.game import Game
from re4pc.paths import game_dir, isolated_game, test_output
from tools.benchmark import Replay, source_identity, native_transition, quantiles


def digest(game):
    return hashlib.sha256((C.c_ubyte*game.arm.SIZE).from_address(game.arm.base)).hexdigest()


def import_slots(arm, names):
    slots = []
    for module in arm.modules:
        for section in module['elf'].iter_sections():
            if section['sh_type'] != 'SHT_REL':
                continue
            for relocation in section.iter_relocations():
                symbol = module['symbols'].get_symbol(relocation['r_info_sym'])
                if relocation['r_info_type'] in (21,22) and symbol['st_shndx'] == 'SHN_UNDEF' and symbol.name in names:
                    slots.append((module['base']+relocation['r_offset'], symbol.name))
    return slots


def check(game, replay, output):
    stream = game.graphics.render_stream
    arm = game.arm
    cases, distinct, endpoint_errors = [], 0, []
    # All native inspection hooks have been removed before measuring replay.
    replay.advance(20)
    for label, event in (
            ('walk', ('key', True, ord('w'))),
            ('turn', ('mouse_delta', 45, -12)),
            ('stop', ('key', False, ord('w'))),
            ('aim', ('mouse_button', True, 3)),
            ('fire', ('touch', True, 400, 240)),
            ('release-fire', ('touch', False, 400, 240)),
            ('holster', ('mouse_button', False, 3))):
        game.event(event)
        for _ in range(8): replay.advance()
        native = game.graphics.capture_image()
        before = digest(game)
        calls = arm.calls.copy()
        native_ticks = game.frames
        start = time.perf_counter()
        result = stream.render(1)
        cost = time.perf_counter()-start
        assert result, ('Native snapshot unavailable', label, stream.metrics())
        endpoint = game.graphics.capture_image()
        difference = ImageChops.difference(native, endpoint)
        error = max(difference.getextrema()[i][1] for i in range(3))
        endpoint_errors.append(error)
        if error:
            native.save(output/(label+'-native.png'))
            endpoint.save(output/(label+'-endpoint.png'))
        assert error <= 1, ('Replay endpoint differs from native draw', label, error)
        previous = None
        middle_result = stream.render(.5)
        middle = game.graphics.capture_image()
        if middle_result == 2:
            stream.render(0)
            previous = game.graphics.capture_image()
            if middle.tobytes() not in (previous.tobytes(), endpoint.tobytes()):
                distinct += 1
                if label in ('walk','turn'):
                    previous.save(output/(label+'-previous.png'))
                    middle.save(output/(label+'-intermediate.png'))
                    endpoint.save(output/(label+'-current.png'))
        # Multiple refreshes at different rates must leave all guest bytes equal.
        for alpha in (.1, .2, .4, .6, .8, 1):
            stream.render(alpha)
        assert digest(game) == before, ('Presentation changed guest memory', label)
        assert arm.calls == calls and game.frames == native_ticks, ('Presentation advanced native services', label)
        assert game.graphics.gl.glGetError() == 0, ('GL error', label)
        cases.append({'case':label, 'endpoint_max_channel_error':error,
                      'interpolation_eligible':middle_result == 2, 'replay_ms':cost*1000,
                      'all_guest_bytes_unchanged':True, 'native_calls_unchanged':True})
        print('PRESENTATION_CASE', json.dumps(cases[-1]), flush=True)
    assert distinct >= 2, ('No demonstrated intermediate motion', distinct, stream.metrics())

    # Paired measurements in the same scene. Only original import GOT slots are
    # switched; rerunning the ELF relocator would incorrectly apply ABS32 twice.
    bridge = arm.graphics_bridge
    slots = import_slots(arm, bridge.NAMES)
    assert slots, 'No native graphics import slots found'
    timings = []
    try:
        for repetition in range(3):
            for fast in ((False,True) if repetition%2 == 0 else (True,False)):
                for address,name in slots:
                    arm.w32(address, arm.imports[name] if fast else bridge.original_imports[name])
                replay.advance(5)
                start = len(replay.work)
                replay.advance(30)
                timings.append({'repetition':repetition, 'native_bridge':fast,
                                'work_ms':quantiles(replay.work[start:]),
                                'median_ms':statistics.median(replay.work[start:])})
    finally:
        for address,name in slots: arm.w32(address,arm.imports[name])

    rates = []
    params = arm.call('_ZN12GM_CtrlParam8Get_InstEv')
    mission = arm.call('_ZN13GM_MisConduct8Get_InstEv')
    # This story mission normally leaves its countdown disabled. Enable a
    # ten-minute clock through the native API as an explicit fixture control;
    # presentation must neither advance nor stall it relative to native ticks.
    arm.call('_ZN13GM_MisConduct13Set_LimitTimeEscb',mission,600,1,0)
    assert arm.read(mission+0x10,1) == b'\x01'
    for rate in (60,120,0):
        game.presentation_rate = rate
        game.start_presentation()
        worker = game.presenter
        before_frames = game.frames
        before_seconds = arm.call('_ZN12GM_CtrlParam15Get_MisTotalSecEv',params)
        before_limit = arm.call('_ZN12GM_CtrlParam16Get_MisLimitTimeEv',params)
        before_mission = {'ticks':arm.u32(mission),'active':arm.read(mission+0x10,1)[0]}
        started = time.monotonic()
        replay.advance(60)
        elapsed = time.monotonic()-started
        after_seconds = arm.call('_ZN12GM_CtrlParam15Get_MisTotalSecEv',params)
        after_limit = arm.call('_ZN12GM_CtrlParam16Get_MisLimitTimeEv',params)
        worker.check()
        measured = worker.metrics()
        print('PRESENTATION_RATE_OBSERVATION',rate,measured,'ticks',game.frames-before_frames,
              'seconds',before_seconds,after_seconds,'mission_before',before_mission,
              'mission_after',{'ticks':arm.u32(mission),'active':arm.read(mission+0x10,1)[0]},
              'player_active',game.pc.active,'story',game.pc.story_active,flush=True)
        assert measured['recent_fps'] > (45 if rate == 60 else 80), ('Independent FPS target not reached',rate,measured)
        assert game.frames-before_frames == 60 and after_seconds-before_seconds == 3 and before_limit-after_limit == 3, (
            'Mission clock changed',rate,before_seconds,after_seconds,before_limit,after_limit)
        rates.append({'target_fps':rate, 'measured':measured, 'simulation_ticks':60,
                      'mission_seconds':after_seconds-before_seconds, 'wall_seconds':elapsed})
        print('PRESENTATION_RATE',json.dumps(rates[-1]),flush=True)
        worker.close()
        game.presenter = None

    game.presentation_rate = 60
    game.start_presentation()
    replay.output = output
    transition = native_transition(game, replay, 1)
    assert transition['verified'], 'Native stage transition failed'
    assert game.graphics.gl.glGetError() == 0
    assert not game.graphics.debug_messages, sorted(game.graphics.debug_messages)
    return {'schema_version':1, 'source':source_identity(), 'cases':cases,
            'distinct_intermediate_cases':distinct, 'endpoint_max_channel_error':max(endpoint_errors),
            'snapshot_metrics':stream.metrics(), 'paired_timings':timings,
            'presentation_rates':rates,
            'transition':transition,
            'limitations':['Synthetic mission fixture; full campaign and physical input hardware not qualified.',
                           'Simulation remains 20 Hz; interpolation adds up to one tick (50 ms) of visual latency.',
                           'Driver submission times are not GPU execution times; background desktop activity is uncontrolled.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=game_dir())
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = test_output('presentation', args.output)
    checkout = Path(__file__).resolve().parents[1]
    if output.resolve() == checkout or checkout in output.resolve().parents:
        parser.error('Keep game data and captures outside the checkout')
    os.environ.setdefault('SDL_VIDEODRIVER', 'offscreen')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    game = Game(isolated_game(args.game, output), hidden=True, skip_videos=True,
                settings={'presentation_rate':60, 'achievement_capture':'off'}, diagnostics=False)
    replay = Replay(game)
    try:
        replay.advance(200)
        user = game.arm.symbols['_ZZN13Bio4_UserData11GetInstanceEvE4inst']
        game.arm.call('_ZN13Bio4_UserData20SetMissionDifficultyEh', user, 4)
        replay.village()
        replay.close()
        report = check(game, replay, output)
        (output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
        print('PRESENTATION_PASS', output/'results.json', flush=True)
    finally:
        replay.close()
        game.close()


if __name__ == '__main__':
    main()
