"""HD battle units: 2x versions of the PS1 unit sheets (HEX/HEXU.BIN, 7 TIMs 240x240 4bpp,
24x24 cells) made from the PC (Win95) release's unit frames on the user's own PC disc.

usage: python gen/hdunits.py PC_DIR OUTDIR [--preview]
  PC_DIR holds CHR_IDO.E2, CHR_ATT.E2, PALET.E2 (hdpack.py --keep-work)
  -> OUTDIR/texupload-P4-<sheet hash>-<palette hash>-60x240-0-0-240x240-P0-15.png (480x480 RGBA, 7 sheets x 4
  side palettes); --preview adds PS1-vs-PC side-by-side sheets (preview<n>_<palette>.png)
  copy the texupload files to <DuckStation>/textures/SLPM-86205/replacements/

The game uploads the 7 sheets whole (VRAM 384 + 64n, 256) and draws the map units from them with one of 4
side CLUTs (EXE file offset 0x9bf3c, 4 x 16 colours: blue, purple, red = the TIM's CLUT, white; they differ in
entries 4-6 = main colour bright..dark and 7-9 = second colour). The PC red frames are recoloured per CLUT:
PC palette 53-60 (red ramp) -> entries 6..4, 80-87 (blue ramp) -> entries 9..7.

Facts: the first 637 cells are 49 unit types x 13 cells = 6 walk frames (PC CHR_IDO entry,
6 x 48x48: side, side, front, front, back, back), 6 attack frames (PC CHR_ATT entry < 79, 6 or 9 x 64x64;
9-frame types use frames 0,2,3,5,6,8; the PS1 cell is a 24x24 window of the half-size frame, a different
window per frame -> found here by matching), 1 hit frame (CHR_ATT entry 79 + type, 48x48). The PS1 sheets
hold the red side only (PC even types up to 62; odd = blue); the last 19 cells (boats, fire, effects)
have no source here and stay PS1 pixels (2x nearest), as does block 39 (not identified). Block 31 (Nanman
Cavalry) = PC type 62; blocks 47/48 (PS1-only officer sprites) show the PC sprite of their class, see ALIAS.
"""
import json, os, struct, sys
import numpy as np
import xxhash
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ls11, timdump

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PS1 = os.path.join(ROOT, 'work', 'ps1')     # folder with the PS1 disc's files (hdpack.py sets it)
CELL, PER, NTYPES = 24, 13, 49
# PS1 block -> PC unit type (PS1 follows the PC class order; None = PS1-only variant, kept as is)
BLOCK_TYPE = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 36, 38, 40, 42, 42, 44, 46, 48, 50,
              52, 54, 56, 58, 60, 62, 64, 65, 66, 67, 68, 69, 70, None, 72, 73, 74, 75, 76, 77, 78, None, None]
# PS1-only officer sprites (program switch at 0x8004e96c: officer 2 Zhang Fei -> block 47, officer 3 Zhao Yun -> 48).
# The PC disc has no art for them (its 7 officer types 72-78 = blocks 40-46), so they get what the PC has for
# their class: Light Cavalry = block 6 (PC type 12), cell for cell.
ALIAS = {47: 6, 48: 6}
ATT9 = (0, 2, 3, 5, 6, 8)
SIDES = ('blue', 'purple', 'red', 'white')            # order of the EXE table


def side_cluts(tim_clut):
    """the 4 side CLUTs (16 x u16 each) from the EXE: the table whose third row is the TIM's CLUT"""
    d = open(os.path.join(PS1, 'SLPS_006.88'), 'rb').read()
    i = d.find(struct.pack('<16H', *tim_clut))
    assert i >= 0x40, 'side palette table not found'
    return [struct.unpack_from('<16H', d, i - 0x40 + 0x20 * k) for k in range(4)]


def rgb15(v):
    return np.array([(v & 31) << 3, (v >> 5 & 31) << 3, (v >> 10 & 31) << 3], np.float32)


