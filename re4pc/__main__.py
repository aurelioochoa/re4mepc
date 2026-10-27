"""Linux runtime, graphical launcher, settings and stopped-game save tools."""
import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from .assets import import_apk, validate
from .paths import game_dir
from .runtime_log import configure, log, RuntimeLog
from .settings import Settings


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def argument_parser():
    parser = argparse.ArgumentParser(description='Resident Evil 4 Mobile ARM engine compatibility host for Linux PC')
    sub = parser.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('import', help='Restore game data from an Android APK')
    imp.add_argument('apk', type=Path)
    imp.add_argument('--output', type=Path, default=game_dir())
    check = sub.add_parser('check', help='Validate imported game data')
    check.add_argument('--game', type=Path, default=game_dir())
    launcher = sub.add_parser('launcher', help='Open the graphical desktop launcher')
    launcher.add_argument('--game', type=Path, default=game_dir())
    launcher.add_argument('--smoke-test', action='store_true', help='Open the launcher briefly, then exit for package validation')
    for command in ('backup', 'backups', 'export-backup', 'restore-backup', 'import-backup', 'delete-backup'):
        item = sub.add_parser(command, help='Stopped-game save operation: ' + command)
        item.add_argument('--game', type=Path, default=game_dir())
        if command in ('export-backup', 'restore-backup', 'delete-backup'):
            item.add_argument('snapshot_id')
        if command == 'export-backup':
            item.add_argument('destination', type=Path)
            item.add_argument('--include-media', action='store_true', help='Export a portable save and achievement media bundle')
        if command == 'import-backup':
            item.add_argument('archive', type=Path)
    gallery = sub.add_parser('export-achievements', help='Export original achievement captures and their metadata as ZIP')
    gallery.add_argument('destination', type=Path)
    gallery.add_argument('--game', type=Path, default=game_dir())
    gallery.add_argument('--achievement', action='append', default=[], metavar='ID', help='Select an achievement (repeatable; default: all)')
    settings = sub.add_parser('settings', help='Show settings or change one value using JSON')
    settings.add_argument('--set', nargs=2, metavar=('KEY', 'JSON_VALUE'))
    run = sub.add_parser('run', help='Run the original mobile engine in a desktop window')
    run.add_argument('--game', type=Path, default=game_dir())
    run.add_argument('--width', type=int, help='Override saved window width')
    run.add_argument('--height', type=int, help='Override saved window height')
    run.add_argument('--window-mode', choices=('windowed', 'fullscreen'))
    from .timing import PRESENTATION_RATES
    run.add_argument('--presentation-rate', '--fps', type=int, choices=PRESENTATION_RATES,
                     help='Presentation FPS with geometry interpolation; 0 uncapped, 20 native. Simulation stays 20 Hz')
    run.add_argument('--no-fast-graphics', action='store_true', help='Use Python GL state imports for performance comparisons')
    run.add_argument('--sensitivity', type=float)
    run.add_argument('--controller-sensitivity', type=float)
    run.add_argument('--dead-zone', type=float)
    run.add_argument('--invert-y', action=argparse.BooleanOptionalAction, default=None)
    run.add_argument('--frames', type=int, default=0, help='Stop after this many simulation ticks (0: interactive)')
    run.add_argument('--skip-videos', action='store_true', help='Skip cutscenes')
    run.add_argument('--trace-jni', action='store_true')
    from .languages import GAME_LANGUAGES
    run.add_argument('--language', choices=tuple(GAME_LANGUAGES), help='Override saved game language')
    run.add_argument('--controls', choices=('pc', 'touch'), default='pc')
    run.add_argument('--screenshot', type=Path)
    run.add_argument('--script', type=Path, help='JSON input replay; frame numbers count simulation ticks')
    run.add_argument('--stats', type=Path, help='Write versioned statistics with preserved legacy fields')
    run.add_argument('--profile', type=Path, help='Detailed versioned JSONL timing trace')
    run.add_argument('--native-profile', action='append', default=[], metavar='SYMBOL', help='Opt-in native symbol timing (perturbs execution)')
    run.add_argument('--profile-imports', action='store_true', help='Opt-in dispatch and service-body profiling (perturbs execution)')
    cache = run.add_mutually_exclusive_group()
    cache.add_argument('--cache', action='store_true', help='Enable experimental persistent converted-texture cache')
    cache.add_argument('--no-cache', action='store_false', dest='cache', help='Compute textures without conversion caching (default)')
    run.set_defaults(cache=False)
    run.add_argument('--cache-dir', type=Path, help='Isolated texture-cache directory for comparisons')
    run.add_argument('--no-diagnostics', action='store_true', help='Disable timing instrumentation for overhead comparisons')
    run.add_argument('--log-level', choices=('debug', 'info', 'warning', 'error'), default='info')
    run.add_argument('--log-file', type=Path)
    run.add_argument('--log-interval', type=float, default=5, help='Seconds between live status lines (0 disables)')
    return parser


