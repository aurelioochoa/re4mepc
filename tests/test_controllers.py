import unittest
from re4pc.controllers import ControllerInput
from re4pc.actions import virtual_key
from re4pc.input import DesktopInput
from re4pc.settings import validate


class ControllerTests(unittest.TestCase):
    def test_look_uses_controller_sensitivity_with_a_distinct_event(self):
        pad=ControllerInput(settings={'sensitivity':4,'controller_sensitivity':2})
        pad.process(('controller_axis',7,2,32767))
        self.assertIn(('controller_look',60.0,0.0),pad.tick(gameplay=True))

    def test_quick_tap_preserved_by_desktop_sampling(self):
        pad=ControllerInput()
        pad.gameplay=True
        pad.process(('controller_button',True,7,0))
        pad.process(('controller_button',False,7,0))
        held=set()
        input=DesktopInput(lambda *args:None,lambda down,key:held.add(key) if down else held.discard(key))
        for event in pad.tick(gameplay=True):input.enqueue(event)
        input.flush()
        self.assertEqual(held,{virtual_key('action')})
        input.flush()
        self.assertEqual(held,set())

    def test_disconnect_releases_only_removed_controller(self):
        pad=ControllerInput()
        pad.gameplay=True
        pad.process(('controller_button',True,7,0))
        pad.process(('controller_button',True,8,0))
        self.assertEqual(pad.tick(gameplay=True),[('key',True,virtual_key('action'))])
        pad.process(('controller_removed',7))
        self.assertEqual(pad.tick(gameplay=True),[])
        pad.process(('controller_removed',8))
        self.assertEqual(pad.tick(gameplay=True),[('key',False,virtual_key('action'))])

    def test_dead_zone_axes_trigger_and_focus_release(self):
        pad=ControllerInput()
        pad.process(('controller_axis',7,0,1000))
        self.assertEqual(pad.tick(gameplay=True),[])
        pad.process(('controller_axis',7,1,-32768))
        pad.process(('controller_axis',7,4,20000))
        events=pad.tick(gameplay=True)
        self.assertIn(('key',True,virtual_key('forward')),events)
        self.assertIn(('key',True,virtual_key('aim')),events)
        pad.process(('focus_lost',))
        events=pad.tick(gameplay=True)
        self.assertIn(('key',False,virtual_key('forward')),events)
        self.assertIn(('key',False,virtual_key('aim')),events)
        self.assertEqual(pad.tick(gameplay=True),[])

    def test_menu_buttons_are_keys_and_right_stick_has_no_pointer(self):
        pad=ControllerInput()
        pad.process(('controller_button',True,7,0))
        self.assertEqual(pad.tick(),[('key',True,virtual_key('action'))])
        pad.process(('controller_axis',7,2,32767))
        self.assertEqual(pad.tick(),[])
        pad.process(('controller_button',False,7,0))
        self.assertEqual(pad.tick(),[('key',False,virtual_key('action'))])

    def test_reconfigure_releases_old_action_and_applies_new_binding(self):
        pad=ControllerInput()
        pad.gameplay=True
        pad.process(('controller_button',True,7,0))
        pad.tick(gameplay=True)
        values=validate({})
        values['bindings']['controller']['action']=[]
        values['bindings']['controller']['fire']=['a']
        pad.configure(values)
        self.assertIn(('key',False,virtual_key('action')),pad.tick(gameplay=True))
        pad.process(('controller_button',True,7,0))
        self.assertIn(('key',True,virtual_key('fire')),pad.tick(gameplay=True))

    def test_disconnect_discards_queued_down_without_ghost_tap(self):
        pad=ControllerInput()
        pad.gameplay=True
        pad.process(('controller_button',True,7,0))
        pad.process(('controller_removed',7))
        events=pad.tick(gameplay=True)
        self.assertNotIn(('key',True,virtual_key('action')),events)

    def test_axis_outside_sdl_range_ignored(self):
        pad=ControllerInput()
        self.assertTrue(pad.process(('controller_axis',7,99,123)))
        self.assertEqual(pad.tick(),[])

    def test_sdl_lifecycle_duplicate_add_and_disconnect_close_handles(self):
        from unittest.mock import Mock
        sdl=Mock()
        sdl.SDL_NumJoysticks.return_value=1
        sdl.SDL_IsGameController.return_value=1
        sdl.SDL_GameControllerOpen.side_effect=[100,200]
        sdl.SDL_GameControllerGetJoystick.return_value=101
        sdl.SDL_JoystickInstanceID.return_value=7
        pad=ControllerInput(sdl)
        self.assertEqual(pad.handles,{7:100})
        pad.process(('controller_added',0))
        sdl.SDL_GameControllerClose.assert_called_once_with(200)
        pad.process(('controller_removed',7))
        self.assertEqual(sdl.SDL_GameControllerClose.call_args.args,(100,))
        self.assertEqual(pad.handles,{})

    def test_queued_shared_action_survives_first_source_disconnect(self):
        pad=ControllerInput()
        pad.gameplay=True
        pad.process(('controller_button',True,7,0))
        pad.process(('controller_button',True,8,0))
        pad.process(('controller_removed',7))
        self.assertEqual(pad.tick(gameplay=True),[('key',True,virtual_key('action'))])
        pad.process(('controller_removed',8))
        self.assertEqual(pad.tick(gameplay=True),[('key',False,virtual_key('action'))])

    def test_queued_release_survives_disconnect_before_tick(self):
        pad=ControllerInput()
        pad.gameplay=True
        pad.process(('controller_button',True,7,0))
        pad.tick(gameplay=True)
        pad.process(('controller_button',False,7,0))
        pad.process(('controller_removed',7))
        self.assertEqual(pad.tick(gameplay=True),[('key',False,virtual_key('action'))])