def recolour(pal, red, clut):
    """PC palette (256x3) with the red side's two ramps moved to another PS1 side CLUT"""
    out = pal.astype(np.float32).copy()
    lum = lambda c: float(c @ np.array([0.299, 0.587, 0.114], np.float32))
    for pcs, ents in ((range(53, 61), (6, 5, 4)), (range(80, 88), (9, 8, 7))):
        src = [rgb15(red[e]) for e in ents]; dst = [rgb15(clut[e]) for e in ents]
        xs = [lum(c) for c in src]
        for i in pcs:
            l = lum(out[i])
            if l <= xs[0]:
                c = dst[0] * (l / xs[0])
            elif l >= xs[-1]:
                c = dst[-1] + (255 - dst[-1]) * min(1.0, (l - xs[-1]) / max(1.0, 255 - xs[-1])) * 0.6
            else:
                k = 0 if l < xs[1] else 1
                f = (l - xs[k]) / (xs[k + 1] - xs[k]); c = dst[k] * (1 - f) + dst[k + 1] * f
            out[i] = c
    return np.clip(out, 0, 255).astype(np.uint8)


def lsents(path):
    d = open(path, 'rb').read()
    dic, ents = ls11.entries(d)
    return [np.frombuffer(d[o:o + c] if c == u else ls11.decode(d[o:o + c], u, dic), dtype=np.uint8) for c, u, o in ents]


def ps1_sheets():
    d = open(os.path.join(PS1, 'HEX', 'HEXU.BIN'), 'rb').read()
    o, out = 0, []
    while o + 8 <= len(d):
        t = timdump.parse(d, o)
        if not t:
            break
        px = np.frombuffer(t['pix'], dtype=np.uint8)
        idx = np.stack([px & 15, px >> 4], axis=1).reshape(t['h'], t['w'] * 4)
        out.append((t, idx)); o = t['end']
    return out


def half(rgb, m):
    """48x48 (or 64x64) rgb + mask -> half-size premultiplied mean colour + coverage"""
    s = m.shape[0] // 2
    r = (rgb * m[..., None]).reshape(s, 2, s, 2, 3).sum((1, 3)); c = m.reshape(s, 2, s, 2).sum((1, 3))
    return r / np.maximum(c, 1)[..., None], c / 4


def dist(a, am, b, bm):
    return float((np.abs(a - b).sum(-1) / 3 * np.minimum(am, bm)).sum() + 255 * np.abs(am - bm).sum())


def window(cell, cm, frame, pal):
    """best 48x48 window (x, y) of a 64x64 PC attack frame for a 24x24 PS1 cell"""
    r, m = half(pal[frame].astype(np.float32), (frame != 0).astype(np.float32))
    best = min((dist(cell, cm, r[y:y + 24, x:x + 24], m[y:y + 24, x:x + 24]), x, y) for y in range(9) for x in range(9))
    x0, y0 = best[1] * 2, best[2] * 2
    return x0, y0


