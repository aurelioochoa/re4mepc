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
