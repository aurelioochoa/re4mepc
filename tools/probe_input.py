"""Measure original input state after actual SDL press/release events, visibly."""
import ctypes as C
import json
import argparse
import struct
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
output=test_output('input-probe',args.output)
game=Game(isolated_game(args.game,output),skip_videos=True)
sdl=game.graphics.sdl
sdl.SDL_PushEvent.argtypes=(C.c_void_p,)
sdl.SDL_GetWindowSize.argtypes=(C.c_void_p,C.POINTER(C.c_int),C.POINTER(C.c_int))
sdl.SDL_GL_GetDrawableSize.argtypes=sdl.SDL_GetWindowSize.argtypes

def push(kind,x=400,y=390,code=None):
    event=C.create_string_buffer(64)
    struct.pack_into('<I',event,0,kind)
    if code is not None:
        event[12]=bytes([kind==0x300]);struct.pack_into('<i',event,20,code)
    else:
        event[16]=b'\x01';event[17]=bytes([kind==0x401])
        struct.pack_into('<ii',event,20,x,y)
    if sdl.SDL_PushEvent(event)!=1:raise RuntimeError('SDL push failed')

def frame():
    for event in game.graphics.events():game.event(event)
    game.frame();game.graphics.swap();time.sleep(1/45)

try:
    for _ in range(250):frame()
    width=C.c_int();height=C.c_int()
    for name in ('SDL_GetWindowSize','SDL_GL_GetDrawableSize'):
        getattr(sdl,name)(game.graphics.window,C.byref(width),C.byref(height))
        print(name,width.value,height.value,flush=True)
    push(0x300,code=ord('w'));push(0x301,code=ord('w'))
    frame()
    print('QUICK_KEY_SCAN',game.arm.call('_ZN10Bio4_Input11Get_KeyScanEv'),flush=True)
    push(0x300,code=ord('w'));frame()
    print('HELD_KEY_SCAN',game.arm.call('_ZN10Bio4_Input11Get_KeyScanEv'),flush=True)
    push(0x301,code=ord('w'));frame()
    push(0x401);push(0x402)
    for _ in range(100):frame()
    game.frame();game.graphics.screenshot(output/'mouse-probe.png');game.graphics.swap()
    print('MOUSE_PROBE_DONE',flush=True)
finally:game.close()
