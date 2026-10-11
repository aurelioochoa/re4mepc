import unittest
from re4pc.textures import palette_texture

class TextureTests(unittest.TestCase):
    def test_eight_bit_rgba_indices_and_alpha(self):
        palette=bytes(range(256))*4
        image=palette_texture(0x8b96,3,1,0,palette+bytes([0,10,255]))[0]
        self.assertEqual(image[:3],(0,3,1))
        self.assertEqual(image[3],palette[:4]+palette[40:44]+palette[1020:1024])

    def test_four_bit_nibble_order_and_odd_texel_count(self):
        palette=b''.join(bytes([i*10,0,0]) for i in range(16))
        rgba=palette_texture(0x8b90,3,1,0,palette+b'\x12\x30')[0][3]
        self.assertEqual(rgba,bytes([10,0,0,255,20,0,0,255,30,0,0,255]))

    def test_mipmaps_share_one_palette(self):
        palette=b''.join(bytes([i,0,0,255]) for i in range(256))
        levels=palette_texture(0x8b96,2,2,-1,palette+bytes([1,2,3,4,5]))
        self.assertEqual([image[:3] for image in levels],[(0,2,2),(1,1,1)])
        self.assertEqual(levels[1][3],bytes([5,0,0,255]))

    def test_rgb565_expands_channels(self):
        palette=bytes.fromhex('00f8e0071f00ffff')+b'\0\0'*12
        rgba=palette_texture(0x8b92,4,1,0,palette+bytes([0x01,0x23]))[0][3]
        self.assertEqual(rgba,bytes([255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255]))

    def test_truncated_texture_is_an_error(self):
        with self.assertRaisesRegex(ValueError,'Truncated'): palette_texture(0x8b96,2,2,0,b'\0'*1024+b'\0')
