"""HD portraits: DuckStation texture replacements for the PS1 faces (SNR/KAO.BIN, 48x64)
made from the PC (Win95) release's faces (KAO.E2, LS11, 288 x 64x80 8bpp) on the user's own PC disc.

usage: python gen/hdfaces.py PC_KAO.E2 PC_PALET.E2 OUTDIR [--keep-bg]
  -> OUTDIR/texupload-P8-<tex hash>-<palette hash>-24x64-0-0-48x64-P<lo>-<hi>.png (192x256, 4x)
  copy them to <DuckStation>/textures/<serial>/replacements/ (hardware renderer, texture cache +
  texture replacements on; the game is listed as SLPM-86205).

Facts: the PS1 face is the PC face at 0.75x, placed 7.5 rows down (the top rows are empty,
the PC bottom rows are cut). 4x output = each PC pixel as a 3x3 block, 30 rows down. PC palette =
PALET.E2 with R,G,B = bytes 1,2,0 of each triple. PC faces have a coloured backdrop, PS1 ones colour 0
(transparent): the backdrop is removed unless --keep-bg; where the PS1 face has art and the PC one only
backdrop or nothing (plumes and hat tops above the PC frame) the PS1 pixels are kept (4x nearest). File names = XXH3-64 of the TIM pixel data and
of the palette entries lo..hi (lowest..highest index used), as DuckStation's dumps (verified on 4).
"""
import json, os, struct, sys
import numpy as np
import xxhash
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ls11, timdump

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PS1 = os.path.join(ROOT, 'work', 'ps1')     # folder with the PS1 disc's files (hdpack.py sets it)
SCALE, OY = 4, 7.5


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


def backdrop(pc, solid, pcrgb, psrgb):
    """pc 80x64 indices, solid 64x48 bool (PS1 pixel not transparent), pcrgb 80x64x3 PC colours, psrgb 64x48x3
    PS1 colours -> (gone, fromps1): 80x64 bools. gone = backdrop to make transparent; fromps1 = backdrop that
    shows where the PS1 face has art of its own (plumes, hat tops) -> those pixels are taken from the PS1 face."""
    ys = np.clip(np.floor((np.arange(80) + 0.5) * 0.75 + OY).astype(int), 0, 63)
    xs = np.floor((np.arange(64) + 0.5) * 0.75).astype(int)
    pad = np.pad(solid, 2, constant_values=False)
    def near(r):     # any solid PS1 pixel within r of the mapped position
        acc = np.zeros((80, 64), bool)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                acc |= pad[np.clip(ys + dy + 2, 0, 67)][:, np.clip(xs + dx + 2, 0, 51)]
        return acc
    here, n1, n2 = near(0), near(1), near(2)
    bgidx = [i for i in np.unique(pc) if (~here[pc == i]).mean() > 0.8]     # colours that live in the backdrop
    gone = (~n2) | (np.isin(pc, bgidx) & ~here)
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
    capped = extra.sum() > 500     # the two pictures do not line up (face 262): leave the PC pixels alone
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
    top = int(OY * SCALE)
    report = []                      # what stays PS1 pixels, for the audit
    for n, (c, u, o) in enumerate(ents):
        b = d[o:o + c]
        pc = np.frombuffer(b if c == u else ls11.decode(b, u, dic), dtype=np.uint8).reshape(80, 64)
        t = tims[n]
        solid = np.frombuffer(t['pix'], dtype=np.uint8).reshape(64, 48) != 0
        rgba = np.dstack([pal[pc], np.full((80, 64), 255, np.uint8)])
        ps1 = np.array([timdump.c15(v) for v in t['pal'][0]], np.uint8)[np.frombuffer(t['pix'], dtype=np.uint8).reshape(64, 48)]
        ps1 = np.repeat(np.repeat(ps1, SCALE, axis=0), SCALE, axis=1)          # the PS1 face, 4x nearest
        img = np.zeros((64 * SCALE, 48 * SCALE, 4), np.uint8)
        if keep:
            img[top:] = np.repeat(np.repeat(rgba, 3, axis=0), 3, axis=1)[:64 * SCALE - top]
        else:
            psrgb = np.array([timdump.c15(v)[:3] for v in t['pal'][0]], np.uint8)[np.frombuffer(t['pix'], dtype=np.uint8).reshape(64, 48)]
            gone, fromps1, capped = backdrop(pc, solid, pal[pc], psrgb)
            # PS1 pixels in the output, counted on the PS1 grid (48x64 = 3072): hat tops above the PC frame + plumes
            px = int(solid[:int(OY)].sum()) + int(round(fromps1.sum() * 0.5625))
            if px:
                report.append(dict(file='SNR/KAO.BIN', tim=n, px=px, why='hat top / plume from the PS1 face, %s' % (
                    'under 2% of the picture' if px < 62 else '2% of the picture or more')))
            elif capped:
                report.append(dict(file='SNR/KAO.BIN', tim=n, px=0, why='none (PC face does not line up with the PS1 one: PC pixels only)'))
            rgba[gone | fromps1] = 0
            big = np.repeat(np.repeat(rgba, 3, axis=0), 3, axis=1)             # 240x192
            use = np.repeat(np.repeat(fromps1, 3, axis=0), 3, axis=1)
            img[top:] = big[:64 * SCALE - top]
            img[top:][use[:64 * SCALE - top]] = ps1[top:][use[:64 * SCALE - top]]
            img[:top] = ps1[:top]                                              # rows above the PC frame
        Image.fromarray(img, 'RGBA').save(os.path.join(out, name(t)))
    report += [dict(file='SNR/KAO.BIN', tim=n, why='no PC face (PS1-only portrait)') for n in range(len(ents), len(tims))]
    json.dump(report, open(os.path.join(out, 'hd_report.json'), 'w'), indent=1)
    print(len(ents), 'faces ->', out, '(%d with PS1 pixels kept, %d PS1 faces without PC art)' % (
        sum(1 for r in report if r.get('px')), len(tims) - len(ents)))


if __name__ == '__main__':
    main()
