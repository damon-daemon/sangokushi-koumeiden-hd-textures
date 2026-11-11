"""PlayStation TIM pictures: header parser and 15-bit colour conversion."""
import struct


def c15(v):
    r, g, b = v & 31, (v >> 5) & 31, (v >> 10) & 31
    return (r << 3, g << 3, b << 3, 0 if v == 0 else 255)


def parse(d, o):
    """TIM at offset o of d -> dict (bpp code, w in VRAM words, h, CLUT rows, pixel bytes, end offset) or None."""
    magic, flag = struct.unpack_from('<II', d, o)
    if magic != 0x10 or (flag & ~0xb) not in (0,) or (flag & 7) > 3:
        return None
    bpp = flag & 3
    p = o + 8
    pal = []
    if flag & 8:
        ln, x, y, w, h = struct.unpack_from('<IHHHH', d, p)
        cl = struct.unpack_from('<%dH' % (w * h), d, p + 12)
        pal = [cl[i:i + w] for i in range(0, w * h, w)]
        p += ln
    ln, x, y, w, h = struct.unpack_from('<IHHHH', d, p)
    pix = d[p + 12:p + ln]
    return dict(off=o, end=p + ln, bpp=bpp, w=w, h=h, x=x, y=y, pal=pal, pix=pix)
