import struct
import unittest
from re4pc.pc_controls import PCControls
from re4pc.bionic import float_out
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP


class Memory:
    def __init__(self):
        self.data = bytearray(8192)
        self.calls = []
    def alloc(self, size): return 7000
    def read(self, address, size): return bytes(self.data[address:address+size])
    def write(self, address, value): self.data[address:address+len(value)] = value
    def u32(self, address): return struct.unpack('<I', self.read(address, 4))[0]
    def w32(self, address, value): self.write(address, struct.pack('<I', value))
    def call(self, *args): self.calls.append(args)


class Registers:
    def __init__(self): self.values = {UC_ARM_REG_R0:4300, UC_ARM_REG_R1:4000, UC_ARM_REG_R2:4200, UC_ARM_REG_R3:4100}
    def reg_read(self, reg): return self.values[reg]
    def reg_write(self, reg, value): self.values[reg] = value


class ItemPickupTests(unittest.TestCase):
    def setUp(self):
        self.arm = Memory()
        self.pc = PCControls(self.arm)
        self.uc = Registers()
        self.uc.reg_write(UC_ARM_REG_SP, 6000)
        self.arm.w32(6004, 100)
        self.arm.w32(100+4, 1000)
        self.arm.write(100+0x20, b'\x01')
        self.arm.w32(100+0x14, 2000)
        self.arm.write(2000+0x50, b'\x01\x01')

    def frame(self):
        self.pc.begin_frame()
        self.arm.w32(100+0x24, 0)
        self.pc._item_window(self.uc, 0, 0, None)
        return self.arm.u32(100+0x24)

    def test_first_press_selects_and_second_press_takes_once(self):
        self.pc.key(True, 23)
        self.assertEqual(self.frame(), 0)
        self.assertTrue(self.pc.item_active)
        # Opening the window while Space is held must not confirm it.
        self.pc.key(True, 23)
        self.assertEqual(self.frame(), 0)
        self.pc.key(False, 23)
        self.pc.key(True, 23)
        self.assertEqual(self.frame(), 4)
        self.assertEqual(self.frame(), 0)

    def test_disabled_or_hidden_take_button_does_not_confirm(self):
        self.frame()
        for flags in (b'\0\x01', b'\x01\0', b'\0\0'):
            self.arm.write(2000+0x50, flags)
            self.pc.key(True, 23)
            self.assertEqual(self.frame(), 0)
            self.pc.key(False, 23)

    def test_focus_release_cancels_pending_take(self):
        self.frame()
        self.pc.key(True, 23)
        self.pc.release()
        self.assertEqual(self.frame(), 0)

    def test_closed_window_does_not_leave_a_take_request_for_next_item(self):
        self.frame()
        self.pc.key(True, 23)
        self.arm.write(100+0x20, b'\0')
        self.assertEqual(self.frame(), 0)
        self.assertFalse(self.pc.item_active)
        self.arm.write(100+0x20, b'\x01')
        self.assertEqual(self.frame(), 0)

    def test_touch_mode_does_not_change_item_input(self):
        self.pc.enabled = False
        self.pc.item_take_this_frame = True
        self.arm.w32(100+0x24, 8)
        self.pc._item_window(self.uc, 0, 0, None)
        self.assertEqual(self.arm.u32(100+0x24), 8)
        self.assertFalse(self.pc.item_active)


