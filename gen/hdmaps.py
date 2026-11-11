"""HD battle maps: 6x versions of the PS1 battle map pictures (HEX/HEXMAP.BIN, 52 TIMs 8bpp, 8 px per cell)
made from the PC (Win95) release's maps (48 px per cell) on the user's own PC disc.

usage: python gen/hdmaps.py PC_DIR OUTDIR [--preview]
  PC_DIR holds m01.e2 ... m50.e2 and PALET.E2 (hdpack.py --keep-work)
  -> OUTDIR/texupload-P8-<TIM hash>-<palette hash>-<w>x<h>-<x>-0-<rw>x<h>-P<lo>-<hi>.png (6x RGBA)
  --preview adds preview<n>.png (PS1 picture 6x nearest | PC picture)
  copy the texupload files to <DuckStation>/textures/SLPM-86205/replacements/

Facts: the game uploads the map whole at VRAM (864, 256); DuckStation splits the write at the
texture-page columns (64 VRAM words = 128 px at 8bpp; 864 is half a page in), so the picture arrives as
rects starting at px 0, 64, 192. Each rect is named with the hash of the whole TIM pixel data, the range
lo-hi of the CLUT indices used inside that rect, and the hash of the FIRST hi-lo+1 CLUT entries (entries
0..hi-lo, not lo..hi: checked against six fresh-boot dumps with lo > 0). Seen for map 0 only (104 px wide: rects 0-63 and
64-103), so for wider maps both readings are written: "the rest in one piece" and "split again at px 192"
(the unused names are harmless).
PC map = raw 8bpp, 16x16 tiles row-major, palette PALET.E2 (R,G,B = bytes 1,2,0), index 0 = black.
PS1 TIM n = PC m(n+1); TIM 50 = m23, TIM 51 = m40; TIM 43 and 44 have no PC file (left alone).
"""
import json, os, struct, sys
import numpy as np
import xxhash
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timdump

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PS1 = os.path.join(ROOT, 'work', 'ps1')     # folder with the PS1 disc's files (hdpack.py sets it)
SCALE, TILE, SPLITS = 6, 16, (64, 192)
PC_OF = {**{n: n + 1 for n in range(50) if n not in (43, 44)}, 50: 23, 51: 40}


def ps1_maps():
    d = open(os.path.join(PS1, 'HEX', 'HEXMAP.BIN'), 'rb').read()
    o, out = 0, []
    while o + 8 <= len(d):
        t = timdump.parse(d, o)
        if not t:
            break
        out.append(t); o = t['end']
    return out


def pc_file(pcdir, n):
    names = {f.lower(): f for f in os.listdir(pcdir)}
    f = names.get('m%02d.e2' % n)
    return os.path.join(pcdir, f) if f else None


def pc_map(path, w, h):
    """raw tile file -> (h*6, w*6) index picture"""
    W, H = w * SCALE, h * SCALE
    d = np.frombuffer(open(path, 'rb').read(), dtype=np.uint8)
    assert len(d) == W * H and W % TILE == 0 and H % TILE == 0, (path, len(d), W, H)
    return d.reshape(H // TILE, W // TILE, TILE, TILE).transpose(0, 2, 1, 3).reshape(H, W)


def rects(w):
    """(x0, x1) pieces of a map of width w, for both split readings"""
    out = {(0, min(w, SPLITS[0]))}
    if w > SPLITS[0]:
        out.add((SPLITS[0], w))
        if w > SPLITS[1]:
            out.update({(SPLITS[0], SPLITS[1]), (SPLITS[1], w)})
    return sorted(out)


def name(t, idx, x0, x1):
    part = idx[:, x0:x1]
    lo, hi = int(part.min()), int(part.max())
    pal = t['pal'][0]
    return 'texupload-P8-%016X-%016X-%dx%d-%d-0-%dx%d-P%d-%d.png' % (
        xxhash.xxh3_64_intdigest(t['pix']), xxhash.xxh3_64_intdigest(struct.pack('<%dH' % (hi - lo + 1), *pal[:hi - lo + 1])),
        t['w'], t['h'], x0, x1 - x0, t['h'], lo, hi)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    pcdir, out = argv[:2]
    os.makedirs(out, exist_ok=True)
    raw = np.frombuffer(open(os.path.join(pcdir, 'PALET.E2'), 'rb').read(), dtype=np.uint8).reshape(256, 3)
    pal = np.dstack([raw[:, (1, 2, 0)][None], np.full((1, 256, 1), 255, np.uint8)])[0]
    pal[0, :3] = 0
    n_png = n_map = 0
    report = []                      # maps left as PS1 pixels, for the audit
    for n, t in enumerate(ps1_maps()):
        src = pc_file(pcdir, PC_OF[n]) if n in PC_OF else None
        if not src:
            print('map %d: no PC file, left alone' % n)
            report.append(dict(file='HEX/HEXMAP.BIN', tim=n, why='no PC map file')); continue
        w, h = t['w'] * 2, t['h']
        idx = np.frombuffer(t['pix'], dtype=np.uint8)[:w * h].reshape(h, w)
        big = pal[pc_map(src, w, h)]
        for x0, x1 in rects(w):
            Image.fromarray(big[:, x0 * SCALE:x1 * SCALE], 'RGBA').save(os.path.join(out, name(t, idx, x0, x1)))
            n_png += 1
        n_map += 1
        if '--preview' in argv:
            ps = np.array([timdump.c15(v)[:3] + (255,) for v in t['pal'][0]], np.uint8)[idx]
            ps = np.repeat(np.repeat(ps, SCALE, axis=0), SCALE, axis=1)
            Image.fromarray(np.hstack([ps, big]), 'RGBA').save(os.path.join(out, 'preview%02d.png' % n))
    json.dump(report, open(os.path.join(out, 'hd_report.json'), 'w'), indent=1)
    print(n_map, 'maps,', n_png, 'PNGs ->', out)


if __name__ == '__main__':
    main()
