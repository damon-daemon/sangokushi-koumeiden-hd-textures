"""HD texture pack coverage audit (offline): every texture file on the PS1 disc against the replacement PNGs.

usage: python tools/dev/hdaudit.py PS1 [--repl DIR]... [--dumps DIR]... [--report FILE]... [--full] [-o OUT]
  PS1       track 1 of the PlayStation disc (image file), or a folder holding all of its files
  --repl    folder(s) of replacement PNGs (default: out/, where hdpack.py writes them)
  --dumps   folder(s) of DuckStation texture dumps (default: none)
  --report  hd_report.json files written by the generators: what they left as PS1 pixels
            (default: work/gen/*/hd_report.json, kept by hdpack.py --keep-work)
  -o        the report (default: work/audit.md; the summary is also printed); --full lists every TIM with its names

What it does
  1. goes through every file of the PS1 disc (not movies, music) and parses every TIM;
  2. computes the DuckStation texture-cache name(s) each TIM gets when it is uploaded whole:
       texupload-P<4|8>-<XXH3 of the pixel data>-<XXH3 of the first hi-lo+1 CLUT words>-<w>x<h>-<x>-<y>-<rw>x<rh>-P<lo>-<hi>
     (lo..hi = CLUT indices used inside the rect; w = VRAM words). Per-file rules: HEXU = 4 side CLUTs from the EXE,
     HEXMAP = split at px 64 (and 192);
  3. marks a TIM "replaced" when the replacement folder holds a PNG with its pixel hash (the first hash in the name is
     of the whole upload, so it identifies the TIM whatever the rect), and says whether the name was a predicted one;
  4. folds in the generators' reports (parts of a replaced texture that are still PS1 pixels);
  5. maps every dumped name back to file + TIM; dumps whose hash is no TIM on the disc are run-time textures.
A dump taken with DumpReplacedTextures off holds only what was NOT replaced: run this on that folder for the miss list.
"""
import glob, json, os, re, struct, sys
from collections import defaultdict
import xxhash
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'gen'))
import disc, timdump

SKIP_DIRS = ('pc', 'MOVIE', 'IMOVIE1', 'IMOVIE2', 'BGM', 'BGM2')
NAME = re.compile(r'texupload-P(\d+)-([0-9A-F]{16})-([0-9A-F]{16})-(\d+)x(\d+)-(\d+)-(\d+)-(\d+)x(\d+)-P(\d+)-(\d+)\.png$')

# What the PC (Win95) disc has for each PS1 file. state: 'gen' = a generator exists, 'todo' = PC art exists or is
# likely, not wired up, 'none' = no PC art / no gain, 'runtime' = never sampled as uploaded (copied into work pages).
PC = {
    'SNR/KAO.BIN':    ('gen',  'hdfaces.py: PC KAO.E2 64x80 (288 of 303 faces)'),
    'SNR/ORGKAO.BIN': ('gen',  'copy of KAO.BIN (same hashes = same PNGs) except 0, 1, 211 = staff photos (joke set, no PC art)'),
    'HEX/HEXU.BIN':   ('gen',  'hdunits.py: PC CHR_IDO / CHR_ATT 48x48, 4 side palettes'),
    'HEX/HEXMAP.BIN': ('gen',  'hdmaps.py: PC m01-m50.e2 at 6x (50 of 52 maps)'),
    'PM.BIN':         ('gen',  'hdbacks.py: halls = PC PMAPCHIP.E2 640x400 (40 of 41; the PC picture is the middle 200 rows)'),
    'SMAP.E2':        ('gen',  'hdbacks.py: town overviews = PC MMAP.E2 640x400 (26 of 29; 0 world map: the PC world maps MMAP 0/1 are other pictures; 27, 28 have no PC picture)'),
    'NL.BIN':         ('none', 'title / loading / config screens: no PC picture (the PC disc has no such archive; its program holds only icons and cursors)'),
    'SNR/MARK.BIN':   ('none', 'icons and stat plates: PC MARK.E2 icons are smaller (24x24 vs 32x32), ITEM.E2 = 27 item pictures 48x48, other art'),
    'HEX/HEXF.BIN':   ('none', 'close-up terrain backdrops: no PC picture (HEXZCHP.E2 / hmapchip.e2 = 16x16 battle map tiles, HEXEFF.E2 = panels + effect cells, MARK.E2 tail = copyright text + logo)'),
    'HEX/HEXC.BIN':   ('none', 'attack close-up sheets (64x56 frames): already PC-size art, no gain'),
    'HEX/HEXM.BIN':   ('none', 'attack close-up sheets (64x56 frames): already PC-size art, no gain'),
    'PMAP/JJMARK.BIN': ('none', 'town sprites 32x40: PC PMAPOBJ.E2 is the same size'),
    'PMAP/MASK.BIN':  ('none', 'town foreground masks: cut from the PS1 backdrops (revisit with hdbacks)'),
}
PC_DEFAULT = {'PMAP': ('none', 'town/hall sprites 32x40: PC PMAPOBJ.E2 is the same size'),
              'PMAP2': ('none', 'town/hall sprites 32x40: PC PMAPOBJ.E2 is the same size')}