class GameControllerRoutingTests(unittest.TestCase):
    def setUp(self):
        from types import SimpleNamespace
        from re4pc.game import Game
        from re4pc.actions import key_map, MouseBindings
        self.events=[]
        self.pad=ControllerInput()
        self.game=Game.__new__(Game)
        self.game.pc=SimpleNamespace(enabled=True,active=False,item_active=False,story_active=False,
            key=lambda down,code:self.events.append(('pc',down,code)),release=lambda:None)
        self.game.jni=SimpleNamespace(activity=1,native=lambda *args:self.events.append(args))
        self.game.media=SimpleNamespace(video=None)
        self.game.graphics=SimpleNamespace(controller=self.pad)
        self.game.keymap=key_map()
        self.game.mouse_bindings=MouseBindings()
        self.game.key_sources={}
        self.game.key_routes={}
        self.game.story_keys=set()
        self.game.mouse_captured=self.game.mouse_released=self.game.skipping_touch=False
        self.game.input_events=0
        self.game.touch_previous=(0,0)
        self.game.desktop_input=DesktopInput(self.game.touch,self.game.key)

    def tick(self):
        for event in self.pad.tick(gameplay=self.game.pc.active):self.game.event(event)
        self.game.desktop_input.flush()

    def test_startup_confirm_and_dpad_use_native_menu_keys(self):
        self.game.event(('controller_button',True,7,1))  # B confirm
        self.tick()
        self.game.event(('controller_button',False,7,1))
        self.tick()
        self.game.event(('controller_button',True,7,12))  # D-pad down
        self.tick()
        self.game.event(('controller_button',False,7,12))
        self.tick()
        self.assertEqual([(event[0],event[1]) for event in self.events],
            [('native_onKeyDown',66),('native_onKeyUp',66),('native_onKeyDown',20),('native_onKeyUp',20)])

    def test_menu_action_button_reaches_native_key_without_a_touch(self):
        self.game.event(('controller_button',True,7,0))
        self.tick()
        self.game.event(('controller_button',False,7,0))
        self.tick()
        self.assertEqual([(event[0],event[1]) for event in self.events],
            [('native_onKeyDown',23),('native_onKeyUp',23)])

    def test_controller_release_keeps_gameplay_route_after_menu_opens(self):
        self.game.pc.active=True
        self.game.event(('controller_button',True,7,3))  # knife Y
        self.tick()
        self.game.pc.active=False
        self.game.event(('controller_button',False,7,3))
        self.tick()
        self.assertEqual(self.events,[('pc',True,11),('pc',False,11)])


@unittest.skipUnless(__import__('os').environ.get('RE4PC_CONTROLLER_GAME'),
                     'Set RE4PC_CONTROLLER_GAME for isolated real-engine SDL controller verification')