class TouchHUDTests(unittest.TestCase):
    def setUp(self):
        self.arm = Memory()
        self.pc = PCControls(self.arm)
        self.uc = Registers()
        self.uc.reg_write(UC_ARM_REG_R0, 100)
        self.arm.w32(100, 1000)
        self.arm.write(100+0x40, b'\x01')
        # Pad, lower weapon, event, companion, gun, knife, scope, menu.
        self.components = {}
        for index, offset in enumerate(range(4, 0x24, 4)):
            component = 2000+index*100
            self.components[offset] = component
            self.arm.w32(100+offset, component)
            self.arm.write(component+0x50, b'\x01\x01')

    def test_draw_hides_movement_and_combat_but_preserves_interactions(self):
        before = bytes(self.arm.data)
        self.pc._hud_begin(self.uc, 0, 0, None)
        for offset, component in self.components.items():
            self.assertEqual(self.arm.read(component+0x51, 1),
                             b'\0' if offset in (4, 8, 0x14, 0x18) else b'\x01')
            self.assertEqual(self.arm.read(component+0x50, 1), b'\x01')
        self.pc._hud_end(self.uc, 0, 0, None)
        self.assertEqual(bytes(self.arm.data), before)
        self.assertEqual(self.pc.hud_visibility, [])

    def test_native_hidden_flags_and_missing_components_are_preserved(self):
        self.arm.write(self.components[0x14]+0x51, b'\0')
        self.arm.w32(100+0x18, 0)
        before = bytes(self.arm.data)
        for _ in range(3):
            self.pc._hud_begin(self.uc, 0, 0, None)
            self.pc._hud_end(self.uc, 0, 0, None)
            self.assertEqual(bytes(self.arm.data), before)

    def test_touch_mode_and_uninitialized_layout_are_unchanged(self):
        for condition in ('touch', 'disabled', 'no_layout'):
            if condition == 'touch': self.pc.enabled = False
            elif condition == 'disabled':
                self.pc.enabled = True
                self.arm.write(100+0x40, b'\0')
            else:
                self.arm.write(100+0x40, b'\x01')
                self.arm.w32(100, 0)
            before = bytes(self.arm.data)
            self.pc._hud_begin(self.uc, 0, 0, None)
            self.pc._hud_end(self.uc, 0, 0, None)
            self.assertEqual(bytes(self.arm.data), before)


class PointerTargetTests(unittest.TestCase):
    def setUp(self):
        self.arm = Memory()
        self.arm.symbols = {'_ZN14LYT_Cmp_Button9doMsgProcEmPv': 501,
                            '_ZN18LYT_Cmp_PushButton9doMsgProcEmPv': 601}
        self.pc = PCControls(self.arm)
        self.pc.active, self.pc.controller = True, 100
        self.arm.w32(100, 1000)
        self.arm.write(100+0x40, b'\x01')
        self.arm.w32(100+0x20, 2000)
        self.arm.w32(2000, 1000)
        self.arm.w32(1000+0x2c, 501)
        self.arm.write(2000+0x50, b'\x01\x01')
        self.arm.write(2000+0xb8, struct.pack('<4i', 10, 20, 80, 50))

    def test_menu_and_context_buttons_use_native_touch_bounds(self):
        for offset in (0x0c, 0x10, 0x1c, 0x20):
            self.arm.w32(100+0x20, 0)
            self.arm.w32(100+offset, 2000)
            self.assertTrue(self.pc.pointer_target(40, 30))
            self.assertTrue(self.pc.pointer_target(90, 70))
            self.assertFalse(self.pc.pointer_target(91, 70))
            self.assertFalse(self.pc.pointer_target(40, 19))
            self.arm.w32(100+offset, 0)

    def test_push_button_uses_its_normal_image_screen_bounds(self):
        self.arm.w32(1000+0x2c, 601)
        self.arm.w32(2000+0x94, 3000)
        self.arm.write(3000+0x3c, struct.pack('<4i', 700, 350, 90, 100))
        self.assertTrue(self.pc.pointer_target(742, 416))
        self.assertFalse(self.pc.pointer_target(40, 30))
        self.arm.w32(2000+0x94, 0)
        self.assertFalse(self.pc.pointer_target(742, 416))

    def test_hidden_disabled_and_combat_buttons_do_not_receive_clicks(self):
        for flags in (b'\0\x01', b'\x01\0', b'\0\0'):
            self.arm.write(2000+0x50, flags)
            self.assertFalse(self.pc.pointer_target(40, 30))
        self.arm.write(2000+0x50, b'\x01\x01')
        self.arm.w32(100+0x20, 0)
        for offset in (4, 8, 0x14, 0x18):
            self.arm.w32(100+offset, 2000)
        self.assertFalse(self.pc.pointer_target(40, 30))

    def test_inactive_gameplay_and_closed_layout_have_no_targets(self):
        for condition in ('inactive', 'touch', 'closed', 'missing'):
            self.pc.active = condition != 'inactive'
            self.pc.enabled = condition != 'touch'
            self.arm.write(100+0x40, bytes([condition != 'closed']))
            self.arm.w32(100, 0 if condition == 'missing' else 1000)
            self.assertFalse(self.pc.pointer_target(40, 30))


