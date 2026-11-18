"""HD portraits: DuckStation texture replacements for the PS1 faces (SNR/KAO.BIN, 48x64)
made from the PC (Win95) release's faces (KAO.E2, LS11, 288 x 64x80 8bpp) on the user's own PC disc.

usage: python gen/hdfaces.py PC_KAO.E2 PC_PALET.E2 OUTDIR [--keep-bg]
  -> OUTDIR/texupload-P8-<tex hash>-<palette hash>-24x64-0-0-48x64-P<lo>-<hi>.png (192x256, 4x)
  copy them to <DuckStation>/textures/<serial>/replacements/ (hardware renderer, texture cache +
  texture replacements on; the game is listed as SLPM-86205).

Facts: the PS1 face is the PC face at 0.75x, cut out of its backdrop and placed in the 48x64 frame: about 7.5
rows down for most, but up to 3 rows higher or lower and, for about 40 faces, 1 to 5 columns left or right. The
place is found here for each face by matching the two pictures (place()). 4x output = each PC pixel as a 3x3
block at that place. PC palette = PALET.E2 with R,G,B = bytes 1,2,0 of each triple.
The outline is the PS1 face's: a PC pixel is shown where the PS1 face has a pixel (PC faces have a coloured,
dithered backdrop, PS1 ones colour 0 = transparent), so nothing of the backdrop stays around the head. Where the
PS1 face has art and the PC one only backdrop or nothing (plumes and hat tops above or beside the PC frame) the PS1
pixels are kept (4x nearest). --keep-bg shows the whole PC picture with its backdrop instead.
Eight PS1 faces are not the PC drawing (another headgear, other colours, another person): they get no replacement
and stay PS1 pictures (DIFFER). File names = XXH3-64 of the TIM pixel data and of the palette entries (the first
hi-lo+1, lo..hi = lowest..highest index used), as DuckStation's dumps (verified on 4).
"""
import json, os, struct, sys
import numpy as np
import xxhash
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ls11, timdump

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PS1 = os.path.join(ROOT, 'work', 'ps1')     # folder with the PS1 disc's files (hdpack.py sets it)
SCALE = 4
DIFFER = 0.17    # share of the face where the two pictures disagree; above it they are different drawings


def ps1_faces():
    d = open(os.path.join(PS1, 'SNR', 'KAO.BIN'), 'rb').read()
    o, out = 0, []
    while o + 8 <= len(d):
        t = timdump.parse(d, o)
        if not t:
            break
        out.append(t); o = t['end']
    return out


def name(t):
    pal, used = t['pal'][0], set(t['pix'])
    lo, hi = min(used), max(used)
    return 'texupload-P8-%016X-%016X-%dx%d-0-0-%dx%d-P%d-%d.png' % (
        xxhash.xxh3_64_intdigest(t['pix']), xxhash.xxh3_64_intdigest(struct.pack('<%dH' % (hi - lo + 1), *pal[:hi - lo + 1])),
        t['w'], t['h'], t['w'] * 2, t['h'], lo, hi)