class RealEngineControllerTests(unittest.TestCase):
    # Explicit method invocation keeps this external-data fixture out of the
    # default component suite without weakening that suite's success oracle.
    def verify_virtual_sdl_controller_navigates_startup_slider_and_gameplay(self):
        import os
        import ctypes as C
        import json
        from pathlib import Path
        from unittest.mock import patch
        from unicorn import UC_HOOK_CODE
        from re4pc.game import Game
        from re4pc.paths import isolated_game, test_output
        from re4pc.timing import FramePacer
        output=test_output('controller',os.environ.get('RE4PC_CONTROLLER_OUTPUT'))
        fixture=isolated_game(Path(os.environ['RE4PC_CONTROLLER_GAME']),output)
        print('CONTROLLER_ARTIFACTS',str(output),flush=True)
        with patch.dict('os.environ',{'SDL_VIDEODRIVER':'offscreen','SDL_AUDIODRIVER':'dummy'}):
            game=Game(fixture,hidden=True,skip_videos=True,diagnostics=False)
        joystick=None
        virtual_index=None
        hooks=[]
        try:
            sdl=game.graphics.sdl
            sdl.SDL_SetHint.argtypes=(C.c_char_p,C.c_char_p)
            sdl.SDL_SetHint(b'SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS',b'1')
            signatures={'SDL_JoystickAttachVirtual':(C.c_int,(C.c_int,)*4),
                        'SDL_JoystickDetachVirtual':(C.c_int,(C.c_int,)),
                        'SDL_JoystickOpen':(C.c_void_p,(C.c_int,)),
                        'SDL_JoystickClose':(None,(C.c_void_p,)),
                        'SDL_JoystickSetVirtualAxis':(C.c_int,(C.c_void_p,C.c_int,C.c_int16)),
                        'SDL_JoystickSetVirtualButton':(C.c_int,(C.c_void_p,C.c_int,C.c_uint8)),
                        'SDL_JoystickUpdate':(None,())}
            for name,(result,args) in signatures.items():
                function=getattr(sdl,name)
                function.restype,function.argtypes=result,args
            virtual_index=sdl.SDL_JoystickAttachVirtual(1,6,15,0)
            self.assertGreaterEqual(virtual_index,0)
            self.assertTrue(sdl.SDL_IsGameController(virtual_index))
            joystick=sdl.SDL_JoystickOpen(virtual_index)
            self.assertTrue(joystick)
            # Triggers idle at -32768 in SDL's virtual joystick API.
            for axis in (4,5):sdl.SDL_JoystickSetVirtualAxis(joystick,axis,-32768)
            pacer=FramePacer()
            ui=set()
            visited=set()
            slider_count=0
            def observe(uc,address,size,context,name):
                ui.add(name)
            for symbol,address in game.arm.symbols.items():
                if ('Bio4_CTTask_' in symbol or 'GM_Task_Mis_' in symbol) and '5FrameEPv' in symbol:
                    hooks.append(game.arm.uc.hook_add(UC_HOOK_CODE,
                        lambda uc,a,s,c,name=symbol:observe(uc,a,s,c,name),begin=address&~1,end=address&~1))
            def frames(count=1):
                for _ in range(count):
                    sdl.SDL_JoystickUpdate()
                    for event in game.graphics.events():game.event(event)
                    ui.clear()
                    game.frame()
                    pacer.wait()
                visited.update(ui)
            def axis(index,value):
                self.assertEqual(sdl.SDL_JoystickSetVirtualAxis(joystick,index,value),0)
            def button(index,down):
                self.assertEqual(sdl.SDL_JoystickSetVirtualButton(joystick,index,down),0)
            def press(index=0):
                # Menus are navigated by focus; A presses the focused control.
                button(index,1);frames(4)
                button(index,0);frames(150)
            frames(200)
            self.assertTrue(game.graphics.controller.handles)
            user=game.arm.symbols['_ZZN13Bio4_UserData11GetInstanceEvE4inst']
            # Select a known gameplay fixture; all UI input remains controller
            # input, and every writable file belongs to the isolated copy.
            game.arm.call('_ZN13Bio4_UserData19SetMissionClearFlagEllb',user,0,0,1)
            game.arm.call('_ZN13Bio4_UserData16SetLastMissionIDEhs',user,0,1)
            game.arm.call('_ZN13Bio4_UserData12SetMissionIDEs',user,1)
            for _ in range(40):
                if game.pc.active:break
                current=' '.join(ui)
                print('CONTROLLER_NAV',game.frames,current,game.menu.state,flush=True)
                game.graphics.screenshot(output/'controller-navigation.png')
                focused=game.menu.focused()
                if focused and focused.kind=='SliderButton':slider_count+=1
                if game.menu.active:press()
                else:frames(150)
            self.assertTrue(game.pc.active,'Controller UI navigation did not reach gameplay')
            self.assertGreater(slider_count,0,'No confirmation slider exercised')
            axis(1,-32768);frames(3)
            self.assertEqual(game.pc.last_sample['y'],100)
            axis(1,0);frames(3)
            self.assertEqual(game.pc.last_sample['y'],0)
            # The two sensitivity controls must be independent through actual
            # SDL events and native camera state, not only the event adapter.
            import struct
            settings=validate({'sensitivity':4,'controller_sensitivity':2})
            game.configure_controls(settings)
            def yaw():
                body=game.arm.u32(game.arm.u32(game.pc.player)+0x120)
                return struct.unpack('<f',game.arm.read(body+0xa4,4))[0]*360/65536
            before=yaw()
            axis(2,32767);frames(3)
            axis(2,0);frames()
            look_delta=(yaw()-before+180)%360-180
            self.assertAlmostEqual(look_delta,-27.0,delta=1.0)
            game.graphics.screenshot(output/'controller-gameplay.png')
            evidence={'frames':game.frames,'slider_drags':slider_count,'gameplay':game.pc.active,
                      'controller_sources':'SDL_JoystickAttachVirtual + SDL virtual axis/button APIs',
                      'visited':sorted(visited),'isolated_game':str(fixture),
                      'controller_look_degrees':look_delta,
                      'mouse_sensitivity':4,'controller_sensitivity':2}
            (output/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
            print('CONTROLLER_ENGINE_PASS',str(output),flush=True)
        finally:
            for hook in hooks:game.arm.uc.hook_del(hook)
            if joystick:sdl.SDL_JoystickClose(joystick)
            if virtual_index is not None and virtual_index>=0:sdl.SDL_JoystickDetachVirtual(virtual_index)
            game.close()