def rng(ns):
    out, i = [], 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        out.append('%d' % ns[i] if i == j else '%d-%d' % (ns[i], ns[j])); i = j + 1
    return ', '.join(out)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    pcdir, out = argv[:2]
    os.makedirs(out, exist_ok=True)
    raw = np.frombuffer(open(os.path.join(pcdir, 'PALET.E2'), 'rb').read(), dtype=np.uint8).reshape(256, 3)
    pal = raw[:, (1, 2, 0)]
    ido, att = lsents(os.path.join(pcdir, 'CHR_IDO.E2')), lsents(os.path.join(pcdir, 'CHR_ATT.E2'))
    sheets = ps1_sheets()
    red = sheets[0][0]['pal'][0]
    cluts = dict(zip(SIDES, side_cluts(red)))
    idx = np.stack([s[1] for s in sheets])                                   # 7 x 240 x 240
    fpal = np.array([rgb15(v) for v in red], np.float32)

    # cell -> (PC frame, window x, y)
    cells = {}
    for b, t in enumerate(BLOCK_TYPE):
        if t is None:
            continue
        n = b * PER
        walk, a, hit = ido[t].reshape(6, 48, 48), att[t].reshape(-1, 64, 64), att[79 + t].reshape(48, 48)
        for k in range(6):
            cells[n + k] = (walk[k], 0, 0)
            m = n + 6 + k
            ci = idx[m // 100, m % 100 // 10 * 24:m % 100 // 10 * 24 + 24, m % 10 * 24:m % 10 * 24 + 24]
            cm = (ci != 0).astype(np.float32)
            f = a[ATT9[k] if len(a) == 9 else k]
            cells[m] = (f,) + window(fpal[ci] * cm[..., None], cm, f, pal)
        cells[n + 12] = (hit, 0, 0)
    for b, src in ALIAS.items():
        for k in range(PER):
            cells[b * PER + k] = cells[src * PER + k]

    for side, clut in cluts.items():
        c4 = np.array([timdump.c15(v) for v in clut], np.uint8)
        big = np.repeat(np.repeat(c4[idx], 2, axis=1), 2, axis=2)            # PS1 pixels 2x, this side's colours
        p = pal if side == 'red' else recolour(pal, red, clut)
        for n, (frame, x0, y0) in cells.items():
            s, cy, cx = n // 100, n % 100 // 10, n % 10
            f = frame[y0:y0 + 48, x0:x0 + 48]
            rgba = np.dstack([p[f], np.where(f != 0, 255, 0).astype(np.uint8)])
            rgba[f == 0] = 0
            big[s, cy * 48:cy * 48 + 48, cx * 48:cx * 48 + 48] = rgba
        ph = xxhash.xxh3_64_intdigest(struct.pack('<16H', *clut))
        for s, (t, _) in enumerate(sheets):
            name = 'texupload-P4-%016X-%016X-%dx%d-0-0-%dx%d-P0-15.png' % (
                xxhash.xxh3_64_intdigest(t['pix']), ph, t['w'], t['h'], t['w'] * 4, t['h'])
            Image.fromarray(big[s], 'RGBA').save(os.path.join(out, name))
            if '--preview' in argv:
                a = np.repeat(np.repeat(c4[idx[s]], 2, axis=0), 2, axis=1)
                Image.fromarray(np.hstack([a, big[s]]), 'RGBA').save(os.path.join(out, 'preview%d_%s.png' % (s, side)))
    # what stays PS1 pixels (2x nearest) inside the replaced sheets, for the audit
    used = [m for m in range(len(sheets) * 100)
            if (idx[m // 100, m % 100 // 10 * 24:m % 100 // 10 * 24 + 24, m % 10 * 24:m % 10 * 24 + 24] != 0).any()]
    report = []
    for s in range(len(sheets)):
        ps1 = [m for m in used if m // 100 == s and m not in cells]
        if ps1:
            why = 'cells %s' % rng(ps1)
            blocks = sorted({m // PER for m in ps1 if m < NTYPES * PER})
            if blocks:
                why += ' (unit block %s: no PC sprite identified)' % ', '.join(map(str, blocks))
            if any(m >= NTYPES * PER for m in ps1):
                why += ' (cells from %d: boats, fire, effects)' % (NTYPES * PER)
            report.append(dict(file='HEX/HEXU.BIN', tim=s, why=why))
            print('sheet %d keeps PS1 pixels: %s' % (s, why))
    for b, src in sorted(ALIAS.items()):
        print('block %d shows the PC sprite of block %d (PS1-only officer sprite)' % (b, src))
    json.dump(report, open(os.path.join(out, 'hd_report.json'), 'w'), indent=1)
    print(len(sheets) * len(cluts), 'sheets ->', out)


if __name__ == '__main__':
    main()
