"""Run a visible smoke replay with isolated saves, then print measured evidence."""
import json
import argparse
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from re4pc.game import Game

from re4pc.paths import game_dir, isolated_game, test_output
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--game',type=Path,default=game_dir())
parser.add_argument('--output',type=Path)
args=parser.parse_args()
output=test_output('visible-test',args.output)
test_game=isolated_game(args.game,output)
print('Test artifacts:',output,flush=True)
replay=[{'frame':0,'action':'label','text':'VISIBLE TEST — original intro, title, mouse input and audio'},
        {'frame':230,'action':'resize','width':1000,'height':700},
        {'frame':240,'action':'event','event':['fullscreen']},
        {'frame':250,'action':'screenshot','path':str(output/'intro.png')},
        {'frame':255,'action':'event','event':['fullscreen']},
        {'frame':260,'action':'resize','width':800,'height':480},
        {'frame':265,'action':'event','event':['key',True,1073741884]},
        {'frame':266,'action':'screenshot','path':str(output/'diagnostics.png')},
        {'frame':270,'action':'event','event':['key',True,1073741884]},
        {'frame':300,'action':'skip_video'},
        {'frame':400,'action':'screenshot','path':str(output/'title.png')},
        {'frame':550,'action':'screenshot','path':str(output/'menu.png')},
        {'frame':550,'action':'assert_no_video'},
        {'frame':555,'action':'save_roundtrip'}]
# At the native 20 Hz cadence, the old 710-frame replay could idle long
# enough for the main menu to start its attract/fade sequence again.
for frame in (410,450,490,530):
    replay.extend([{'frame':frame,'action':'down','x':400,'y':390},
                   {'frame':frame+5,'action':'up','x':400,'y':390}])
replay.sort(key=lambda event:event['frame'])
script=output/'replay.json';script.write_text(json.dumps(replay,indent=2)+'\n')
game=Game(test_game)
media_max_ms={}
def measured(name, callback):
    def invoke(*args):
        started=time.perf_counter()
        result=callback(*args)
        elapsed=(time.perf_counter()-started)*1000
        media_max_ms[name]=max(media_max_ms.get(name,0),elapsed)
        return result
    return invoke
game.media.video_service=measured('video_service',game.media.video_service)
game.media.end_video=measured('end_video',game.media.end_video)
game.media.audio_service=measured('audio_service',game.media.audio_service)
stats=game.run(560,script=script,replay_only=True)
stats['media_max_ms']={name:round(value,3) for name,value in media_max_ms.items()}
(output/'stats.json').write_text(json.dumps(stats,indent=2)+'\n')
assert stats['draw_calls']>100 and stats['texture_uploads']>10,'Original renderer did not draw'
assert stats['audio_nonzero_samples']>0,'Audio device received only silence'
assert stats['videos_played']>0,'No original cutscene played'
assert stats['input_events']>=2,'Mouse replay did not reach engine'
assert not stats['gl_messages'],'OpenGL reported errors'
assert stats['save_roundtrip_verified'],'Original engine serialization failed'
assert stats['engine_hz']==20,'Frame-driven gameplay must use its native clock'
assert stats['elapsed_seconds']>=stats['frames']/stats['engine_hz']-0.1,'Host accelerated game time'
# Measure the real bridges on a cold cache. Decoder startup and teardown
# must return promptly, even though decoding/reaping continues.
assert all(value<100 for value in media_max_ms.values()), ('Main-thread media stall',media_max_ms)
from PIL import Image,ImageStat
for name in ('intro','title','menu'):
    picture=Image.open(output/(name+'.png'))
    assert sum(ImageStat.Stat(picture).var)>100,f'{name} capture is blank'
    if name=='menu':
        # A black attract/fade screen with only the corner logo also has
        # nonzero variance. Require content in the menu's central region.
        assert sum(ImageStat.Stat(picture.crop((200,100,600,350))).mean)>40,'Menu capture reached a fade/attract screen'
assert (test_game/'saves/save.dat').stat().st_size>0,'Original engine did not create save data'
print('VISIBLE_SMOKE_PASS: review',output,'intro.png, title.png, menu.png and stats.json')