def place(pcrgb, psrgb, solid):
    """where the PC face (80x64x3) sits on the 4x PS1 canvas (256x192): (y, x) of its top left corner in output
    pixels (one PC pixel = 3), and the share of the face where the two pictures still disagree at that place.
    Found by comparing the PS1 face with the PC one averaged down to PS1 pixels, inside the head only."""
    big = np.repeat(np.repeat(pcrgb.astype(np.float64), 3, axis=0), 3, axis=1)             # 240x192
    sat = np.zeros((241, 193, 3)); sat[1:, 1:] = big.cumsum(0).cumsum(1)
    ps = psrgb.astype(np.float64)
    def erode(m):
        q = np.pad(m, 1)
        return m & q[:-2, 1:-1] & q[2:, 1:-1] & q[1:-1, :-2] & q[1:-1, 2:]
    edge = erode(solid); inner = erode(edge)
    rows, cols = np.arange(64) * 4, np.arange(48) * 4
    def down(y0, x0):                    # the PC face seen through the PS1 pixel grid; ok = PS1 pixels it covers fully
        r, c = rows - y0, cols - x0
        ok = ((r >= 0) & (r <= 236))[:, None] & ((c >= 0) & (c <= 188))[None, :]
        r, c = np.clip(r, 0, 236), np.clip(c, 0, 188)
        d = (sat[r + 4][:, c + 4] - sat[r][:, c + 4] - sat[r + 4][:, c] + sat[r][:, c]) / 16
        return d, ok
    need = max(1, inner.sum() // 2)
    def err(y0, x0):
        d, ok = down(y0, x0); m = inner & ok
        return float(np.abs(d - ps)[m].mean()) if m.sum() >= need else 1e9
    best = min((err(y, x), y, x) for y in range(8, 57, 2) for x in range(-24, 25, 2))
    best = min((err(y, x), y, x) for y in range(best[1] - 2, best[1] + 3) for x in range(best[2] - 2, best[2] + 3))
    y0, x0 = best[1:]
    d, ok = down(y0, x0); m = edge & ok
    def blur(a):                         # 3x3 mean inside m: the dither of either picture must not count
        a = np.pad(a * m[..., None], ((1, 1), (1, 1), (0, 0))); k = np.pad(m.astype(np.float64), 1)
        box = lambda v: sum(v[1 + dy:65 + dy, 1 + dx:49 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        return box(a) / np.maximum(box(k), 1)[..., None]
    off = float((np.abs(blur(d) - blur(ps)).mean(-1)[m] > 60).mean()) if m.any() else 1.0
    return y0, x0, off


def backdrop(pc, solid, pcrgb, psrgb, y0, x0):
    """pc 80x64 indices, solid 64x48 bool (PS1 pixel not transparent), pcrgb 80x64x3 PC colours, psrgb 64x48x3
    PS1 colours, (y0, x0) from place() -> (gone, fromps1, capped): 80x64 bools. gone = PC pixels not shown (the PS1
    face has no pixel there); fromps1 = backdrop that shows where the PS1 face has art of its own (plumes, hat
    tops) -> those pixels are taken from the PS1 face."""
    yy, xx = (y0 + np.arange(80) * 3 + 1) // 4, (x0 + np.arange(64) * 3 + 1) // 4      # PS1 pixel under each PC pixel
    iny, inx = (yy >= 0) & (yy < 64), (xx >= 0) & (xx < 48)
    ys, xs = np.clip(yy, 0, 63), np.clip(xx, 0, 47)
    inside = iny[:, None] & inx[None, :]
    pad = np.pad(solid, 1, constant_values=False)
    here = solid[ys][:, xs] & inside
    n1 = np.zeros((80, 64), bool)        # any solid PS1 pixel next to the mapped position
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            n1 |= pad[np.clip(yy + dy + 1, 0, 65)][:, np.clip(xx + dx + 1, 0, 49)]
    gone = ~here
    # colours the backdrop is made of (98% of the area clearly outside the face)
    cnt = np.bincount(pc[~n1], minlength=256)
    order = np.argsort(-cnt); cum = np.cumsum(cnt[order])
    bgset = order[:int(np.searchsorted(cum, 0.98 * max(1, cum[-1]))) + 1] if cum[-1] else []
    # ... showing under solid PS1 pixels of a clearly different colour, connected to the removed backdrop
    diff = np.abs(pcrgb.astype(np.int16) - psrgb[ys][:, xs].astype(np.int16)).mean(-1)
    cand = np.isin(pc, bgset) & here & (diff > 60)
    grown = gone.copy()
    while True:
        g = np.pad(grown, 1, constant_values=True)
        nxt = grown | (cand & (g[:-2, 1:-1] | g[2:, 1:-1] | g[1:-1, :-2] | g[1:-1, 2:]))
        if (nxt == grown).all():
            break
        grown = nxt
    extra = grown & ~gone
    capped = extra.sum() > 500     # more than a plume: leave the PC pixels alone
    if capped:
        extra[:] = False
    return gone, extra, capped


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    kao, palet, out = argv[:3]
    keep = '--keep-bg' in argv
    os.makedirs(out, exist_ok=True)
    raw = np.frombuffer(open(palet, 'rb').read(), dtype=np.uint8).reshape(256, 3)
    pal = raw[:, (1, 2, 0)]
    d = open(kao, 'rb').read()
    dic, ents = ls11.entries(d)
    tims = ps1_faces()
    H, W = 64 * SCALE, 48 * SCALE
    report = []                      # what stays PS1 pixels, for the audit
    made = moved = 0
    for n, (c, u, o) in enumerate(ents):
        b = d[o:o + c]
        pc = np.frombuffer(b if c == u else ls11.decode(b, u, dic), dtype=np.uint8).reshape(80, 64)
        t = tims[n]
        pix = np.frombuffer(t['pix'], dtype=np.uint8).reshape(64, 48)
        solid = pix != 0
        ps4 = np.array([timdump.c15(v) for v in t['pal'][0]], np.uint8)[pix]
        y0, x0, off = place(pal[pc], ps4[..., :3], solid)
        if off > DIFFER:
            report.append(dict(file='SNR/KAO.BIN', tim=n, why='PS1 drawing differs from the PC one (%d%% of the face)' % round(off * 100)))
            continue
        moved += x0 != 0
        img = np.repeat(np.repeat(ps4, SCALE, axis=0), SCALE, axis=1)          # the PS1 face, 4x nearest
        frompc = np.zeros((H, W), bool)
        if keep:
            show, capped = np.ones((80, 64), bool), False
            img[:] = 0
        else:
            gone, fromps1, capped = backdrop(pc, solid, pal[pc], ps4[..., :3], y0, x0)
            show = ~(gone | fromps1)
        rgba = np.dstack([pal[pc], np.full((80, 64), 255, np.uint8)])
        big = np.repeat(np.repeat(rgba, 3, axis=0), 3, axis=1)                 # 240x192
        use = np.repeat(np.repeat(show, 3, axis=0), 3, axis=1)
        ya, xa, yb, xb = max(y0, 0), max(x0, 0), min(y0 + 240, H), min(x0 + 192, W)
        dst, src = (slice(ya, yb), slice(xa, xb)), (slice(ya - y0, yb - y0), slice(xa - x0, xb - x0))
        img[dst][use[src]] = big[src][use[src]]
        frompc[dst] = use[src]
        Image.fromarray(img, 'RGBA').save(os.path.join(out, name(t)))
        made += 1
        # PS1 pixels in the output, counted on the PS1 grid (48x64 = 3072): hat tops outside the PC frame + plumes
        px = int(round(((img[..., 3] != 0) & ~frompc).sum() / SCALE ** 2))
        if px and not keep:
            report.append(dict(file='SNR/KAO.BIN', tim=n, px=px, why='hat top / plume from the PS1 face, %s' % (
                'under 2% of the picture' if px < 62 else '2% of the picture or more')))
        elif capped:
            report.append(dict(file='SNR/KAO.BIN', tim=n, px=0, why='none (PC backdrop under much of the PS1 face: PC pixels only)'))
    report += [dict(file='SNR/KAO.BIN', tim=n, why='no PC face (PS1-only portrait)') for n in range(len(ents), len(tims))]
    json.dump(report, open(os.path.join(out, 'hd_report.json'), 'w'), indent=1)
    differ = [r['tim'] for r in report if 'differs' in r['why']]
    print(made, 'faces ->', out, '(%d not at the usual place, %d with PS1 pixels kept; stay PS1: %d drawn differently%s, %d without PC art)' % (
        moved, sum(1 for r in report if r.get('px')), len(differ), ' (%s)' % ', '.join(map(str, differ)) if differ else '',
        len(tims) - len(ents)))


if __name__ == '__main__':
    main()
