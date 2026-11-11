"""HD backdrops: 2x versions of the PS1 hall pictures (PM.BIN) and town overviews (SMAP.E2), 320x240 or
320x200 8bpp TIMs, made from the PC (Win95) release's 640x400 pictures on the user's own PC disc.

usage: python gen/hdbacks.py PC_DIR OUTDIR [--preview] [--pc-colours]
  PC_DIR holds PMAPCHIP.E2, MMAP.E2, PALET.E2 (hdpack.py --keep-work)
  -> OUTDIR/texupload-P8-<TIM hash>-<palette hash>-160x<h>-0-0-320x<h>-P<lo>-<hi>.png (640 x 2h RGBA)
  --preview adds preview_<file>_<n>.png (PS1 picture 2x nearest | replacement)
  Town overviews: PC palette entries that are plainly another colour in the PS1 picture are taken from it.
  Halls: the PC pixels take the PS1 picture's colours (per PC palette index, the
  mean PS1 colour under it), so the PC part joins the PS1 rows above and below it without a visible step.
  --pc-colours keeps the PC palette instead (brighter, step at rows 20/220)
  copy the texupload files to <DuckStation>/textures/SLPM-86205/replacements/

Facts:
- The game uploads these pictures whole (dumps: 160x240-0-0-320x240), so one PNG per TIM, named by the
  rule palette hash = first hi-lo+1 CLUT entries).
- PC PMAPCHIP.E2 (LS11, 40 entries x 256,000 B) = 640x400 pictures stored as 8x8 tiles, row-major, 80 per row
  (PMAP.E2 is the walk grid, not a tile map). Entry n = PM.BIN TIM n, except 23 <-> 25; TIM 40 has no PC picture.
- PC MMAP.E2 (LS11, 28 x 256,000 B) = raw 640x400. Entries 0, 1 = world maps (not the PS1 picture); entry n + 1 =
  SMAP.E2 TIM n for n = 1..26. SMAP TIMs 0 (world map), 27, 28 have no PC picture.
- A 320x240 PS1 picture = the PC picture at half size, 20 rows down: the PS1 has 20 more rows above and below
  (halls: more of the same render; towns: a stone frame). Those rows have no PC art and stay PS1 pixels (2x
  nearest). Exceptions measured by correlation: PM 8 (29 rows down, 1 px left), PM 35 (5 rows down).
  The 320x200 PS1 pictures (PM 19, 20, 23, 25, 29) are the whole PC picture.
- Hall colours: the PC pictures are dithered to the shared PC palette and are brighter than the PS1's 240-row
  re-renders (own 256-colour palette each); the 200-row ones and the towns have the same colours on both.
"""
import json, os, struct, sys
import numpy as np
import xxhash
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ls11, timdump

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PS1 = os.path.join(ROOT, 'work', 'ps1')     # folder with the PS1 disc's files (hdpack.py sets it)
W, PCH = 320, 200
# PS1 file -> (PC archive, decoder, {TIM: PC entry}, {TIM: (dy, dx)} where the half-size PC picture sits)
HALL_OF = {**{n: n for n in range(40)}, 23: 25, 25: 23}
TOWN_OF = {n: n + 1 for n in range(1, 27)}
OFFSET = {('PM.BIN', 8): (29, -1), ('PM.BIN', 35): (5, 0)}
# PC halls carry a red exit arrow (one 32x20 sprite, also mirrored) that the PS1 draws as a sprite instead:
# PC entry -> top left corner in the PC picture (found by searching all 40 pictures for the sprite)
ARROW = {**{n: (592, 368) for n in (2, 3, 6, 9, 10, 14, 19, 24, 28)}, **{n: (16, 368) for n in (1, 13, 16, 20, 22, 26)},
         0: (0, 60), 4: (0, 64), 7: (0, 66), 15: (0, 57), 5: (608, 37), 17: (598, 57)}
# PS1 pictures that show something else than the PC one in places (halls: a person baked in, furniture or curtains
# moved; town 18: another hill, no river): (file, TIM) -> rectangles (x0, y0, x1, y1) in PS1 pixels that stay PS1
# pixels (set by eye)
KEEP = {('PM.BIN', 22): [(160, 97, 232, 150)], ('PM.BIN', 24): [(76, 88, 224, 164)],
        ('PM.BIN', 36): [(204, 116, 263, 164), (256, 190, 320, 220), (212, 20, 320, 80)],
        ('PM.BIN', 37): [(154, 117, 217, 169), (212, 20, 320, 112)],
        ('SMAP.E2', 18): [(0, 20, 320, 94)]}


