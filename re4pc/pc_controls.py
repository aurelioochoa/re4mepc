"""Translate desktop controls into the original game's gameplay input channel."""
import math
import struct
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP
from .bionic import float_out

# Set_TurnY accepts a floating point binary angle, not degrees. Aim pitch
# is an animation blend in [0, 65536], with 32768 neutral; _Set_AimingCam
# subtracts (pitch - 32768) / 3 from its binary camera rotation. Increasing
# the blend looks up; desktop look_pitch increases when looking down.
TURN = 65536.0
AIM_CENTER = TURN / 2
AIM_UNITS_PER_DEGREE = 3 * TURN / 360
MOUSE_DEGREES_PER_PIXEL = 0.15
# Set_LookAt_Bind orbits without a pitch clamp. Stop just short of vertical:
# at 90 degrees the view direction is parallel to the camera's up vector.
# While aiming, the [0, 65536] blend range bounds pitch to 60 degrees.
PITCH_LIMIT = 89.0

# Keep one click through the weapon's short startup/recovery animation.
# At 20 Hz this expires after one second; menus, damage and releasing aim
# cancel it sooner. These states/fields are from the supported native player.
FIRE_BUFFER_FRAMES = 20
FIRE_BUFFER_STATES = (0, 1, 2, 4, 5, 6, 7, 19)

# LYT_Cmp_VirtualPad posts a flick when a touch lands in the same pad
# direction as the previous one while its 5-frame counter is running.
# GM_CtrlLyt_Input turns up, down, left and right into these trigger bits.
# _State_AtkAimM plays the sidestep for each (motions 0x11-0x14) and
# then restarts aiming; _State_Move uses down for the quick turn (motion 7).
DOUBLE_TAP_FRAMES = 5
DOUBLE_TAP_TRIGGERS = {19: 0x4000, 20: 0x8000, 21: 0x10000, 22: 0x20000}
# Set_MvtPlay enters this state, then changes to the state at +0x64.
MVT_PLAY_STATE = 33
AIM_START_STATE = 1

# Fields in the supported GM_CtrlLyt_Input layout: Pad, ActBtn_Post
# (lower weapon), ActBtn_Gun and ActBtn_Knif. Event, Ashley, scope and
# menu components remain visible. LYT_CmpProduct's visibility is separate
# from its input enable flag.
TOUCH_COMBAT_COMPONENTS = (0x04, 0x08, 0x14, 0x18)
TOUCH_UI_COMPONENTS = (0x0c, 0x10, 0x1c, 0x20)
COMPONENT_VISIBLE = 0x51


