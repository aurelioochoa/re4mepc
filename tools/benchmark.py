"""Repeat isolated startup, title-to-village and gameplay cache comparisons.

Cold means application caches only, never Linux disk/page-cache eviction. An
optional transition replay must reach a different native loaded stage; missing
or unsuccessful transition evidence is explicitly reported as unverified.
"""
import argparse
import cProfile
import json
import os
import platform
import shutil
import statistics
import struct
import hashlib
import subprocess
from contextlib import nullcontext
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0
from re4pc.game import Game
from re4pc.assets import COMPATIBLE_LIBRARIES
from re4pc.paths import game_dir, isolated_game, test_output
from re4pc.runtime_log import configure
from re4pc.settings import validate as validate_settings
from re4pc.timing import FramePacer


def source_identity(root=None):
    """Bind measurements to the actual source bytes, including local changes."""
    root = Path(root or Path(__file__).resolve().parent.parent)
    from re4pc.packaging import APPLICATION_MODULES, NATIVE_INPUTS
    paths = [root/'re4pc'/name for name in APPLICATION_MODULES]
    paths += [root/'native'/name for name in NATIVE_INPUTS]
    paths += [root/'tools/benchmark.py', root/'tools/build_native.py']
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode() + b'\0')
        digest.update(path.read_bytes())
    try:
        revision = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                           stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'],
                                            stderr=subprocess.DEVNULL))
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    return {'revision': revision, 'dirty': dirty, 'runtime_source_sha256': digest.hexdigest()}


def quantiles(values):
    values = sorted(values)
    return {name: values[min(len(values)-1, max(0, int(len(values)*ratio+.999)-1))]
            for name, ratio in (('p50', .5), ('p95', .95), ('p99', .99))} if values else {}


def phase_delta(after, before):
    return {name: {'seconds': record['seconds'] - before.get(name, {}).get('seconds', 0),
                   'calls': record['calls'] - before.get(name, {}).get('calls', 0)}
            for name, record in after.items()}