class MouseControlTests(unittest.TestCase):
    def setUp(self):
        self.arm = Memory()
        self.pc = PCControls(self.arm)
        self.pc.player, self.pc.main = 100, 1000
        self.arm.w32(100, 2000)
        self.arm.w32(2000+0x120, 3000)
        self.arm.write(1000+0x61, b'\x01')

    def test_entering_aim_keeps_engine_pitch(self):
        self.pc.active = True
        self.pc.look_pitch = 40
        self.arm.write(100+0x48, b'\x01')
        self.arm.write(2000+0x130, struct.pack('<f', 32768))
        self.pc.begin_frame()
        self.assertEqual(struct.unpack('<f', self.arm.read(2000+0x130, 4))[0], 32768)
        self.assertEqual(self.pc.look_pitch, 0)
        self.assertEqual(self.arm.calls, [])

    def test_camera_pitch_is_absolute_and_preserves_orbit_anchor(self):
        self.pc.look_pitch = 20
        self.arm.write(4300+0x10, struct.pack('<fffffff', 1400,16384,0,10,20,30,40))
        orbit=self.arm.read(4300+0x14,24)
        uc = Registers()
        for _ in range(60):self.pc._camera_pose(uc, 0, 0, None)
        native_pitch=struct.unpack('<f',self.arm.read(4300+0x10,4))[0]
        self.assertAlmostEqual(native_pitch*360/65536,20,places=4)
        self.assertEqual(self.arm.read(4300+0x14,24),orbit)

    def test_mouse_yaw_uses_corrected_direction(self):
        self.pc.active = True
        self.arm.write(3000+0xa4, struct.pack('<f', 16384))
        self.pc.move(20, 0)
        self.pc.begin_frame()
        value = struct.unpack('<f', struct.pack('<I', self.arm.calls[0][2]))[0]
        self.assertAlmostEqual(value*360/65536, 87, places=4)

    def test_yaw_wrap_does_not_jump_to_a_different_heading(self):
        self.pc.active = True
        self.arm.write(3000+0xa4, struct.pack('<f', 65500))
        self.pc.move(-20, 0)
        self.pc.begin_frame()
        value = struct.unpack('<f', struct.pack('<I', self.arm.calls[0][2]))[0]
        self.assertAlmostEqual((value-65500)%65536*360/65536, 3, places=4)

    def test_continuous_mouse_turn_preserves_model_world_position(self):
        translation=struct.pack('<fff',71300,1090,128974)
        self.arm.write(3000+0x34,translation)
        native_call=self.arm.call
        def set_turn(*args):
            native_call(*args)
            if args[0]=='_ZN10GM_ObjBase9Set_TurnYEf':
                # Native setRotate builds a rotation matrix at the origin.
                self.arm.write(3000+0x34,bytes(12))
                self.arm.write(3000+0xa4,struct.pack('<I',args[2]))
        self.arm.call=set_turn
        for aiming in (False,True):
            self.arm.write(100+0x48,bytes([aiming]))
            self.arm.write(2000+0x130,struct.pack('<f',32768))
            for dx in [80]*30+[-80]*30:
                self.pc.active=True
                self.pc.move(dx,0)
                self.pc.begin_frame()
                self.assertEqual(self.arm.read(3000+0x34,12),translation)

    def test_aim_motion_preserves_neutral_blend_and_uses_camera_units(self):
        self.pc.active = True
        self.arm.write(100+0x48, b'\x01')
        self.arm.write(2000+0x130, struct.pack('<f', 32768))
        self.pc.move(0, -20)
        self.pc.begin_frame()
        native = struct.unpack('<f', self.arm.read(2000+0x130, 4))[0]
        self.assertAlmostEqual((native-32768)/3*360/65536, 3, places=4)
        self.assertAlmostEqual(self.pc.look_pitch, -3)
        self.assertAlmostEqual(native/65536, 0.525, places=4)
        self.assertEqual(self.arm.calls[0][2], float_out(native))

    def test_large_aim_motion_is_bounded_and_can_reverse(self):
        self.arm.write(100+0x48, b'\x01')
        self.arm.write(2000+0x130, struct.pack('<f', 32768))
        for dy, expected in ((-10000,-45),(20,-42),(10000,45),(-20,42)):
            self.pc.active = True
            self.pc.move(0, dy)
            self.pc.begin_frame()
            self.assertAlmostEqual(self.pc.look_pitch, expected, places=4)
            blend=struct.unpack('<f', self.arm.read(2000+0x130, 4))[0]/65536
            self.assertGreaterEqual(blend, 0.125)
            self.assertLessEqual(blend, 0.875)

    def test_aim_entry_carries_look_angle_without_overriding_touch_mode(self):
        self.pc.active = True
        self.pc.button(True, 3)
        self.pc.look_pitch = -20
        uc = Registers()
        self.pc._aim_start(uc, 0, 0, None)
        native=struct.unpack('<f',struct.pack('<I',uc.reg_read(UC_ARM_REG_R2)))[0]
        self.assertAlmostEqual((native-32768)/3*360/65536, 20, places=4)
        self.pc.enabled=False
        uc.reg_write(UC_ARM_REG_R2, 1234)
        self.pc._aim_start(uc, 0, 0, None)
        self.assertEqual(uc.reg_read(UC_ARM_REG_R2), 1234)

    def test_aim_entry_accounts_for_native_camera_baseline(self):
        self.pc.active=True
        self.pc.button(True,3)
        self.arm.write(100+8,struct.pack('<f',-102400))
        self.arm.write(100+0x14,struct.pack('<f',1400))
        self.pc.look_pitch=-15
        uc=Registers()
        self.pc._aim_start(uc,0,0,None)
        native=struct.unpack('<f',struct.pack('<I',uc.reg_read(UC_ARM_REG_R2)))[0]
        camera_pitch=-1400*360/65536+(native-32768)/3*360/65536
        self.assertAlmostEqual(camera_pitch,15,places=4)
        self.arm.write(100+0x48,b'\x01')
        self.arm.write(2000+0x130,struct.pack('<f',native))
        self.pc.begin_frame()
        self.assertAlmostEqual(self.pc.look_pitch,-15,places=4)

    def test_camera_orbit_points_up_and_leaves_native_aim_alone(self):
        self.pc.active = True
        self.pc.move(0,-20)
        self.pc.begin_frame()
        uc=Registers()
        self.pc._camera_pose(uc,0,0,None)
        native=struct.unpack('<f',self.arm.read(4300+0x10,4))[0]
        self.assertAlmostEqual(native*360/65536,-3,places=4)
        self.arm.write(100+0x48,b'\x01')
        self.arm.write(4300+0x10,struct.pack('<f',1400))
        self.pc._camera_pose(uc,0,0,None)
        self.assertEqual(struct.unpack('<f',self.arm.read(4300+0x10,4))[0],1400)

    def test_inactive_and_released_inputs_do_not_rotate_player(self):
        self.pc.move(100,100)
        self.pc.begin_frame()
        self.assertEqual(self.pc.look_pitch,0)
        self.assertEqual(self.arm.calls,[])
        self.pc.active=True
        self.pc.button(True,3)
        self.pc.move(100,100)
        self.pc.release()
        self.pc.begin_frame()
        self.assertEqual(self.arm.calls,[])
        self.assertEqual(self.pc.buttons,set())

    def test_rendered_view_uses_native_collision_vectors_at_every_pitch(self):
        self.arm.write(4000, struct.pack('<fff', 0, 2, 0))
        self.arm.write(4100, struct.pack('<fff', 0, 1, 10))
        for pitch in (-45,-20,0,20,45):
            self.pc.look_pitch=pitch
            uc=Registers()
            before=dict(uc.values)
            self.pc._camera(uc,0,0,None)
            self.assertEqual(uc.values,before)
            self.assertEqual(self.pc.last_view['eye'],(0,2,0))
            self.assertEqual(self.pc.last_view['target'],(0,1,10))
            self.assertEqual(self.pc.last_view['adjusted_target'],(0,1,10))

    def test_story_camera_and_touch_controls_retain_native_target(self):
        self.arm.write(4000, struct.pack('<fff', 0, 2, 0))
        self.arm.write(4100, struct.pack('<fff', 0, 1, 10))
        self.pc.look_pitch=20
        self.arm.w32(1000+0x3c,5000)
        self.arm.write(5000+0x31c,b'\x01')
        uc=Registers()
        self.arm.write(4300+0x10,struct.pack('<f',1400))
        self.pc._camera_pose(uc,0,0,None)
        self.assertEqual(struct.unpack('<f',self.arm.read(4300+0x10,4))[0],1400)
        self.pc._camera(uc,0,0,None)
        self.assertEqual(uc.reg_read(UC_ARM_REG_R3),4100)

        self.pc.enabled=False
        self.arm.write(5000+0x31c,b'\x00')
        self.pc._camera_pose(uc,0,0,None)
        self.assertEqual(struct.unpack('<f',self.arm.read(4300+0x10,4))[0],1400)
        self.pc._camera(uc,0,0,None)
        self.assertEqual(uc.reg_read(UC_ARM_REG_R3),4100)

    def test_hold_knife_does_not_auto_slash_and_click_uses_knife_channel(self):
        uc=Registers();uc.values[UC_ARM_REG_SP]=6000
        self.arm.w32(6004,5000)
        self.arm.w32(5000,1000)
        self.arm.write(5000+0x40,b'\x01')
        self.arm.write(100+0x48,b'\x01')
        self.arm.write(100+0x5e,b'\x01')
        self.arm.write(100+0x36,struct.pack('<h',2))
        self.pc.key(True,11)
        self.pc._update(uc,0,0,None)
        self.assertEqual(self.pc.last_sample['scan'],0)
        self.pc.button(True,1)
        self.pc._update(uc,0,0,None)
        self.assertEqual(self.pc.last_sample['scan'],0x100)
        self.assertEqual(self.pc.last_sample['trig'],0x100)
        self.pc.button(False,1)
        self.pc.key(False,11)
        self.pc._update(uc,0,0,None)
        self.assertEqual(self.pc.last_sample['trig'],0x10)

    def test_quick_aim_release_cancels_before_aiming_flag_is_set(self):
        uc=Registers();uc.values[UC_ARM_REG_SP]=6000
        self.arm.w32(6004,5000)
        self.arm.w32(5000,1000)
        self.arm.write(5000+0x40,b'\x01')
        self.arm.write(100+0x36,struct.pack('<h',1))
        self.pc.aim_owned=True
        self.pc._update(uc,0,0,None)
        self.assertTrue(self.pc.aim_owned)
        self.assertEqual(self.pc.last_sample['trig'],0x10)


