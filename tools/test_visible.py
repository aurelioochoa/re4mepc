"""Run a visible smoke replay with isolated saves, then print measured evidence."""
import json
import argparse
import sys
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
        {'frame':250,'action':'screenshot','path':str(output/'intro.png')},
        {'frame':300,'action':'skip_video'},
        {'frame':400,'action':'screenshot','path':str(output/'title.png')},
        {'frame':700,'action':'screenshot','path':str(output/'menu.png')},
        {'frame':700,'action':'assert_no_video'},
        {'frame':705,'action':'save_roundtrip'}]
for frame in (410,450,490,530,570,610):
    replay.extend([{'frame':frame,'action':'down','x':400,'y':390},
                   {'frame':frame+5,'action':'up','x':400,'y':390}])
replay.sort(key=lambda event:event['frame'])
script=output/'replay.json';script.write_text(json.dumps(replay,indent=2)+'\n')
game=Game(test_game)
stats=game.run(710,script=script,replay_only=True)
(output/'stats.json').write_text(json.dumps(stats,indent=2)+'\n')
assert stats['draw_calls']>100 and stats['texture_uploads']>10,'Original renderer did not draw'
assert stats['audio_nonzero_samples']>0,'Audio device received only silence'
assert stats['videos_played']>0,'No original cutscene played'
assert stats['input_events']>=2,'Mouse replay did not reach engine'
assert not stats['gl_messages'],'OpenGL reported errors'
assert stats['save_roundtrip_verified'],'Original engine serialization failed'
from PIL import Image,ImageStat
for name in ('intro','title','menu'):
    picture=Image.open(output/(name+'.png'))
    assert sum(ImageStat.Stat(picture).var)>100,f'{name} capture is blank'
assert (test_game/'saves/save.dat').stat().st_size>0,'Original engine did not create save data'
print('VISIBLE_SMOKE_PASS: review',output,'intro.png, title.png, menu.png and stats.json')