class PCControls:
    def __init__(self, arm, enabled=True, settings=None):
        self.arm, self.enabled = arm, enabled
        self.sensitivity = (settings or {}).get("sensitivity", 1.0)
        self.invert_y = (settings or {}).get("invert_y", False)
        self.keys = set()
        self.buttons = set()
        self.motion = [0, 0]
        self.active = False
        self.player = self.main = self.controller = 0
        self.previous_scan = 0
        self.aim_owned = False
        self.knife_owned = False
        self.frames = 0
        self.menu_requested = self.action_requested = False
        self.last_sample = {}
        self.fire_down = self.fire_forwarded = False
        self.fire_pending_until = -1
        self.reload_requested = False
        self.tap_code = None
        self.tap_frame = 0
        self.flick_requested = self.flick_this_frame = 0
        self.story_active = False
        self.item_active = False
        self.item_take_requested = False
        self.item_take_this_frame = False
        self.look_pitch=0.0
        self.aim_base_pitch=0.0
        self.last_view={}
        self.hud_visibility = []

    def install(self):
        symbol='_ZN16GM_CtrlLyt_Input5FrameEP14Bio4_FrameWork'
        # assets.validate checks both library hashes before Game loads them.
        # In that supported layout the Thumb epilogue retains `this` at SP+4.
        epilogue=(self.arm.symbols[symbol]&~1)+self.arm.symbol_sizes[symbol]-4
        self.arm.uc.hook_add(UC_HOOK_CODE,self._update,begin=epilogue,end=epilogue)
        start=self.arm.symbols['_ZN18GM_CtrlMain_Player9Set_StartEP11GM_CtrlMain']&~1
        self.arm.uc.hook_add(UC_HOOK_CODE,self._player,begin=start,end=start)
        # Set_LookAt_Bind builds the orbit from the camera's Euler angles on
        # every gameplay frame, before the behind camera checks collisions.
        bind=self.arm.symbols['_ZN10ERP_Camera15Set_LookAt_BindEv']&~1
        self.arm.uc.hook_add(UC_HOOK_CODE,self._camera_pose,begin=bind,end=bind)
        look=self.arm.symbols['_ZN10ERP_Camera13Set_ViewTransEP11tagVector3DS1_S1_']&~1
        self.arm.uc.hook_add(UC_HOOK_CODE,self._camera,begin=look,end=look)
        aim=self.arm.symbols['_ZN18GM_CtrlMain_Player17_Set_AimStartRotXEP11GM_CtrlMainf']&~1
        self.arm.uc.hook_add(UC_HOOK_CODE,self._aim_start,begin=aim,end=aim)
        if self.enabled:
            item_symbol='_ZN18GM_CtrlLyt_WinItem5FrameEv'
            item_end=(self.arm.symbols[item_symbol]&~1)+self.arm.symbol_sizes[item_symbol]-4
            self.arm.uc.hook_add(UC_HOOK_CODE,self._item_window,begin=item_end,end=item_end)
            draw_symbol='_ZN16GM_CtrlLyt_Input4DrawEP14Bio4_FrameWork'
            draw=self.arm.symbols[draw_symbol]&~1
            end=draw+self.arm.symbol_sizes[draw_symbol]-4
            self.arm.uc.hook_add(UC_HOOK_CODE,self._hud_begin,begin=draw,end=draw)
            self.arm.uc.hook_add(UC_HOOK_CODE,self._hud_end,begin=end,end=end)

    def _item_window(self,uc,address,size,context):
        try:
            if not self.enabled:return
            # WinItem::Frame retains `this` at SP+4 before its epilogue.
            window=self.arm.u32(uc.reg_read(UC_ARM_REG_SP)+4)
            if not self.arm.read(window+0x20,1)[0] or not self.arm.u32(window+4):return
            self.item_active=True
            if not self.item_take_this_frame:return
            self.item_take_this_frame=False
            take=self.arm.u32(window+0x14)
            if take and self.arm.read(take+0x50,2)==b'\x01\x01':
                # Use the same GET trigger as the native Take button. The
                # engine still handles inventory limits and removing the item.
                self.arm.w32(window+0x24,self.arm.u32(window+0x24)|4)
        except BaseException as error:
            self.arm.pending_error=error;uc.emu_stop()

    def _hud_begin(self,uc,address,size,context):
        try:
            if not self.enabled:return
            ctrl=uc.reg_read(UC_ARM_REG_R0)
            if not self.arm.read(ctrl+0x40,1)[0] or not self.arm.u32(ctrl):return
            # Mask only this draw pass. Restore the native flags afterwards
            # so animation, input and subsequent weapon transitions retain
            # the engine's own state, including controls already hidden.
            for offset in TOUCH_COMBAT_COMPONENTS:
                component=self.arm.u32(ctrl+offset)
                if component:
                    flag=component+COMPONENT_VISIBLE
                    self.hud_visibility.append((flag,self.arm.read(flag,1)))
                    self.arm.write(flag,b'\0')
        except BaseException as error:
            self.arm.pending_error=error;uc.emu_stop()

    def _hud_end(self,uc,address,size,context):
        try:
            for flag,visible in self.hud_visibility:
                self.arm.write(flag,visible)
            self.hud_visibility.clear()
        except BaseException as error:
            self.arm.pending_error=error;uc.emu_stop()

    def _aim_start(self,uc,address,size,context):
        if self.enabled and self.active and (3 in self.buttons or 9 in self.keys or 11 in self.keys or self.aim_owned or self.knife_owned):
            # The engine normally starts from the idle animation's pitch.
            # Its camera also has a base X rotation in the player's +0x14
            # vector. Compensate that offset to retain the desktop view angle.
            self.aim_base_pitch=struct.unpack('<f',self.arm.read(self.player+0x14,4))[0]*360/TURN
            pitch=max(0,min(TURN,AIM_CENTER+(self.aim_base_pitch-self.look_pitch)*AIM_UNITS_PER_DEGREE))
            uc.reg_write(UC_ARM_REG_R2,float_out(pitch))

    def _gameplay_camera(self):
        if not self.enabled or not self.main or not self.player:return False
        if not self.arm.read(self.main+0x61,1)[0]:return False
        event=self.arm.u32(self.main+0x3c)
        return not (event and self.arm.read(event+0x31c,1)[0])

    def _camera_pose(self,uc,address,size,context):
        try:
            if not self._gameplay_camera() or self.arm.read(self.player+0x48,1)[0]:return
            camera=uc.reg_read(UC_ARM_REG_R0)
            # Change the orbit pitch, not just the final view matrix. The
            # native eye, target, up vector and wall collision ray then agree.
            # This is absolute: repeated binds cannot accumulate rotation.
            self.arm.write(camera+0x10,struct.pack('<f',self.look_pitch*TURN/360))
        except BaseException as error:
            self.arm.pending_error=error;uc.emu_stop()

    def _camera(self,uc,address,size,context):
        try:
            if not self._gameplay_camera():return
            eye=struct.unpack('<fff',self.arm.read(uc.reg_read(UC_ARM_REG_R1),12))
            target=struct.unpack('<fff',self.arm.read(uc.reg_read(UC_ARM_REG_R3),12))
            aiming=bool(self.arm.read(self.player+0x48,1)[0])
            self.last_view={'eye':eye,'target':target,'adjusted_target':target,'pitch':self.look_pitch,'aiming':aiming}
        except BaseException as error:
            self.arm.pending_error=error;uc.emu_stop()

    def _player(self, uc, address, size, context):
        self.player=uc.reg_read(UC_ARM_REG_R0)
        self.main=uc.reg_read(UC_ARM_REG_R1)
        self.look_pitch=0.0
        self.motion[:]=[0,0]
        self._clear_fire()

    def key(self, down, code):
        if down and code==23 and code not in self.keys and self.item_active:
            self.item_take_requested=True
        if down and code==12 and code not in self.keys:self.reload_requested=True
        if down and code in DOUBLE_TAP_TRIGGERS and code not in self.keys:
            if code==self.tap_code and self.frames-self.tap_frame<=DOUBLE_TAP_FRAMES:
                # Like the pad, a third tap starts a new pair.
                self.flick_requested=DOUBLE_TAP_TRIGGERS[code];self.tap_code=None
            else:self.tap_code,self.tap_frame=code,self.frames
        if down: self.keys.add(code)
        else: self.keys.discard(code)

    def button(self, down, button):
        if down: self.buttons.add(button)
        else: self.buttons.discard(button)

    def pointer_target(self, x, y):
        """Hit-test the native interaction, companion, scope and menu buttons."""
        ctrl = self.controller
        if not (self.enabled and self.active and ctrl and
                self.arm.read(ctrl+0x40, 1)[0] and self.arm.u32(ctrl)):
            return False
        for offset in TOUCH_UI_COMPONENTS:
            component = self.arm.u32(ctrl+offset)
            if not component or self.arm.read(component+0x50, 2) != b'\x01\x01':
                continue
            # Native Button::_doWait uses its touch rectangle; PushButton
            # uses the normal image's screen rectangle. Rect4i starts with
            # a vtable, followed by x, y, width and height.
            handler = self.arm.u32(self.arm.u32(component)+0x2c)
            if handler == self.arm.symbols['_ZN18LYT_Cmp_PushButton9doMsgProcEmPv']:
                image = self.arm.u32(component+0x94)
                if not image: continue
                rectangle = image+0x3c
            elif handler == self.arm.symbols['_ZN14LYT_Cmp_Button9doMsgProcEmPv']:
                rectangle = component+0xb8
            else:
                continue
            left, top, width, height = struct.unpack('<4i', self.arm.read(rectangle, 16))
            if width > 0 and height > 0 and left <= x <= left+width and top <= y <= top+height:
                return True
        return False

    def move(self, dx, dy, *, sensitivity=None):
        scale = self.sensitivity if sensitivity is None else sensitivity
        self.motion[0]+=dx*scale
        self.motion[1]+=dy*scale*(-1 if self.invert_y else 1)

    def release(self):
        self.keys.clear();self.buttons.clear();self.motion[:]=[0,0]
        self.previous_scan=0
        self.reload_requested=False
        self.item_take_requested=self.item_take_this_frame=False
        self.tap_code=None
        self.flick_requested=self.flick_this_frame=0
        self._clear_fire()

    def _clear_fire(self):
        self.fire_down = self.fire_forwarded = False
        self.fire_pending_until = -1

    def _fire_scan(self, state, aiming, knife, want_aim):
        down = 1 in self.buttons or 8 in self.keys
        pressed = down and not self.fire_down
        self.fire_down = down
        if not down:
            self.fire_forwarded = False
        if knife:
            self.fire_pending_until = -1
            return 0x100 if down else 0
        if self.aim_owned and not want_aim:
            self.fire_pending_until = -1
            self.fire_forwarded = False
            return 0
        if not (want_aim or aiming) or state not in FIRE_BUFFER_STATES:
            self.fire_pending_until = -1
            self.fire_forwarded = False
            return 0x80 if down else 0
        if pressed:
            self.fire_pending_until = self.frames + FIRE_BUFFER_FRAMES
        pending = self.frames <= self.fire_pending_until or (down and not self.fire_forwarded)
        # AtkAimM ignores its first substate and rejects a shot while +0xaa
        # is counting down or +0xad still latches the previous press. Feed a
        # released scan while waiting, then let the original code fire/reload.
        step = struct.unpack('<h', self.arm.read(self.player+0x38, 2))[0]
        cooldown = struct.unpack('<h', self.arm.read(self.player+0xaa, 2))[0]
        ready = aiming and state in (2, 4, 5) and step > 0 and cooldown <= 1 and not self.arm.read(self.player+0xad, 1)[0]
        if pending and ready:
            self.fire_pending_until = -1
            self.fire_forwarded = down
            return 0x80
        return 0x80 if down and self.fire_forwarded else 0

    def begin_frame(self):
        self.item_take_this_frame=self.item_take_requested
        self.item_take_requested=False
        self.flick_this_frame=self.flick_requested
        self.flick_requested=0
        self.item_active=False
        dx,dy=self.motion;self.motion[:]=[0,0]
        if self.active and self.player:
            obj=self.arm.u32(self.player)
            body=self.arm.u32(obj+0x120)
            aiming=bool(self.arm.read(self.player+0x48,1)[0])
            if dx:
                yaw=struct.unpack('<f',self.arm.read(body+0xa4,4))[0]
                # Set_TurnY rebuilds the model matrix with setRotate, which
                # clears its translation. The player samples that matrix for
                # the camera before the object's normal position update.
                # Retain its world position during a desktop mouse turn.
                translation=self.arm.read(body+0x34,12)
                self.arm.call('_ZN10GM_ObjBase9Set_TurnYEf',body,float_out((yaw-dx*MOUSE_DEGREES_PER_PIXEL*TURN/360)%TURN))
                self.arm.write(body+0x34,translation)
            if aiming:
                self.aim_base_pitch=struct.unpack('<f',self.arm.read(self.player+0x14,4))[0]*360/TURN
                native_pitch=struct.unpack('<f',self.arm.read(obj+0x130,4))[0]
                self.look_pitch=self.aim_base_pitch-(native_pitch-AIM_CENTER)/AIM_UNITS_PER_DEGREE
            self.look_pitch=max(-PITCH_LIMIT,min(PITCH_LIMIT,self.look_pitch+dy*MOUSE_DEGREES_PER_PIXEL))
            if aiming and dy:
                native_pitch=max(0,min(TURN,AIM_CENTER+(self.aim_base_pitch-self.look_pitch)*AIM_UNITS_PER_DEGREE))
                self.look_pitch=self.aim_base_pitch-(native_pitch-AIM_CENTER)/AIM_UNITS_PER_DEGREE
                self.arm.write(obj+0x130,struct.pack('<f',native_pitch))
                self.arm.call('_ZN18GM_CtrlMain_Player16_Set_AimActBlendEf',self.player,float_out(native_pitch))
        if self.reload_requested:
            self.reload_requested=False
            if self.active and self.player and self.main:
                state=struct.unpack('<h',self.arm.read(self.player+0x36,2))[0]
                if state in (0,2,4,5) and self.arm.call('_ZN18GM_CtrlMain_Player13_Check_ReloadEP11GM_CtrlMain',self.player,self.main):
                    aiming=bool(self.arm.read(self.player+0x48,1)[0])
                    self.arm.call('_ZN18GM_CtrlMain_Player13_Change_StateEs',self.player,7 if aiming else 8)
        self.active=False
        self.story_active=False
        self.frames+=1

    def _update(self, uc, address, size, context):
        try:
            ctrl=self.arm.u32(uc.reg_read(UC_ARM_REG_SP)+4)
            if not self.enabled or not self.arm.read(ctrl+0x40,1)[0] or not self.arm.u32(ctrl):
                self._clear_fire()
                return
            if not self.main or not self.arm.read(self.main+0x61,1)[0]:
                self._clear_fire()
                return
            event=self.arm.u32(self.main+0x3c)
            self.story_active=bool(event and self.arm.read(event+0x31c,1)[0])
            if self.story_active:
                self._clear_fire()
                return
            self.active=True;self.controller=ctrl
            aiming=bool(self.player and self.arm.read(self.player+0x48,1)[0])
            knife=bool(self.player and self.arm.read(self.player+0x5e,1)[0]==1)
            state=struct.unpack('<h',self.arm.read(self.player+0x36,2))[0] if self.player else 0
            want_aim=3 in self.buttons or 9 in self.keys
            x=(21 in self.keys)-(22 in self.keys)
            y=(19 in self.keys)-(20 in self.keys)
            rate_x=x*100
            rate_y=y*100
            scan=(8 if rate_x<0 else 4 if rate_x>0 else 0)|(1 if rate_y>0 else 2 if rate_y<0 else 0)
            scan |= self._fire_scan(state, aiming, knife, want_aim)
            # 0x100 selects the knife while unarmed, then slashes while it is
            # equipped. Holding F readies it; desktop fire performs the slash.
            if 11 in self.keys and not knife: scan|=0x100
            if 66 in self.keys or 23 in self.keys or 47 in self.keys: scan|=0x20
            trig=scan & ~self.previous_scan
            trig|=self.flick_this_frame
            self.flick_this_frame=0
            if want_aim:
                self.aim_owned=True
                # Repeated gun triggers during startup toggle the weapon
                # instead of holding aim. Retry only after holstering ends.
                if not aiming and state == 0:
                    trig|=0x80
            elif self.aim_owned:
                if knife and 11 in self.keys:self.aim_owned=False
                # A quick RMB release can arrive before Check_isAiming turns
                # true. Cancel the startup states too, retaining ownership
                # until the engine leaves the aiming lifecycle.
                elif aiming or state in (1,19):trig|=0x10
                # A sidestep clears the aiming flag, then restarts aim.
                # Keep ownership so that restart is cancelled as above.
                elif state==MVT_PLAY_STATE and struct.unpack('<h',self.arm.read(self.player+0x64,2))[0]==AIM_START_STATE:pass
                else:self.aim_owned=False
            if 11 in self.keys:self.knife_owned=True
            elif self.knife_owned:
                if knife or state in (16,21):trig|=0x10
                else:self.knife_owned=False
            if 32 in self.keys and not self.previous_scan&0x400:trig|=0x400
            if 32 in self.keys:scan|=0x400
            self.previous_scan=scan
            self.arm.w32(ctrl+0x28,self.arm.u32(ctrl+0x28)|trig)
            self.arm.w32(ctrl+0x2c,self.arm.u32(ctrl+0x2c)|scan)
            if rate_x or rate_y:
                # The engine stores magnitudes here; direction lives in scan bits.
                self.arm.write(ctrl+0x34,struct.pack('<hhh',abs(rate_x),abs(rate_y),min(100,round(math.hypot(rate_x,rate_y)))))
                self.arm.write(ctrl+0x3c,struct.pack('<f',float(math.hypot(rate_x,rate_y))))
            self.last_sample={'scan':scan,'trig':trig,'x':rate_x,'y':rate_y,'aiming':aiming,'want_aim':want_aim}
        except BaseException as error:
            self.arm.pending_error=error;uc.emu_stop()