def lsents(path):
    d = open(path, 'rb').read()
    dic, ents = ls11.entries(d)
    return [np.frombuffer(d[o:o + c] if c == u else ls11.decode(d[o:o + c], u, dic), dtype=np.uint8) for c, u, o in ents]


def tiles(e):
    return e.reshape(50, 80, 8, 8).transpose(0, 2, 1, 3).reshape(400, 640)


def raw(e):
    return e.reshape(400, 640)


SETS = (('PM.BIN', 'PMAPCHIP.E2', tiles, HALL_OF, 'hall'), ('SMAP.E2', 'MMAP.E2', raw, TOWN_OF, 'town overview'))


def ps1_tims(rel):
    d = open(os.path.join(PS1, rel), 'rb').read()
    o, out = 0, []
    while o + 8 <= len(d):
        t = timdump.parse(d, o)
        if not t:
            break
        out.append(t); o = (t['end'] + 3) & ~3
    return out


def name(t, idx):
    lo, hi = int(idx.min()), int(idx.max())
    pal = t['pal'][0]
    return 'texupload-P8-%016X-%016X-%dx%d-0-0-%dx%d-P%d-%d.png' % (
        xxhash.xxh3_64_intdigest(t['pix']), xxhash.xxh3_64_intdigest(struct.pack('<%dH' % (hi - lo + 1), *pal[:hi - lo + 1])),
        t['w'], t['h'], t['w'] * 2, t['h'], lo, hi)


