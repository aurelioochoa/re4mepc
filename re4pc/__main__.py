import argparse
import json
import sys
import math
from pathlib import Path
from .assets import import_apk, validate
from .paths import game_dir
from .runtime_log import configure, log, RuntimeLog


def main():
    parser=argparse.ArgumentParser(description='Resident Evil 4 Mobile ARM engine compatibility host for Linux PC')
    sub=parser.add_subparsers(dest='command',required=True)
    imp=sub.add_parser('import',help='Restore game data from an Android APK')
    imp.add_argument('apk',type=Path)
    imp.add_argument('--output',type=Path,default=game_dir())
    check=sub.add_parser('check',help='Validate an imported game data directory')
    check.add_argument('--game',type=Path,default=game_dir())
    run=sub.add_parser('run',help='Run the original mobile engine in a desktop window')
    run.add_argument('--game',type=Path,default=game_dir())
    run.add_argument('--width',type=int,default=800)
    run.add_argument('--height',type=int,default=480)
    run.add_argument('--frames',type=int,default=0,help='Stop after this many engine frames (0: interactive)')
    run.add_argument('--skip-videos',action='store_true',help='Skip cutscenes')
    run.add_argument('--trace-jni',action='store_true')
    run.add_argument('--language',choices=('en','saved'),default='en',help='English at startup or the saved in-game language')
    run.add_argument('--controls',choices=('pc','touch'),default='pc',help='PC mouse/WASD controls or the original touch controls')
    run.add_argument('--screenshot',type=Path)
    run.add_argument('--script',type=Path,help='JSON input replay file')
    run.add_argument('--stats',type=Path,help='Write measured runtime statistics to JSON')
    run.add_argument('--log-level',choices=('debug','info','warning','error'),default='info')
    run.add_argument('--log-file',type=Path,help='Also save runtime logs to this file')
    run.add_argument('--log-interval',type=float,default=5,help='Seconds between live status lines (0 disables)')
    args=parser.parse_args()
    try:
        if args.command=='import':
            print('Imported game data into',import_apk(args.apk,args.output))
        elif args.command=='check':
            print('Game data validated:',validate(args.game))
        else:
            if not (320<=args.width<=3840 and 240<=args.height<=2160) or args.frames<0:
                parser.error('Use dimensions between 320x240 and 3840x2160 and nonnegative frames')
            from .game import Game
            if not math.isfinite(args.log_interval) or args.log_interval<0:
                parser.error('--log-interval must be a finite nonnegative number')
            configure(args.log_level,args.log_file)
            log.info('Starting game: %dx%d, controls=%s, data=%s',args.width,args.height,args.controls,args.game)
            with RuntimeLog(args.log_interval) as telemetry:
                game=Game(args.game,args.width,args.height,False,args.trace_jni,args.skip_videos,args.language,args.controls)
                game.telemetry=telemetry
                stats=game.run(args.frames,args.screenshot,args.script)
            if args.stats: args.stats.write_text(json.dumps(stats,indent=2)+'\n')
            log.info('Game stopped after %d frames; mean engine time %.2f ms',stats['frames'],stats['mean_engine_ms'])
    except KeyboardInterrupt:
        log.info('Stopped by Ctrl+C')
        return 130
    except (ValueError,RuntimeError,OSError,TimeoutError) as error:
        if args.command=='run': log.error('%s',error,exc_info=args.log_level=='debug')
        else: print('re4pc:',error,file=sys.stderr)
        return 1
    return 0

if __name__=='__main__': sys.exit(main())