# files that are not TIM containers but may hold graphics
OTHER = {
    'HEX/HEXZ.BIN':  'battle data archive (entry 55 = battle names); graphics inside not surveyed',
    'SNR/MMAP.E2':   'byte-identical to the PC MMAP.E2 (LS11, 28 x 640x400 = the town overviews hdbacks.py uses): used by the PS1 program?',
    'SNR/PMAP.E2':   'hall walk grids (100x100 words per hall, as on the PC); not graphics',
    'SLPS_006.88':   'program: font (drawn into VRAM at run time), unit side CLUTs, cursor/frame bitmaps not surveyed',
}


def h64(b):
    return '%016X' % xxhash.xxh3_64_intdigest(b)


def source(ps1):
    """(sorted file names, read(name)) for a disc image or a folder of the disc's files."""
    if os.path.isdir(ps1):
        names = [os.path.relpath(os.path.join(r, f), ps1).replace(os.sep, '/') for r, _, fs in os.walk(ps1) for f in fs]
        read = lambda rel: open(os.path.join(ps1, rel), 'rb').read()
    else:
        d = disc.Disc(ps1)
        files = d.files()
        names = [n for n in files if not n.endswith(('.DA', '.STR'))]
        read = lambda rel: d.read(*files[rel])
    names = [n for n in names if n.split('/')[0] not in SKIP_DIRS]
    return sorted(names, key=lambda n: ('/' in n, n)), read


def tims(d):
    o, out, junk = 0, [], 0
    while o + 20 <= len(d):
        t = None
        if d[o:o + 4] == b'\x10\0\0\0':
            try:
                t = timdump.parse(d, o)
            except struct.error:
                t = None
        if (t and t['bpp'] <= 1 and t['pal'] and t['end'] <= len(d) and 0 < t['w'] <= 512 and 0 < t['h'] <= 512
                and len(t['pix']) >= t['w'] * t['h'] * 2):
            out.append(t); o = (t['end'] + 3) & ~3
        else:
            o += 4; junk += 4
    return out, junk, len(d)


def indices(t):
    """-> rows of palette indices (list of bytes objects, one per row), width in px"""
    w16, h = t['w'], t['h']
    px = t['pix'][:w16 * h * 2]
    if t['bpp'] == 1:
        W = w16 * 2
        return [px[y * W:(y + 1) * W] for y in range(h)], W
    W = w16 * 4
    full = bytes(v for b in px for v in (b & 15, b >> 4))
    return [full[y * W:(y + 1) * W] for y in range(h)], W