def box(x, k):
    """k x k box mean (k odd), edges repeated"""
    p = np.pad(x, k // 2, mode='edge')
    c = np.pad(np.cumsum(np.cumsum(p, 0, dtype=np.float64), 1), ((1, 0), (1, 0)))
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def repair(pc, ps2, pal):
    """PC palette with the entries replaced that are plainly other colours in this PS1 picture (mean PS1 colour
    under the index off by more than 40): PALET.E2 is not the whole story for the town overviews (water blues are
    purple in it, hills of town 18 ...)."""
    out = pal.copy()
    flat, col = pc.ravel(), ps2.reshape(-1, 3).astype(np.float64)
    n = np.bincount(flat, minlength=256)
    mean = np.stack([np.bincount(flat, weights=col[:, c], minlength=256) for c in range(3)], axis=1) / np.maximum(n, 1)[:, None]
    bad = (n >= 80) & (np.abs(mean - pal).max(axis=1) > 40)
    out[bad] = np.clip(mean[bad] + 0.5, 0, 255).astype(np.uint8)
    return out, int(bad.sum())


LEVELS = 6


def arrow_mask(pc, pal, x, y):
    """the exit arrow's pixels (red or near black inside its 32x20 box), grown by 2 px"""
    r, g, b = (pal[:, i].astype(int) for i in range(3))
    lut = ((r >= 50) & (g < r * 0.5) & (b < r * 0.5)) | ((r < 70) & (g < 45) & (b < 45))
    m = np.zeros(pc.shape, bool)
    m[y:y + 20, x:x + 32] = lut[pc[y:y + 20, x:x + 32]]
    return box(m.astype(np.float64), 5) > 1e-9


def tone(pc, ps2, ok):
    """PC picture in the PS1 picture's colours: every pixel gets the mean PS1 colour of the pixels that share its
    PC palette index and local brightness (blurred PS1 picture, LEVELS soft classes, interpolated). The index alone
    is not enough: the PC pictures are dithered, so a dark carpet's colours are also sprinkled over a light floor.
    Pixels outside `ok` (where the two pictures show different things) are left out of the means."""
    lum = box(ps2.astype(np.float64).mean(axis=2), 9).ravel() * (LEVELS - 1) / 255
    lo = np.minimum(lum.astype(np.int64), LEVELS - 2)
    frac = lum - lo
    flat, col = pc.ravel().astype(np.int64), ps2.reshape(-1, 3).astype(np.float64)
    size = 256 * LEVELS
    wsum, csum = np.zeros(size), np.zeros((size, 3))
    for lev, w in ((lo, (1 - frac) * ok.ravel()), (lo + 1, frac * ok.ravel())):
        k = flat * LEVELS + lev
        wsum += np.bincount(k, weights=w, minlength=size)
        for c in range(3):
            csum[:, c] += np.bincount(k, weights=w * col[:, c], minlength=size)
    mean = csum / np.maximum(wsum, 1e-9)[:, None]
    out = mean[flat * LEVELS + lo] * (1 - frac)[:, None] + mean[flat * LEVELS + lo + 1] * frac[:, None]
    return np.clip(out + 0.5, 0, 255).astype(np.uint8).reshape(ps2.shape)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    pcdir, out = argv[:2]
    os.makedirs(out, exist_ok=True)
    names = {f.lower(): f for f in os.listdir(pcdir)}
    p = np.frombuffer(open(os.path.join(pcdir, names['palet.e2']), 'rb').read(), dtype=np.uint8).reshape(256, 3)
    pal = p[:, (1, 2, 0)]
    report, n_png = [], 0
    for rel, arc, dec, pc_of, what in SETS:
        ents = lsents(os.path.join(pcdir, names[arc.lower()]))
        for n, t in enumerate(ps1_tims(rel)):
            w, h = t['w'] * 2, t['h']
            if t['bpp'] != 1 or w != W:
                report.append(dict(file=rel, tim=n, why='not a 320-wide 8bpp picture')); continue
            if n not in pc_of:
                report.append(dict(file=rel, tim=n, why='no PC picture')); continue
            idx = np.frombuffer(t['pix'], dtype=np.uint8)[:w * h].reshape(h, w)
            ps = np.array([timdump.c15(v)[:3] for v in t['pal'][0]], np.uint8)[idx]
            ps2 = np.repeat(np.repeat(ps, 2, axis=0), 2, axis=1)
            dy, dx = OFFSET.get((rel, n), ((h - PCH) // 2, 0))
            pc = dec(ents[pc_of[n]])
            # the part of the PC picture that falls inside the PS1 one (PC px = 2 * PS1 px)
            y0, x0 = max(0, 2 * dy), max(0, 2 * dx)
            y1, x1 = min(2 * h, 2 * dy + 400), min(2 * w, 2 * dx + 640)
            part = pc[y0 - 2 * dy:y1 - 2 * dy, x0 - 2 * dx:x1 - 2 * dx]
            # where the PS1 picture stays: no PC art there, PC exit arrow, PS1-only render differences
            keep = np.ones((2 * h, 2 * w), bool)
            keep[y0:y1, x0:x1] = False
            notes = []
            if rel == 'PM.BIN':
                if pc_of[n] in ARROW:
                    keep[2 * dy:2 * dy + 400, max(0, 2 * dx):2 * dx + 640] |= arrow_mask(pc, pal, *ARROW[pc_of[n]])[:, max(0, -2 * dx):]
                    notes.append('PC exit arrow')
            for rx0, ry0, rx1, ry1 in KEEP.get((rel, n), ()):
                keep[2 * ry0:2 * ry1, 2 * rx0:2 * rx1] = True
            if (rel, n) in KEEP:
                notes.append('%d area(s) where the PS1 picture shows something else' % len(KEEP[rel, n]))
            big = ps2.copy()
            if '--pc-colours' not in argv and rel == 'PM.BIN' and h > PCH:
                new = tone(part, ps2[y0:y1, x0:x1], ~keep[y0:y1, x0:x1])
            elif rel == 'SMAP.E2' and '--pc-colours' not in argv:
                ok = ~keep[y0:y1, x0:x1]
                fixed, nbad = repair(part[ok], ps2[y0:y1, x0:x1][ok], pal)
                new = fixed[part]
                if nbad:
                    notes.append('%d palette entries taken from the PS1 picture' % nbad)
            else:
                new = pal[part]
            big[y0:y1, x0:x1] = np.where(keep[y0:y1, x0:x1, None], ps2[y0:y1, x0:x1], new)
            rgba = np.dstack([big, np.full(big.shape[:2], 255, np.uint8)])
            Image.fromarray(rgba, 'RGBA').save(os.path.join(out, name(t, idx)))
            n_png += 1
            rows = [r for r in range(h) if not (y0 <= 2 * r < y1)]
            if rows:
                notes.insert(0, 'rows %d-%d and %d-%d have no PC art' % (rows[0], y0 // 2 - 1, y1 // 2, rows[-1]))
            if notes:
                report.append(dict(file=rel, tim=n, why='%s: %s (PS1 pixels, %.1f%%)' % (
                    what, '; '.join(notes), 100 * keep.mean())))
            if '--preview' in argv:
                Image.fromarray(np.hstack([ps2, big]), 'RGB').save(
                    os.path.join(out, 'preview_%s_%02d.png' % (rel.split('.')[0], n)))
    json.dump(report, open(os.path.join(out, 'hd_report.json'), 'w'), indent=1)
    print(n_png, 'PNGs ->', out, '| kept as PS1:', sum('no PC picture' in r['why'] for r in report), 'pictures whole,',
          sum('PS1 pixels' in r['why'] for r in report), 'in part')


if __name__ == '__main__':
    main()