def main(argv=None):
    parser = argument_parser()
    argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(argv or ['launcher'])
    try:
        if args.command == 'import':
            print('Imported game data into', import_apk(args.apk, args.output))
        elif args.command == 'check':
            print('Game data validated:', validate(args.game))
        elif args.command == 'launcher':
            from .launcher import launch
            launch(args.game, smoke_test=args.smoke_test)
        elif args.command == 'settings':
            values = Settings.load()
            if args.set:
                key, value = args.set
                values[key] = json.loads(value)
                values = Settings.save(values)
            print(json.dumps(values, indent=2))
        elif args.command in ('backup', 'backups', 'export-backup', 'restore-backup', 'import-backup', 'delete-backup', 'export-achievements'):
            from .backups import SaveStore
            if not args.game.is_dir():
                raise ValueError('Game installation does not exist: ' + str(args.game))
            with SaveStore(args.game) as store:
                if args.command == 'backup': result = store.snapshot()
                elif args.command == 'backups': result = store.list_snapshots()
                elif args.command == 'export-backup': result = store.export(args.snapshot_id, args.destination, include_media=args.include_media)
                elif args.command == 'export-achievements':
                    from .capture_exports import export_achievements
                    result = export_achievements(store, args.destination, args.achievement)
                elif args.command == 'restore-backup': result = store.restore(args.snapshot_id)
                elif args.command == 'delete-backup': result = store.delete(args.snapshot_id)
                else: result = store.import_backup(args.archive)
                print(json.dumps(result, indent=2, default=str))
        else:
            if args.frames < 0:
                parser.error('--frames must be nonnegative')
            if not math.isfinite(args.log_interval) or args.log_interval < 0:
                parser.error('--log-interval must be a finite nonnegative number')
            if args.no_diagnostics and (args.profile or args.native_profile or args.profile_imports):
                parser.error('Profiles require diagnostics')
            settings = Settings.load(overrides={
                'window_width': args.width, 'window_height': args.height,
                'window_mode': args.window_mode, 'presentation_rate': args.presentation_rate,
                'sensitivity': args.sensitivity, 'controller_sensitivity': args.controller_sensitivity,
                'stick_dead_zone': args.dead_zone, 'invert_y': args.invert_y,
                'game_language': args.language})
            from .game import Game
            configure(args.log_level, args.log_file)
            log.info('Starting game: %dx%d, controls=%s, data=%s', settings['window_width'], settings['window_height'], args.controls, args.game)
            with RuntimeLog(args.log_interval) as telemetry:
                game = Game(args.game, settings['window_width'], settings['window_height'], False,
                    args.trace_jni, args.skip_videos, settings['game_language'], args.controls,
                    settings=settings, profile=args.profile, native_profiles=args.native_profile,
                    fast_graphics=not args.no_fast_graphics,
                    cache=args.cache, cache_dir=args.cache_dir, telemetry=telemetry,
                    diagnostics=not args.no_diagnostics, import_profile=args.profile_imports)
                stats = game.run(args.frames, args.screenshot, args.script)
            if args.stats: write_json(args.stats, stats)
            log.info('Game stopped after %d ticks; mean frame work %.2f ms', stats['frames'], stats['mean_engine_ms'])
    except KeyboardInterrupt:
        log.info('Stopped by Ctrl+C')
        return 130
    except (ValueError, RuntimeError, OSError, TimeoutError) as error:
        if args.command == 'run': log.error('%s', error, exc_info=args.log_level == 'debug')
        else: print('re4pc:', error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
