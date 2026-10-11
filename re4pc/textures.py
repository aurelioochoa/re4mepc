"""Decode OES paletted textures that desktop OpenGL does not accept."""
import struct


def palette_texture(internal_format, width, height, level, data):
    if not 0x8b90 <= internal_format <= 0x8b99:
        raise ValueError('Unsupported paletted texture format')
    if width < 1 or height < 1 or level > 0:
        raise ValueError('Invalid OES paletted texture dimensions or level')
    variant = (internal_format - 0x8b90) % 5
    bits = 4 if internal_format < 0x8b95 else 8
    entries = 1 << bits
    entry_size = (3,4,2,2,2)[variant]
    palette_size = entries*entry_size
    if len(data) < palette_size: raise ValueError('Truncated OES palette')
    palette = []
    def expand(value,bits): return (value*255)//((1<<bits)-1)
    for i in range(entries):
        p = i*entry_size
        if variant == 0: color = data[p:p+3]+b'\xff'
        elif variant == 1: color = data[p:p+4]
        else:
            value = int.from_bytes(data[p:p+2],'little')
            if variant == 2:
                color = bytes((expand(value>>11,5),expand((value>>5)&63,6),expand(value&31,5),255))
            elif variant == 3:
                color = bytes(((value>>12)*17,((value>>8)&15)*17,((value>>4)&15)*17,(value&15)*17))
            else:
                color = bytes((expand(value>>11,5),expand((value>>6)&31,5),expand((value>>1)&31,5),(value&1)*255))
        palette.append(color)
    offset = palette_size
    images = []
    for mip in range(1-level):
        w,h = max(1,width>>mip),max(1,height>>mip)
        count = w*h
        length = (count*bits+7)//8
        if offset+length > len(data): raise ValueError('Truncated OES texture indices')
        indices = data[offset:offset+length]
        if bits == 8:
            pixels = b''.join(palette[index] for index in indices)
        else:
            pixels = b''.join(palette[(indices[i//2] >> (4 if i%2==0 else 0))&15] for i in range(count))
        images.append((mip,w,h,pixels))
        offset += length
    return images