def checkpoint(path, document):
    """Publish a whole completed case; never leave partial JSON on interruption."""
    temporary = path.with_suffix('.json.tmp')
    with temporary.open('w') as stream:
        json.dump(document, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def case_key(case):
    return case['repetition'], case['mode'], case['diagnostics_enabled']


def resume_document(path, hardware, configuration):
    document = json.loads(path.read_text())
    if document.get('schema_version') != 1 or document.get('hardware') != hardware:
        raise ValueError('Resume requires the same schema and reference hardware')
    if document.get('configuration', configuration) != configuration:
        raise ValueError('Resume requires the same benchmark configuration')
    if 'source' in document and document['source'] != source_identity():
        raise ValueError('Resume requires the same source revision and bytes')
    records = document['records']
    keys = [case_key(case) for case in records]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate completed benchmark cases')
    graphics = [(case['stats']['graphics']['renderer'], case['stats']['graphics']['version']) for case in records]
    if graphics and any(value != graphics[0] for value in graphics):
        raise ValueError('Resume cannot combine different graphics drivers')
    for case in records:
        transition = case['transition']
        stats = case['stats']
        if stats['engine_hashes'] != COMPATIBLE_LIBRARIES or stats['settings'] != validate_settings({}):
            raise ValueError('Resume requires matching supported engine hashes and default settings')
        if case['profiled'] or not case['diagnostics_enabled'] or (
                configuration['native_transition'] is not None and (
                    not transition['verified'] or transition['after_stage'] != configuration['native_transition'])):
            raise ValueError('Inherited case does not match the requested qualification run')
    document['configuration'] = configuration
    return document


class Replay:
    def __init__(self, game):
        self.game = game
        self.ui, self.title = set(), 0
        self.hooks = []
        self.pacer = FramePacer()
        self.work = []
        for name, address in game.arm.symbols.items():
            if ('Bio4_CTTask_' in name or 'GM_Task_Mis_' in name) and '5FrameEPv' in name:
                def observe(uc, address, size, context, name=name):
                    self.ui.add(name)
                    if 'Task_Title5Frame' in name:
                        self.title = uc.reg_read(UC_ARM_REG_R0)
                self.hooks.append(game.arm.uc.hook_add(UC_HOOK_CODE, observe, begin=address & ~1, end=address & ~1))

    def advance(self, count=1):
        for _ in range(count):
            for event in self.game.graphics.events():
                if event == ('quit',):
                    raise RuntimeError('Benchmark interrupted')
            self.ui.clear()
            self.game.frame()
            self.work.append(self.game.frame_times[-1]*1000)
            self.game.present()
            with self.game.phase('pacing'):
                self.pacer.wait()

    def click(self, x, y, drag=None):
        self.game.event(('touch', True, x, y))
        self.advance(4)
        if drag:
            self.game.event(('motion', *drag))
            self.advance(4)
            x, y = drag
        self.game.event(('touch', False, x, y))
        self.advance(150)

    def village(self):
        user = self.game.arm.symbols['_ZZN13Bio4_UserData11GetInstanceEvE4inst']
        self.advance(200)
        # This is the existing isolated mission-2 regression fixture setup.
        self.game.arm.call('_ZN13Bio4_UserData19SetMissionClearFlagEllb', user, 0, 0, 1)
        self.game.arm.call('_ZN13Bio4_UserData16SetLastMissionIDEhs', user, 0, 1)
        self.game.arm.call('_ZN13Bio4_UserData12SetMissionIDEs', user, 1)
        title_started, story_selected = None, False
        limit = self.game.frames + 2400
        while self.game.frames < limit:
            current = ' '.join(self.ui)
            print('BENCHMARK_NAV', self.game.frames, current, flush=True)
            if title_started is None and ('Title' in current):
                title_started = time.monotonic()
            if self.game.pc.active:
                break
            if 'DataReset' in current: self.click(400, 405)
            elif 'NewNotice' in current: self.click(742, 416)
            elif 'DiffConf' in current: self.click(240, 320, (550, 320))
            elif 'DiffTop' in current: self.click(400, 415)
            elif 'MissionSelectStory' in current:
                self.click(60, 240) if story_selected else self.click(400, 200)
                story_selected = True
            elif 'MissionSelectMercenary' in current: self.click(400, 110)
            elif 'TitleTop' in current: self.click(400, 128)
            elif 'Task_Title5Frame' in current:
                step = self.game.arm.u32(self.title+8)
                if step == 1: self.click(400, 390)
                elif step == 4: self.click(400, 128)
                else: self.advance(10)
            elif 'GameMain' in current or 'Mis_Main' in current: self.click(60, 416)
            else: self.advance(10)
        if not self.game.pc.active:
            raise RuntimeError('Replay did not reach village; last UI: '+current)
        if title_started is None:
            raise RuntimeError('Title boundary not observed')
        return time.monotonic()-title_started

    def close(self):
        for hook in self.hooks:
            self.game.arm.uc.hook_del(hook)
        self.hooks.clear()


def stage_number(game):
    data = game.arm.call('_ZNK11GM_CtrlMain12Get_CtrlDataEv', game.pc.main)
    return game.arm.call('_ZN16GM_CtrlMain_Data13Get_LoadStgNoEv', data)


def native_transition(game, replay, destination):
    """Synthetic request through the audited native stage-change lifecycle.

    The supported event controller reads signed stage/entry at +0x1ae/+0x1af.
    Its stage-change routine ends the field/player/objects, recreates resources
    through Set_StgEntry, and starts the new stage. This fixture exercises that
    real lifecycle; it does not certify a natural door/mission-completion route.
    """
    if not 0 <= destination <= 21:
        raise ValueError('Native transition destination must be a supported stage 0..21')
    before = stage_number(game)
    if before == destination:
        raise ValueError('Transition fixture must change the native loaded stage')
    game.desktop_input.release()
    game.desktop_input.flush()
    game.pc.release()
    event = game.arm.call('_ZNK11GM_CtrlMain11Get_CtrlEveEv', game.pc.main)
    # These two request fields are consumed by the native transition routine.
    game.arm.write(event+0x1ae, bytes((destination, 0)))
    started = time.monotonic()
    with game.phase('stage_transition', 'native stage-change fixture'):
        game.arm.call('_ZN17GM_CtrlMain_Event16_Frame_StgChangeEP11GM_CtrlMain', event, game.pc.main)
    blocking = time.monotonic()-started
    after = stage_number(game)
    work_start = len(replay.work)
    replay.advance(40)
    game.graphics.screenshot(output_path := replay.output/'stage-transition.png')
    return {'verified': after == destination and before != after and game.pc.active,
            'fixture': 'synthetic native stage-change request; natural door route unverified',
            'before_stage': before, 'after_stage': after, 'blocking_seconds': blocking,
            'seconds': time.monotonic()-started, 'post_transition_work_ms': quantiles(replay.work[work_start:]),
            'capture': str(output_path)}


def overhead_probe(game, replay, repetitions=5, ticks=40):
    original = game.diagnostics
    if original is None:
        raise ValueError('Overhead probe needs initially enabled diagnostics')
    measurements = []
    # Interleave windows to reduce systematic ordering/drift bias. Disable
    # all measurement sites, including imported I/O and GL, on baseline windows.
    try:
        for repetition in range(repetitions):
            for enabled in ((False, True) if repetition % 2 == 0 else (True, False)):
                for owner in (game, game.arm, game.bionic, game.graphics, game.graphics.texture_cache):
                    owner.diagnostics = original if enabled else None
                game.phase = original.phase if enabled else lambda *args, **kwargs: nullcontext()
                replay.work.clear()
                replay.advance(ticks)
                measurements.append({'repetition':repetition+1, 'enabled':enabled,
                                     'ticks':ticks, 'work_ms':quantiles(replay.work)})
    finally:
        for owner in (game, game.arm, game.bionic, game.graphics, game.graphics.texture_cache):
            owner.diagnostics = original
        game.phase = original.phase
    baseline = statistics.median(x['work_ms']['p50'] for x in measurements if not x['enabled'])
    instrumented = statistics.median(x['work_ms']['p50'] for x in measurements if x['enabled'])
    ratio = instrumented/baseline-1
    return {'method':'interleaved stationary gameplay windows; same live scene, no detailed profile',
            'windows':measurements, 'baseline_median_ms':baseline, 'diagnostic_median_ms':instrumented,
            'overhead_fraction':ratio, 'gate_passed':ratio <= .05}


def run_case(root, output, mode, diagnostics, gameplay_ticks, transition=None, python_profile=False,
             native_destination=None, probe=False, native_profiles=(), expected_graphics=None, import_profile=False):
    cache = output / 'textures'
    if mode == 'cold':
        shutil.rmtree(cache, ignore_errors=True)
        shutil.rmtree(root/'cache', ignore_errors=True)
    shutil.rmtree(root/'saves', ignore_errors=True)
    (root/'saves').mkdir()
    started = time.monotonic()
    profiler = cProfile.Profile() if python_profile else None
    if profiler: profiler.enable()
    game = Game(root, hidden=True, skip_videos=True, cache=mode != 'disabled', cache_dir=cache,
                diagnostics=diagnostics, settings=validate_settings({}), native_profiles=native_profiles, import_profile=import_profile)
    replay = Replay(game)
    replay.output = output
    try:
        if expected_graphics and (game.graphics.renderer, game.graphics.version) != expected_graphics:
            raise ValueError('Active graphics driver differs from the reference benchmark')
        startup = time.monotonic()-started
        startup_phases = game.diagnostics.metrics()['phases'] if game.diagnostics else {}
        loading = replay.village()
        loading_phases = game.diagnostics.metrics()['phases'] if game.diagnostics else {}
        loading_work = replay.work[:]
        replay.close()  # Selective navigation hooks don't burden gameplay samples.
        replay.work.clear()
        # Exercise sustained translation and tank turning at native cadence.
        game.event(('key', True, ord('w')))
        replay.advance(gameplay_ticks//2)
        game.event(('key', False, ord('w')))
        game.event(('key', True, ord('a')))
        replay.advance(gameplay_ticks-gameplay_ticks//2)
        game.event(('key', False, ord('a')))
        gameplay_work = quantiles(replay.work)
        gameplay_phases = game.diagnostics.metrics()['phases'] if game.diagnostics else {}
        transition_result = {'verified': False, 'reason': 'No stage-transition replay supplied'}
        if transition:
            entries = json.loads(Path(transition).read_text())
            before = stage_number(game)
            transition_started = time.monotonic()
            for tick in range(max(entry['frame'] for entry in entries)+1):
                for entry in entries:
                    if entry['frame'] == tick:
                        game.event(tuple(entry['event']))
                replay.advance()
            after = stage_number(game)
            transition_result = {'verified': before is not None and before != after,
                                 'before_stage': before, 'after_stage': after,
                                 'seconds': time.monotonic()-transition_started}
        elif native_destination is not None:
            transition_result = native_transition(game, replay, native_destination)
            if not transition_result['verified']:
                raise RuntimeError('Native stage-transition fixture failed')
        overhead = overhead_probe(game, replay) if probe else None
        stats = game.statistics(replay.pacer)
        return {'startup_seconds': startup, 'title_to_village_seconds': loading,
                'loading_max_work_ms': max(loading_work), 'gameplay_work_ms': gameplay_work,
                'loading_work_ms': quantiles(loading_work),
                'loading_phases': phase_delta(loading_phases, startup_phases),
                'gameplay_phases': phase_delta(gameplay_phases, loading_phases),
                'mode': mode, 'diagnostics_enabled': diagnostics, 'transition': transition_result,
                'profiled': bool(python_profile or native_profiles or import_profile), 'overhead_probe':overhead, 'stats': stats}
    finally:
        replay.close()
        game.close()
        if profiler:
            profiler.disable()
            profiler.dump_stats(str(output/'python-profile.pstats'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=game_dir())
    parser.add_argument('--output', type=Path)
    parser.add_argument('--repetitions', type=int, default=5)
    parser.add_argument('--gameplay-ticks', type=int, default=200)
    parser.add_argument('--modes', nargs='+', choices=('disabled', 'cold', 'warm'), default=['disabled', 'cold', 'warm'])
    parser.add_argument('--compare-diagnostics', action='store_true')
    parser.add_argument('--python-profile', action='store_true')
    parser.add_argument('--profile-imports', action='store_true')
    parser.add_argument('--transition-script', type=Path, help='JSON frame/event replay; must change native loaded-stage ID')
    parser.add_argument('--native-transition', type=int, help='Synthetic audited stage-change fixture (stage 0..21); natural door route remains unverified')
    parser.add_argument('--overhead-probe', action='store_true', help='First case: five interleaved gameplay windows per diagnostics mode')
    parser.add_argument('--native-profile', action='append', default=[], help='Selected native timing symbols; profiled samples excluded from qualification')
    parser.add_argument('--resume', action='store_true', help='Keep completed cases in output/results.json and run only missing cases')
    args = parser.parse_args()
    if args.repetitions < 1 or args.gameplay_ticks < 20: parser.error('Use positive repetitions and at least 20 gameplay ticks')
    output = test_output('benchmark', args.output)
    root = isolated_game(args.game, output)
    hardware = {'platform': platform.platform(), 'machine': platform.machine(),
                'cpu': next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')), platform.processor()),
                'memory_bytes': os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')}
    configure('warning')
    configuration = {'gameplay_ticks':args.gameplay_ticks, 'native_transition':args.native_transition,
                     'transition_script':str(args.transition_script) if args.transition_script else None,
                     'compare_diagnostics':args.compare_diagnostics, 'native_profiles':args.native_profile,
                     'python_profile':args.python_profile, 'import_profile':args.profile_imports}
    document = {'schema_version':1, 'hardware':hardware, 'configuration':configuration,
                'source':source_identity(),
                'cache_definition':'application caches; OS page cache uncontrolled', 'records':[]}
    if args.resume:
        if args.compare_diagnostics or args.python_profile or args.native_profile or args.profile_imports:
            parser.error('Resume qualification runs without detailed profiling or diagnostics comparison')
        document = resume_document(output/'results.json', hardware, configuration)
    records = document['records']
    completed = {case_key(case) for case in records}
    expected_graphics = ((records[0]['stats']['graphics']['renderer'], records[0]['stats']['graphics']['version'])
                         if records else None)
    document.setdefault('sessions', []).append({'started_unix':time.time(),
        'resumed_cases':len(records), 'note':'Fresh isolated inputs and freshly primed warm cache per session'})
    checkpoint(output/'results.json', document)
    # Warm samples are primed by a discarded cold run in the same installation.
    if 'warm' in args.modes and any((repetition+1, 'warm', True) not in completed
                                  for repetition in range(args.repetitions)):
        run_case(root, output, 'cold', True, 20, expected_graphics=expected_graphics)
    for repetition in range(args.repetitions):
        for mode in args.modes:
            for diagnostic_mode in ([False, True] if args.compare_diagnostics else [True]):
                if (repetition+1, mode, diagnostic_mode) in completed:
                    continue
                case = run_case(root, output, mode, diagnostic_mode, args.gameplay_ticks,
                                args.transition_script, args.python_profile and not records,
                                args.native_transition, args.overhead_probe and not records, args.native_profile,
                                expected_graphics, args.profile_imports)
                if expected_graphics is None:
                    expected_graphics = case['stats']['graphics']['renderer'], case['stats']['graphics']['version']
                case['repetition'] = repetition + 1
                records.append(case)
                checkpoint(output/'results.json', document)
                print('BENCHMARK_CASE', repetition+1, mode, diagnostic_mode,
                      round(case['title_to_village_seconds'],3), case['gameplay_work_ms'], flush=True)
    print('BENCHMARK_RUNS_COMPLETE:', output/'results.json', flush=True)
    if any(not case['transition']['verified'] for case in records):
        print('STAGE_TRANSITION_UNVERIFIED: results do not satisfy the complete four-scenario release gate', flush=True)


if __name__ == '__main__':
    main()