def rect_name(t, rows, clut, x0, x1, y0=0, y1=None):
    y1 = t['h'] if y1 is None else y1
    used = set()
    for r in rows[y0:y1]:
        used.update(r[x0:x1])
    lo, hi = min(used), max(used)
    return 'texupload-P%d-%s-%s-%dx%d-%d-%d-%dx%d-P%d-%d.png' % (
        8 if t['bpp'] else 4, h64(t['pix']), h64(struct.pack('<%dH' % (hi - lo + 1), *clut[:hi - lo + 1])),
        t['w'], t['h'], x0, y0, x1 - x0, y1 - y0, lo, hi)


_side = READ = None
def side_cluts(tim_clut):
    global _side
    if _side is None:
        d = READ('SLPS_006.88')
        i = d.find(struct.pack('<16H', *tim_clut))
        _side = [struct.unpack_from('<16H', d, i - 0x40 + 0x20 * k) for k in range(4)] if i >= 0x40 else [tim_clut]
    return _side


def predicted(rel, t):
    """names this TIM is expected to get -> {name: note}"""
    rows, W = indices(t)
    own = t['pal'][0]
    if rel == 'HEX/HEXU.BIN':
        return {rect_name(t, rows, c, 0, W): 'side %s' % s for s, c in zip(('blue', 'purple', 'red', 'white'), side_cluts(own))}
    if rel == 'HEX/HEXMAP.BIN':
        out = {rect_name(t, rows, own, 0, min(W, 64)): 'px 0-63'}
        if W > 64:
            out[rect_name(t, rows, own, 64, W)] = 'px 64-%d' % (W - 1)
        if W > 192:
            out[rect_name(t, rows, own, 64, 192)] = 'px 64-191 (if split at 192)'
            out[rect_name(t, rows, own, 192, W)] = 'px 192-%d (if split at 192)' % (W - 1)
        return out
    return {rect_name(t, rows, own, 0, W): 'whole'}


def ranges(ns):
    ns = sorted(ns); out = []; i = 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        out.append('%d' % ns[i] if i == j else '%d-%d' % (ns[i], ns[j])); i = j + 1
    return ', '.join(out)


def whole(f):
    m = NAME.match(f)
    mul = 2 if m.group(1) == '8' else 4
    return (m.group(6), m.group(7)) == ('0', '0') and int(m.group(8)) == int(m.group(4)) * mul and m.group(9) == m.group(5)


def listdir(d):
    return [f for f in os.listdir(d) if NAME.match(f)] if os.path.isdir(d) else []


def args_of(flag, argv):
    return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == flag]


