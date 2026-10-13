"""Long-running isolated host soak and native stage lifecycle stress.

Stage requests are synthetic and never count as natural doors, mission restarts
or campaign progression. Reports retain separate gates for duration, occupancy,
resource growth and lifecycle cycles; no campaign success is inferred.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from re4pc.game import Game
from re4pc.paths import game_dir, isolated_game, test_output
from tools.benchmark import Replay, native_transition, stage_number, checkpoint, source_identity


def sample(game, elapsed):
    stats=game.statistics()
    resident=int(Path('/proc/self/statm').read_text().split()[1])*4096
    return {'elapsed_seconds':elapsed,'ticks':game.frames,'gameplay':game.pc.active,
            'rss_bytes':resident,'guest_live_bytes':stats['diagnostics']['guest_live_bytes'],
            'guest_heap_bytes':stats['heap_bytes'],'pending_audio_decodes':stats['pending_audio_decodes'],
            'pending_audio_requests':stats['pending_audio_requests'],
            'open_descriptors':len(list(Path('/proc/self/fd').iterdir())),
            'held_keys':len(game.desktop_input.keys_down),'held_buttons':len(game.pc.buttons),
            'work_ms':stats['diagnostics']['frame_work_ms']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,default=game_dir())
    parser.add_argument('--output',type=Path)
    parser.add_argument('--seconds',type=float,default=7200)
    parser.add_argument('--cycles',type=int,default=20)
    args=parser.parse_args()
    if args.seconds<0 or args.cycles<0:parser.error('Use nonnegative seconds and cycles')
    output=test_output('session-validation',args.output)
    checkout=Path(__file__).resolve().parents[1]
    if output.resolve()==checkout or checkout in output.resolve().parents:
        parser.error('Keep isolated engine fixtures outside the checkout')
    root=isolated_game(args.game,output)
    report={'schema_version':1,'source':source_identity(),'completed':False,'natural_campaign_verified':False,
            'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'fixture':'synthetic tutorial clear, mission selection and stage requests; not natural progression',
            'cycles':[],'samples':[],'failure':None}
    game=replay=None
    checkpoint(output/'results.json',report)
    try:
        game=Game(root,hidden=True,skip_videos=True)
        replay=Replay(game);replay.output=output
        replay.village();replay.close()
        for index in range(args.cycles):
            destination=3 if stage_number(game)!=3 else 1
            row=native_transition(game,replay,destination)
            if not row['verified']:raise RuntimeError('Native stage lifecycle failed')
            row['cycle']=index+1;row['resources']=sample(game,0)
            report['cycles'].append(row)
            checkpoint(output/'results.json',report)
            print('SESSION_CYCLE_PASS',index+1,flush=True)
        started=time.monotonic();next_sample=0;active=total=0
        while time.monotonic()-started<args.seconds:
            replay.advance();total+=1;active+=int(game.pc.active)
            elapsed=time.monotonic()-started
            if elapsed>=next_sample:
                report['samples'].append(sample(game,elapsed))
                report.update(continuous_seconds=elapsed,gameplay_fraction=active/max(1,total))
                checkpoint(output/'results.json',report)
                print('SESSION_SAMPLE',round(elapsed),game.frames,game.pc.active,flush=True)
                next_sample+=60
        elapsed=time.monotonic()-started
        report['samples'].append(sample(game,elapsed))
        warm=[row for row in report['samples'] if row['elapsed_seconds']>=300]
        report.update(continuous_seconds=elapsed,gameplay_fraction=active/max(1,total),
                      duration_gate=elapsed>=7200,synthetic_lifecycle_gate=len(report['cycles'])>=20,
                      held_input_gate=all(not row['held_keys'] and not row['held_buttons'] for row in report['samples']),
                      post_warmup_resource_delta=({key:warm[-1][key]-warm[0][key] for key in
                          ('rss_bytes','guest_live_bytes','guest_heap_bytes','open_descriptors')} if len(warm)>1 else None),
                      memory_growth_review='Inspect samples and warm-up delta; no automatic leak threshold or campaign claim')
        game.verify_save_roundtrip()
        report['save_roundtrip']=game.save_verified
        report['completed']=True
    except BaseException as error:
        report['failure']=str(error)
        raise
    finally:
        checkpoint(output/'results.json',report)
        if replay is not None:replay.close()
        if game is not None:game.close()
    print('SESSION_RECORDED',output/'results.json',flush=True)


if __name__=='__main__':main()
