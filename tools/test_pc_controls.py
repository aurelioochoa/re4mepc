"""Visible gameplay regression, invoked with live_test's test_pc command."""
import ctypes as C
import json
import struct
import math
import time
from pathlib import Path


def check_gameplay(game, output=None):
    assert game.pc.active, 'Start a mission and dismiss story text first'
    from re4pc.paths import test_output
    from re4pc.timing import FramePacer
    output=test_output('pc-controls',output)
    sdl=game.graphics.sdl
    sdl.SDL_PushEvent.argtypes=(C.c_void_p,)
    sdl.SDL_GetWindowID.argtypes=(C.c_void_p,)
    expected=[]
    evidence={}
    pacer=FramePacer()

    def push(kind, value=0, dx=0, dy=0):
        if not expected:
            # Pump desktop focus changes before queuing synthetic motion.
            # SDL can flush queued motion while processing a real focus loss.
            for event in game.graphics.events():
                if event==('quit',) or event==('key',True,1073741893):
                    raise RuntimeError('Visible test interrupted')
        event=C.create_string_buffer(64)
        struct.pack_into('<II',event,0,kind,0)
        struct.pack_into('<I',event,8,sdl.SDL_GetWindowID(game.graphics.window))
        if kind in (0x300,0x301):
            event[12]=bytes([kind==0x300]);struct.pack_into('<i',event,20,value)
            expected.append(('key',kind==0x300,value))
        elif kind in (0x401,0x402):
            event[16]=bytes([value]);event[17]=bytes([kind==0x401])
            struct.pack_into('<ii',event,20,400,240)
            expected.append(('touch',kind==0x401,400,240) if value==1 else ('mouse_button',kind==0x401,value))
        elif kind==0x200:
            event[12]=b'\x0d'
            expected.append(('focus_lost',))
        else:
            struct.pack_into('<iiii',event,20,400,240,dx,dy)
            expected.append(('mouse_delta',dx,dy))
        assert sdl.SDL_PushEvent(event)==1

    def advance(count=1):
        for _ in range(count):
            events=list(game.graphics.events())
            # SDL's poll boundary can return an empty batch before events
            # pushed after the preceding pump. Drain the next batch before
            # measuring a synthetic event's effect on this engine frame.
            for _ in range(2):
                if all(event in events for event in expected):break
                events.extend(game.graphics.events())
            for event in list(expected):
                assert event in events, ('SDL event lost',event,events)
                game.event(event);expected.remove(event)
            for event in events:
                if event==('quit',) or event==('key',True,1073741893):
                    raise RuntimeError('Visible test interrupted')
            game.frame();game.graphics.swap();pacer.wait()

    def capture(name):
        game.frame();game.graphics.screenshot(output/(name+'.png'));game.graphics.swap()

    def state():
        return struct.unpack('<h',game.arm.read(game.pc.player+0x36,2))[0]

    def position():
        obj=game.arm.u32(game.pc.player)
        body=game.arm.u32(obj+0x120)
        return struct.unpack('<fff',game.arm.read(body+0x88,12))

    def yaw():
        body=game.arm.u32(game.arm.u32(game.pc.player)+0x120)
        return struct.unpack('<f',game.arm.read(body+0xa4,4))[0]*360/65536

    def pitch():
        obj=game.arm.u32(game.pc.player)
        return game.pc.aim_base_pitch-(struct.unpack('<f',game.arm.read(obj+0x130,4))[0]-32768)/3*360/65536

    def camera_angles():
        view=game.pc.last_view
        vector=[b-a for a,b in zip(view['eye'],view['adjusted_target'])]
        return (math.degrees(math.atan2(vector[0],vector[2])),
                math.degrees(math.atan2(vector[1],math.hypot(vector[0],vector[2]))))

    def delta_angle(before,after):return (after-before+180)%360-180

    def bullets():
        case=game.arm.call('_ZN12GM_CtrlParam8Get_InstEv')
        category=game.arm.read(game.pc.player+0x5e,1)[0]
        return game.arm.call('_ZN16Bio4_AttacheCase16GetLoadBulletNumEl',case,category)

    game.graphics.sdl.SDL_SetWindowTitle(game.graphics.window,b'VISIBLE PC CONTROL TEST - WASD, mouse aim, fire, reload')
    game.desktop_input.release();game.desktop_input.flush();game.pc.release()
    game.pc.aim_owned=True
    game.mouse_released=False
    advance(45)
    assert game.mouse_captured,'Gameplay did not capture cursor'
    # Exercise the original mission clock rather than inferring its rate
    # from host FPS. This fixture has private saves/resources.
    mission=game.arm.call('_ZN13GM_MisConduct8Get_InstEv')
    params=game.arm.call('_ZN12GM_CtrlParam8Get_InstEv')
    limit_get='_ZN12GM_CtrlParam16Get_MisLimitTimeEv'
    limit_set='_ZN12GM_CtrlParam16Set_MisLimitTimeEs'
    old_limit=game.arm.call(limit_get,params)
    old_ticks=game.arm.u32(mission)
    old_enabled=game.arm.read(mission+0x10,1)
    total_get='_ZN12GM_CtrlParam15Get_MisTotalSecEv'
    before_total=game.arm.call(total_get,params)
    try:
        game.arm.call(limit_set,params,120)
        game.arm.w32(mission,0)
        game.arm.write(mission+0x10,b'\x01')
        started=time.monotonic()
        advance(20)
        elapsed=time.monotonic()-started
        remaining=game.arm.call(limit_get,params)
        total=game.arm.call(total_get,params)
        assert remaining==119,('Native mission clock did not advance one second in 20 updates',remaining)
        assert total==before_total+1,('Native elapsed game time',before_total,total)
        assert elapsed>=0.9,('Host accelerated gameplay',elapsed)
        evidence['native_clock']={'updates':20,'game_seconds':120-remaining,'wall_seconds':round(elapsed,3)}
        print('CONTROL_PASS native_clock',json.dumps(evidence['native_clock']),flush=True)
    finally:
        game.arm.call(limit_set,params,old_limit)
        game.arm.w32(mission,old_ticks)
        game.arm.write(mission+0x10,old_enabled)
    capture('before')
    # Collision traces use the camera object's eye/target, so the rendered
    # view must use those same vectors throughout a sustained mouse sweep.
    camera=game.arm.call('_ZNK18GM_CtrlMain_Camera10Get_ErpCamEv',game.arm.call('_ZNK11GM_CtrlMain11Get_CtrlCamEv',game.pc.main))
    target_origin=game.pc.last_view['target']
    orbit_radius=math.dist(game.pc.last_view['eye'],target_origin)
    for name,dx,dy,count in [('sweep_right',80,0,30),('sweep_left',-80,0,30),
                             ('sweep_up',0,-20,15),('sweep_down',0,20,30),
                             ('sweep_level',0,-20,15)]:
        for step in range(count):
            push(0x400,dx=dx,dy=dy);advance()
            view=game.pc.last_view
            native_target=struct.unpack('<fff',game.arm.read(camera+0x1c,12))
            assert math.dist(native_target,view['adjusted_target'])<0.1,('Rendering and collision targets differ',name,step,native_target,view)
            # A stationary turn may rotate the shoulder offset, but must not
            # drag the orbit anchor across the map toward the world origin.
            assert math.dist(native_target,target_origin)<orbit_radius,('Camera anchor left Leon',name,step,target_origin,native_target)
            assert abs(camera_angles()[1]+game.pc.look_pitch)<0.1,(name,step,camera_angles())
            if step in (count//4,count//2,3*count//4):capture(name+'_'+str(step))
        capture(name)
        evidence[name]={'frames':count,'camera':camera_angles(),'pitch':game.pc.look_pitch,'target':game.pc.last_view['target'],'origin':target_origin,'orbit_radius':orbit_radius}
        print('CONTROL_PASS',name,json.dumps(evidence[name]),flush=True)
    for name,dx,dy in [('look_right',20,0),('look_left',-20,0),('look_up',0,-20),('look_down',0,20)]:
        rotation=yaw();look_pitch=game.pc.look_pitch
        camera_before=camera_angles()
        push(0x400,dx=dx,dy=dy);advance()
        turned=delta_angle(rotation,yaw())
        if dx:assert abs(turned+dx*0.15)<0.1,(name,turned)
        if dy:
            assert abs(game.pc.look_pitch-look_pitch-dy*0.15)<0.1
            assert game.pc.last_view and game.pc.last_view['pitch']==game.pc.look_pitch
            assert game.pc.last_view['target']==game.pc.last_view['adjusted_target']
        advance(15)
        camera_after=camera_angles()
        if dx:assert abs(abs(delta_angle(camera_before[0],camera_after[0]))-3)<0.5,(name,'camera did not turn',camera_before,camera_after)
        if dy:assert abs(camera_after[1]+game.pc.look_pitch)<0.1,(name,'camera points in wrong direction',camera_after)
        capture(name);evidence[name]={'yaw_delta':turned,'pitch_delta':game.pc.look_pitch-look_pitch,'camera_before':camera_before,'camera_after':camera_after}
        print('CONTROL_PASS',name,json.dumps(evidence[name]),flush=True)
    for letter,flag,expected_x,expected_y in [('w',1,0,100),('s',2,0,-100),('a',4,100,0),('d',8,-100,0)]:
        before=position();rotation=yaw()
        push(0x300,ord(letter));advance()
        assert game.pc.last_sample['x']==expected_x and game.pc.last_sample['y']==expected_y
        assert game.arm.call('_ZN16GM_CtrlLyt_Input13Get_InputScanEv',game.pc.controller)&flag
        advance(20)
        after=position();turned=delta_angle(rotation,yaw())
        if letter in ('w','s'):assert math.dist(before,after)>0.01,(letter,'Leon did not move',before,after,state())
        else:assert (turned>0 if letter=='a' else turned<0),(letter,'wrong turn direction',rotation,yaw(),state())
        evidence[letter]={'before':before,'after':after,'yaw_delta':turned}
        capture(letter)
        push(0x301,ord(letter));advance(5)
        assert game.pc.last_sample['x']==0 and game.pc.last_sample['y']==0,(letter,'release stuck')
        print('CONTROL_PASS',letter,json.dumps(evidence[letter]),flush=True)
    # Both transitions in one SDL poll still reach distinct engine frames.
    push(0x300,ord('a'));push(0x301,ord('a'));advance()
    assert game.pc.last_sample['x']==100
    advance();assert game.pc.last_sample['x']==0
    push(0x401,3);push(0x402,3);advance(90)
    assert not game.pc.last_sample['aiming'] and not game.pc.buttons,'Quick RMB tap left aim held'
    assert abs(camera_angles()[1])<0.1,'Quick RMB tap changed view pitch'
    evidence['quick_aim_release']='RMB down/up in one poll cancels aim before startup completes'
    print('CONTROL_PASS quick_aim_release',flush=True)
    push(0x401,3);advance(45)
    assert game.pc.last_sample['aiming'],('RMB did not aim',game.pc.last_sample,state())
    capture('aim')
    for name,dx,dy in [('mouse_right',20,0),('mouse_left',-20,0),('mouse_up',0,-20),('mouse_down',0,20)]:
        rotation=yaw();aim_pitch=pitch();camera_before=camera_angles()
        push(0x400,dx=dx,dy=dy);advance()
        turned=delta_angle(rotation,yaw());new_pitch=pitch()
        if dx:assert abs(turned+dx*0.15)<0.1,(name,turned)
        if dy:assert abs(new_pitch-aim_pitch-dy*0.15)<0.1,(name,aim_pitch,new_pitch)
        advance(15);capture(name)
        camera_after=camera_angles()
        if dx:assert abs(abs(delta_angle(camera_before[0],camera_after[0]))-3)<0.5,(name,'aim camera did not turn',camera_before,camera_after)
        if dy:assert abs(camera_after[1]-camera_before[1]+dy*0.15)<0.5,(name,'aim camera points in wrong direction',camera_before,camera_after)
        evidence[name]={'yaw_delta':turned,'pitch_delta':new_pitch-aim_pitch,'camera_before':camera_before,'camera_after':camera_after}
        print('CONTROL_PASS',name,json.dumps(evidence[name]),flush=True)
    # Continuous motion and repeated RMB transitions must not snap the blend
    # to zero or leave the camera staring at the ground after release.
    for _ in range(10):
        push(0x400,dy=-10);advance()
    advance(20)
    assert abs(pitch()+15)<0.1,('continuous upward aim',pitch())
    capture('aim_up_15')
    for attempt in range(3):
        push(0x402,3);advance(30)
        assert not game.pc.last_sample['aiming']
        assert abs(camera_angles()[1]-15)<0.1,('released camera lost pitch',camera_angles())
        push(0x401,3);advance(30)
        assert game.pc.last_sample['aiming']
        assert abs(pitch()+15)<0.1,('RMB snapped pitch',pitch())
        assert abs(camera_angles()[1]-15)<1,('RMB snapped camera',camera_angles())
    capture('aim_reentered_15')
    rotation=yaw();aim_pitch=pitch();view=camera_angles()
    advance(60)
    assert abs(delta_angle(rotation,yaw()))<0.1 and abs(pitch()-aim_pitch)<0.1,'Aim drifted without motion'
    assert abs(camera_angles()[1]-view[1])<0.1,'Camera drifted without motion'
    evidence['aim_transitions']={'cycles':3,'pitch':pitch(),'camera':camera_angles(),'stationary_frames':60}
    push(0x400,dy=100);advance(20)
    ammo=bullets()
    push(0x401,1);push(0x402,1);advance(35)
    remaining=bullets();assert remaining==ammo-1,('Click did not fire exactly once',ammo,remaining,state())
    evidence['fire']={'before':ammo,'after':remaining}
    capture('fired')
    print('CONTROL_PASS fire',ammo,remaining,flush=True)
    push(0x300,ord('r'));push(0x301,ord('r'));advance(90)
    reloaded=bullets();assert reloaded>remaining,('R did not reload',remaining,reloaded,state())
    evidence['reload']={'before':remaining,'after':reloaded}
    push(0x402,3);advance(45)
    assert not game.pc.last_sample['aiming'],'RMB release did not cancel aim'
    print('CONTROL_PASS right_mouse_release',flush=True)
    # The aiming flag clears before the holster animation finishes. A knife
    # trigger during that animation is intentionally ignored by the engine.
    for _ in range(180):
        if state() in (0,2):break
        advance()
    assert state() in (0,2),('Aim release did not finish its animation',state())
    push(0x300,ord('f'));advance(30)
    assert state()==2 and game.arm.read(game.pc.player+0x5e,1)[0]==1,('F did not ready knife',state())
    capture('knife');evidence['knife']={'state':state()}
    push(0x401,1);push(0x402,1);advance(3)
    assert state()==6 and game.arm.read(game.pc.player+0x5e,1)[0]==1,('Left click did not slash with knife',state())
    advance(30)
    push(0x301,ord('f'));advance(45)
    assert game.arm.read(game.pc.player+0x5e,1)[0]!=1,('F release left knife active',state())
    print('CONTROL_PASS knife',flush=True)
    for name,key,flag in [('arrow_up',1073741906,1),('arrow_down',1073741905,2),('arrow_left',1073741904,4),('arrow_right',1073741903,8),('action_e',ord('e'),32),('action_enter',13,32),('action_space',32,32)]:
        push(0x300,key);push(0x301,key);advance()
        assert game.arm.call('_ZN16GM_CtrlLyt_Input13Get_InputTrigEv',game.pc.controller)&flag,(name,game.pc.last_sample)
        advance(2)
        evidence[name]={'native_trigger':flag}
        print('CONTROL_PASS',name,flush=True)
    push(0x300,ord('x'));advance(45)
    assert game.pc.last_sample['aiming'], ('X did not aim', {'state':state(),
        'active':game.pc.active, 'story':game.pc.story_active,
        'item':game.pc.item_active, 'keys':sorted(game.pc.keys),
        'sample':game.pc.last_sample})
    ammo=bullets();push(0x300,ord('z'));push(0x301,ord('z'));advance(35)
    assert bullets()==ammo-1,'Z did not fire exactly once'
    push(0x301,ord('x'));advance(45)
    assert not game.pc.last_sample['aiming'],'X release did not cancel aim'
    evidence['keyboard_aim_fire']='X holds aim; Z fires; releasing X cancels aim'
    print('CONTROL_PASS keyboard_aim_fire',flush=True)
    push(0x401,3);advance(30)
    assert game.pc.last_sample['aiming']
    push(0x200);advance(45)
    assert not game.mouse_captured and not game.pc.last_sample['aiming'],'Focus loss left mouse captured or aiming'
    assert not game.pc.buttons and not game.pc.keys,'Focus loss left inputs held'
    ammo=bullets()
    push(0x401,1);push(0x402,1);advance(5)
    assert game.mouse_captured and bullets()==ammo,'Recapture click fired a shot'
    evidence['focus_release']='SDL focus loss releases aim and cursor; click recaptures without firing'
    print('CONTROL_PASS focus_release',flush=True)
    push(0x300,9);push(0x301,9);advance(3)
    assert not game.mouse_captured,'Tab did not release cursor'
    push(0x401,1);push(0x402,1);advance(3)
    assert game.mouse_captured,'Click did not recapture cursor'
    push(0x300,27);push(0x301,27);advance(40)
    assert not game.mouse_captured,'Escape did not open menu and release cursor'
    capture('menu')
    evidence['cursor']='Tab releases; click recaptures; Escape opens menu'
    (output/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print('PC_CONTROLS_PASS',json.dumps(evidence),flush=True)


if __name__=='__main__':
    import sys
    import argparse
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    from re4pc.game import Game
    from re4pc.timing import FramePacer
    from re4pc.paths import game_dir, isolated_game, test_output
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,default=game_dir())
    parser.add_argument('--output',type=Path)
    parser.add_argument('--hidden',action='store_true',help='Render a hidden SDL window for injected-event replay; does not certify physical cursor capture')
    args=parser.parse_args()
    output=test_output('pc-controls',args.output)
    test_root=isolated_game(args.game,output)
    print('Test artifacts:',output,flush=True)
    game=Game(test_root,skip_videos=True,hidden=args.hidden)
    try:
        from unicorn import UC_HOOK_CODE
        from unicorn.arm_const import UC_ARM_REG_R0
        ui=set()
        ui_hooks=[]
        title=[0]
        story_selected=False
        pacer=FramePacer()
        def observe(uc,address,size,context,name):
            ui.add(name)
            if 'Task_Title5Frame' in name:title[0]=uc.reg_read(UC_ARM_REG_R0)
        for symbol,address in game.arm.symbols.items():
            if ('Bio4_CTTask_' in symbol or 'GM_Task_Mis_' in symbol) and '5FrameEPv' in symbol:
                ui_hooks.append(game.arm.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,c,name=symbol: observe(uc,a,s,c,name),begin=address&~1,end=address&~1))
        def frames(count):
            for _ in range(count):
                for event in game.graphics.events():
                    if event==('quit',) or event==('key',True,1073741893):raise RuntimeError('Test interrupted')
                ui.clear();game.frame();game.graphics.swap();pacer.wait()
            game.graphics.screenshot(output/'pc-navigation.png')
        def click(x,y):
            game.event(('touch',True,x,y));frames(4)
            game.event(('touch',False,x,y));frames(150)
            game.frame();game.graphics.screenshot(output/'pc-navigation.png');game.graphics.swap()
            print('NAV',x,y,'frame',game.frames,'active',game.pc.active,'story',game.pc.story_active,flush=True)
        frames(200)
        # Isolated fixture: clear the tutorial and select story mission 2.
        user=game.arm.symbols['_ZZN13Bio4_UserData11GetInstanceEvE4inst']
        game.arm.call('_ZN13Bio4_UserData19SetMissionClearFlagEllb',user,0,0,1)
        game.arm.call('_ZN13Bio4_UserData16SetLastMissionIDEhs',user,0,1)
        game.arm.call('_ZN13Bio4_UserData12SetMissionIDEs',user,1)
        for _ in range(40):
            if game.pc.active:break
            current=' '.join(ui)
            print('UI',current,flush=True)
            if 'DataReset' in current:click(400,405)
            elif 'NewNotice' in current:click(742,416)
            elif 'DiffConf' in current:
                game.event(('touch',True,240,320));frames(4)
                game.event(('motion',550,320));frames(4)
                game.event(('touch',False,550,320));frames(150)
            elif 'DiffTop' in current:click(400,415)
            elif 'MissionSelectStory' in current:
                click(60,240) if story_selected else click(400,200)
                story_selected=True
            elif 'MissionSelectMercenary' in current:click(400,110)
            elif 'TitleTop' in current:click(400,128)
            elif 'Task_Title5Frame' in current:
                step=game.arm.u32(title[0]+8)
                print('TITLE_STEP',step,flush=True)
                if step==1:click(400,390)
                elif step==4:click(400,128)
                else:frames(150)
            elif 'GameMain' in current or 'Mis_Main' in current:click(60,416)
            else:frames(150)
        for hook in ui_hooks: game.arm.uc.hook_del(hook)
        check_gameplay(game,output)
    finally:game.close()