def main():
    global READ
    argv = sys.argv[1:]
    if not argv or argv[0].startswith('-') or not os.path.exists(argv[0]):
        sys.exit(__doc__)
    files, READ = source(argv[0])
    repl = args_of('--repl', argv) or [os.path.join(ROOT, 'out')]
    dumps = args_of('--dumps', argv)
    reports = args_of('--report', argv) or sorted(glob.glob(os.path.join(ROOT, 'work', 'gen', '*', 'hd_report.json')))
    out = (args_of('-o', argv) or [os.path.join(ROOT, 'work', 'audit.md')])[0]
    full = '--full' in argv

    rnames = {f for d in repl for f in listdir(d)}
    rhash = defaultdict(set)
    for f in rnames:
        rhash[NAME.match(f).group(2)].add(f)
    dnames = {}
    for d in dumps:
        for f in listdir(d):
            dnames.setdefault(f, os.path.basename(d.rstrip('/')))
    left = defaultdict(dict)                    # file -> tim -> note (still PS1 pixels inside a replaced texture)
    for r in reports:
        for e in json.load(open(r)):
            left[e['file']][e['tim']] = e['why']

    L, summ = [], []
    P = L.append
    byhash = {}                                 # pixel hash -> (file, tim)
    cluts = {}                                  # pixel hash -> CLUTs the game may draw this TIM with
    used_repl = set()
    tot = defaultdict(int)
    for rel in files:
        ts, junk, size = tims(READ(rel))
        if not ts:
            if rel in OTHER:
                summ.append((rel, 0, 'not a TIM file', OTHER[rel]))
            continue
        state, src = PC.get(rel) or PC_DEFAULT.get(os.path.dirname(rel)) or ('todo', 'PC counterpart not looked up')
        groups = defaultdict(list)              # status -> tim numbers
        rowsout = []
        for n, t in enumerate(ts):
            th = h64(t['pix'])
            dup = byhash.get(th)
            byhash.setdefault(th, (rel, n))
            cluts.setdefault(th, side_cluts(t['pal'][0]) if rel == 'HEX/HEXU.BIN' else [t['pal'][0]])
            pred = predicted(rel, t)
            if dup and n not in left[rel] and dup[1] in left[dup[0]]:
                left[rel][n] = left[dup[0]][dup[1]]
            have = rhash.get(th, set())
            used_repl |= have
            seen = sorted(f for f in dnames if NAME.match(f).group(2) == th)
            hit = [f for f in pred if f in have]
            if have:
                st = 'replaced'
                if not hit:
                    st = 'replaced, but under a name that was not predicted'
                elif rel == 'HEX/HEXU.BIN' and len(hit) < len(pred):
                    st = 'replaced for %d of %d side palettes' % (len(hit), len(pred))
                if n in left[rel]:
                    st += '; PS1 pixels kept: ' + left[rel][n]
            elif state == 'gen':
                st = 'NOT replaced: ' + (left[rel].get(n) or 'generator made no PNG')
            elif state == 'todo':
                st = 'NOT replaced: PC source to do'
            elif state == 'runtime':
                st = 'not replaceable (run-time work page source)'
            else:
                st = 'not replaced: no PC source / no gain'
            # a dump of the whole upload under another name = the offline rule is wrong for this TIM (sub-rect dumps
            # are normal: DuckStation dumps what was sampled, and still takes a whole-upload replacement)
            odd = [f for f in seen if f not in pred and whole(f)]
            if odd:
                st += ' [RULE MISS: dumped whole under %d other name(s)]' % len(odd)
            groups[st].append(n)
            tot[st.split(':')[0].split(';')[0].split(' [')[0]] += 1
            W = t['w'] * (2 if t['bpp'] else 4)
            rowsout.append((n, 'P%d %dx%d' % (8 if t['bpp'] else 4, W, t['h']), st, pred, seen, dup))
        P('## %s — %d TIMs%s' % (rel, len(ts), ', %d B not TIM' % junk if junk else ''))
        P('PC source: %s' % src)
        P('')
        P('| TIMs | count | status |'); P('|---|---|---|')
        for st, ns in sorted(groups.items(), key=lambda kv: kv[1][0]):
            P('| %s | %d | %s |' % (ranges(ns), len(ns), st))
        P('')
        nsub = sum(1 for _, _, _, pred, seen, _ in rowsout for f in seen if f not in pred and not whole(f))
        nok = sum(1 for _, _, _, pred, seen, _ in rowsout for f in seen if f in pred)
        if nsub or nok:
            P('Dumps: %d under a predicted name, %d as sub-rects.' % (nok, nsub)); P('')
        odd_rows = [(n, f) for n, _, _, pred, seen, _ in rowsout for f in seen if f not in pred and whole(f)]
        if odd_rows:
            P('Whole-upload dumps that the offline rule did not predict (rule to refine):')
            for n, f in odd_rows[:40]:
                P('- TIM %d: `%s` (%s)' % (n, f, dnames[f]))
            if len(odd_rows) > 40:
                P('- ... %d more' % (len(odd_rows) - 40))
            P('')
        dups = [(n, d) for n, _, _, _, _, d in rowsout if d]
        if dups:
            P('%d TIMs have the same pixels as an earlier TIM (one PNG serves both), e.g. %s.' % (
                len(dups), ', '.join('%d = %s #%d' % (n, d[0], d[1]) for n, d in dups[:3])))
            P('')
        if full:
            for n, kind, st, pred, seen, _ in rowsout:
                P('- TIM %d %s: %s' % (n, kind, st))
                for f, note in pred.items():
                    P('  - %s `%s` %s' % ('[x]' if f in rnames else '[ ]', f, note))
            P('')
        nrep = sum(len(ns) for st, ns in groups.items() if st.startswith('replaced'))
        summ.append((rel, len(ts), '%d replaced' % nrep if nrep else state, src))

    # replacement PNGs that match no TIM (stale or mis-named)
    stale = sorted(rnames - used_repl)
    # dumps: map back
    P('## Dumped textures')
    P('')
    for folder in sorted(set(dnames.values())):
        fs = sorted(f for f, d in dnames.items() if d == folder)
        known = defaultdict(list); unknown = defaultdict(int)
        for f in fs:
            m = NAME.match(f)
            if m.group(2) in byhash:
                known[byhash[m.group(2)][0]].append((byhash[m.group(2)][1], f))
            else:
                unknown['P%s %sx%s words, rect %sx%s' % (m.group(1), m.group(4), m.group(5), m.group(8), m.group(9))] += 1
        P('### %s — %d files' % (folder, len(fs)))
        for rel, lst in sorted(known.items()):
            # A dump is skipped only when a replacement has the very same name; a replacement is applied when the
            # upload hash matches and its own palette range hashes the same in the palette of the draw. So a
            # sub-rect dump of a replaced upload is no miss if a known CLUT explains the dump's palette hash and
            # gives the replacement's palette hash too.
            nrep = miss = 0
            for n, f in lst:
                m = NAME.match(f)
                if m.group(2) not in rhash:
                    continue
                nd = int(m.group(11)) - int(m.group(10)) + 1
                ok = False
                for c in cluts[m.group(2)]:
                    if h64(struct.pack('<%dH' % nd, *c[:nd])) != m.group(3):
                        continue
                    for r in rhash[m.group(2)]:
                        k = NAME.match(r)
                        nr = int(k.group(11)) - int(k.group(10)) + 1
                        ok |= h64(struct.pack('<%dH' % nr, *c[:nr])) == k.group(3)
                nrep += ok
                if not ok:
                    miss += 1
                    P('- **MISS** %s TIM %d: `%s` (upload has a replacement, but not for this palette)' % (rel, n, f))
            P('- %s: %d dumps of TIMs %s (%d = sub-rects of a replaced upload, same palette: replaced on screen%s)' % (
                rel, len(lst), ranges({n for n, _ in lst}), nrep, '; %d MISS' % miss if miss else ''))
        if unknown:
            P('- not a TIM on the disc (run-time: text, work pages, program bitmaps): %d' % sum(unknown.values()))
            for k, v in sorted(unknown.items(), key=lambda kv: -kv[1]):
                P('  - %d x %s' % (v, k))
        P('')
    if stale:
        P('## Replacement PNGs matching no TIM on the disc: %d' % len(stale))
        for f in stale[:20]:
            P('- `%s`' % f)
        P('')

    head = ['# HD texture pack coverage (tools/dev/hdaudit.py)', '',
            'replacement folder(s): %s (%d PNGs); dump folders: %d; generator reports: %d' % (
                ', '.join(os.path.relpath(d, ROOT) for d in repl), len(rnames), len(set(dnames.values())), len(reports)), '',
            '| file | TIMs | state | PC source |', '|---|---|---|---|']
    head += ['| %s | %s | %s | %s |' % (rel, n or '-', st, src) for rel, n, st, src in summ]
    head += ['', '| status | TIMs |', '|---|---|'] + ['| %s | %d |' % kv for kv in sorted(tot.items(), key=lambda kv: -kv[1])] + ['']
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, 'w').write('\n'.join(head + L) + '\n')
    print('\n'.join(head))
    print('->', out)


if __name__ == '__main__':
    main()