class ConfigurableCameraTests(unittest.TestCase):
    def test_controller_scale_bypasses_mouse_sensitivity_but_retains_inversion(self):
        pc=PCControls(Memory(),settings={'sensitivity':2,'invert_y':True})
        pc.move(4,5,sensitivity=1.0)
        self.assertEqual(pc.motion,[4,-5])

    def test_sensitivity_and_inversion_apply_once_to_mouse_delta(self):
        arm=Memory()
        pc=PCControls(arm,settings={'sensitivity':2,'invert_y':True})
        pc.move(4,5)
        self.assertEqual(pc.motion,[8,-10])
        pc.move(-1,-2)
        self.assertEqual(pc.motion,[6,-6])
        pc.release()
        self.assertEqual(pc.motion,[0,0])


class CombatInputTests(unittest.TestCase):
    def setUp(self):
        self.arm = Memory()
        self.pc = PCControls(self.arm)
        self.pc.player, self.pc.main = 100, 1000
        self.arm.w32(100, 2000)
        self.arm.w32(2000+0x120, 3000)
        self.arm.write(2000+0x130, struct.pack('<f', 32768))
        self.arm.write(1000+0x61, b'\x01')
        self.arm.w32(5000, 1000)
        self.arm.write(5000+0x40, b'\x01')
        self.uc = Registers()
        self.uc.reg_write(UC_ARM_REG_SP, 6000)
        self.arm.w32(6004, 5000)
        self.pc.button(True, 3)

    def frame(self, state=2, step=1, cooldown=0, latch=0):
        self.arm.write(100+0x36, struct.pack('<hh', state, step))
        self.arm.write(100+0x48, bytes([state in (2,4,5,6,7)]))
        self.arm.write(100+0xaa, struct.pack('<h', cooldown))
        self.arm.write(100+0xad, bytes([latch]))
        self.pc.begin_frame()
        self.arm.w32(5000+0x28, 0)
        self.arm.w32(5000+0x2c, 0)
        self.pc._update(self.uc, 0, 0, None)
        return self.arm.u32(5000+0x2c), self.arm.u32(5000+0x28)

    def test_quick_click_survives_aim_start_and_fires_once(self):
        self.frame(0)
        self.pc.button(True, 1)
        self.assertEqual(self.frame(1)[0], 0)
        self.pc.button(False, 1)
        self.assertEqual(self.frame(2, step=0)[0], 0)
        self.assertEqual(self.frame()[0], 0x80)
        self.assertEqual(self.frame(6)[0], 0)
        self.assertEqual(self.frame()[0], 0)

    def test_click_during_recoil_waits_for_cooldown_and_release_latch(self):
        self.pc.key(True, 8)
        self.assertEqual(self.frame(6, cooldown=4)[0], 0)
        self.pc.key(False, 8)
        self.assertEqual(self.frame(cooldown=3)[0], 0)
        self.assertEqual(self.frame(latch=1)[0], 0)
        self.assertEqual(self.frame(cooldown=1)[0], 0x80)
        self.assertEqual(self.frame()[0], 0)

    def test_held_fire_retains_native_repeat_after_first_accepted_press(self):
        self.pc.button(True, 1)
        self.assertEqual(self.frame()[0], 0x80)
        self.assertEqual(self.frame(6)[0], 0x80)
        self.pc.button(False, 1)
        self.assertEqual(self.frame(6)[0], 0)

    def test_releasing_aim_or_focus_discards_buffered_click(self):
        for cancel in ('aim', 'focus'):
            self.setUp()
            self.pc.button(True, 1)
            self.frame(1)
            self.pc.button(False, 1)
            if cancel == 'aim': self.pc.button(False, 3)
            else: self.pc.release()
            self.assertEqual(self.frame()[0], 0)
            self.pc.button(True, 3)
            self.assertEqual(self.frame()[0], 0)

    def test_damage_story_and_menu_cannot_replay_a_buffered_shot(self):
        for interruption in ('damage', 'story', 'menu'):
            self.setUp()
            self.pc.button(True, 1)
            self.frame(1)
            self.pc.button(False, 1)
            if interruption == 'damage': self.frame(9)
            elif interruption == 'story':
                self.arm.w32(1000+0x3c, 4000)
                self.arm.write(4000+0x31c, b'\x01')
                self.frame()
                self.arm.write(4000+0x31c, b'\0')
            else:
                self.arm.write(1000+0x61, b'\0')
                self.frame()
                self.arm.write(1000+0x61, b'\x01')
            self.assertEqual(self.frame()[0], 0)

    def test_buffer_expires_instead_of_firing_after_a_long_animation(self):
        self.pc.button(True, 1)
        self.frame(1)
        self.pc.button(False, 1)
        for _ in range(21): self.frame(1)
        self.assertEqual(self.frame()[0], 0)

    def test_holding_fire_through_a_long_startup_still_fires(self):
        self.pc.button(True, 1)
        for _ in range(30): self.frame(1)
        self.assertEqual(self.frame()[0], 0x80)

    def test_long_aim_start_does_not_receive_a_second_toggle(self):
        self.assertEqual(self.frame(0)[1] & 0x80, 0x80)
        for _ in range(35):
            self.assertEqual(self.frame(1)[1] & 0x80, 0)
        self.assertEqual(self.frame(3)[1] & 0x80, 0)
        self.assertEqual(self.frame(0)[1] & 0x80, 0x80)

    def test_pc_laser_overrides_only_the_visibility_query(self):
        self.uc.reg_write(UC_ARM_REG_R0, 1)
        before = bytes(self.arm.data)
        self.pc._desktop_laser(self.uc, 0, 0, None)
        self.assertEqual(self.uc.reg_read(UC_ARM_REG_R0), 0)
        self.assertEqual(bytes(self.arm.data), before)
        self.pc.enabled = False
        self.uc.reg_write(UC_ARM_REG_R0, 1)
        self.pc._desktop_laser(self.uc, 0, 0, None)
        self.assertEqual(self.uc.reg_read(UC_ARM_REG_R0), 1)
