"""Keep a visible game window open and accept JSON test actions on stdin."""
import json
import argparse
import ctypes as C
import struct
import select
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from re4pc.game import Game
from re4pc.paths import game_dir, isolated_game, test_output
from re4pc.bionic import float_in
from re4pc.bionic import signed

parser=argparse.ArgumentParser()
parser.add_argument('--game',type=Path,default=game_dir())
parser.add_argument('--output',type=Path)
parser.add_argument('--skip-videos',action='store_true')
args=parser.parse_args()
output=test_output('live-test',args.output)
game=Game(isolated_game(args.game,output),skip_videos=args.skip_videos)
print('Test artifacts:',output,flush=True)
pending=[]
running=True
try:
    print('VISIBLE_TEST_READY: enter JSON actions (click, key, screenshot, skip_video, stats, quit)',flush=True)
    while running:
        start=time.monotonic()
        if select.select([sys.stdin],[],[],0)[0]:
            line=sys.stdin.readline()
            if not line: break
            try:
                command=json.loads(line)
                action=command['action']
                if action=='click':
                    game.touch('down',command['x'],command['y'])
                    pending.append((game.frames+3,command['x'],command['y']))
                elif action=='key': game.key(command['down'],command['code'])
                elif action=='sdl_mouse':
                    event=C.create_string_buffer(64)
                    kind={'down':0x401,'up':0x402,'move':0x400}[command['kind']]
                    struct.pack_into('<I',event,0,kind)
                    game.graphics.sdl.SDL_GetWindowID.argtypes=(C.c_void_p,)
                    struct.pack_into('<I',event,8,game.graphics.sdl.SDL_GetWindowID(game.graphics.window))
                    event[16]=bytes([command.get('button',1)])
                    if kind != 0x400:event[17]=bytes([kind==0x401])
                    struct.pack_into('<ii',event,20,command['x'],command['y'])
                    if kind==0x400:struct.pack_into('<ii',event,28,command.get('dx',0),command.get('dy',0))
                    game.graphics.sdl.SDL_PushEvent.argtypes=(C.c_void_p,)
                    if game.graphics.sdl.SDL_PushEvent(event)!=1:raise RuntimeError('SDL mouse event failed')
                elif action=='sdl_key':
                    event=C.create_string_buffer(64)
                    struct.pack_into('<I',event,0,0x300 if command['down'] else 0x301)
                    event[12]=bytes([command['down']])
                    struct.pack_into('<i',event,20,command['key'])
                    game.graphics.sdl.SDL_PushEvent.argtypes=(C.c_void_p,)
                    if game.graphics.sdl.SDL_PushEvent(event)!=1:raise RuntimeError('SDL keyboard event failed')
                elif action=='sample_pad':
                    ctrl=game.arm.call('_ZN16GM_CtrlLyt_Input8Get_InstEv')
                    values={name:signed(value) for name in ('Get_InputRateX','Get_InputRateY','Get_InputScan')
                            for value in [game.arm.call(f'_ZN16GM_CtrlLyt_Input{len(name)}{name}Ev',ctrl)]}
                    print('PAD_STATE',json.dumps(values),'PC',json.dumps(game.pc.last_sample),
                          'STATUS',game.pc.active,game.pc.story_active,game.mouse_captured,game.mouse_released,
                          'KEYS',sorted(game.pc.keys),'BUTTONS',sorted(game.pc.buttons),flush=True)
                elif action=='test_pc':
                    from test_pc_controls import check_gameplay
                    check_gameplay(game,output)
                elif action in ('down','up','move'): game.touch(action,command['x'],command['y'])
                elif action=='skip_video': game.media.end_video()
                elif action=='screenshot':
                    game.frame();game.graphics.screenshot(command['path']);game.graphics.swap()
                    print('CAPTURED',command['path'],'frame',game.frames,flush=True)
                elif action=='stats':
                    stats={'frames':game.frames,'draws':game.graphics.draws,'textures':game.graphics.textures,'inputs':game.input_events,
                           'audio_nonzero_samples':game.media.audio.re4_audio_measure(1),'videos':game.media.videos_played,
                           'recent_engine_ms':round(sum(game.frame_times[-100:])/max(1,len(game.frame_times[-100:]))*1000,2),
                           'gl_messages':sorted(game.graphics.debug_messages)}
                    print('LIVE_STATS',json.dumps(stats),flush=True)
                    if command.get('path'): Path(command['path']).write_text(json.dumps(stats,indent=2)+'\n')
                elif action=='inspect_keys':
                    count=game.arm.u32(game.arm.symbols['_ZN10Bio4_Input12m_KeyListNumE'])
                    pointer=game.arm.symbols['_ZN10Bio4_Input9m_KeyListE']
                    print('KEY_ASSIGNMENTS',count,[tuple(game.arm.u32(pointer+i*8+j*4) for j in range(2)) for i in range(count)],flush=True)
                elif action=='save':
                    user=game.arm.symbols['_ZZN13Bio4_UserData11GetInstanceEvE4inst']
                    result=game.arm.call('_ZN13Bio4_UserData4SaveEl',user,63)
                    print('SAVE',result,flush=True)
                elif action=='quit': running=False
                else: raise ValueError('Unknown action')
                print('ACTION',action,'frame',game.frames,flush=True)
            except (ValueError,KeyError) as error: print('COMMAND_ERROR',str(error),flush=True)
        for frame,x,y in list(pending):
            if game.frames>=frame:
                game.touch('up',x,y);pending.remove((frame,x,y))
        for event in game.graphics.events():
            if not game.event(event):running=False
        if not running:break
        game.frame();game.graphics.swap()
        time.sleep(max(0,1/45-(time.monotonic()-start)))
finally:
    game.close()
