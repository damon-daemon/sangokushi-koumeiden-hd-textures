"""Sangokushi Koumeiden HD texture pack: build DuckStation texture replacements that show the PC (Windows 95)
release's higher-resolution art in the PlayStation game. Everything is made on your machine from your own two
discs; nothing from either disc is part of this repository.

usage: python hdpack.py PC_DISC PS1_TRACK1 [-o OUTDIR] [--pc-colours] [--keep-work]
  PC_DISC     image of the PC disc (raw .img/.bin with 2352-byte sectors, or a 2048-byte .iso),
              or a folder holding its files (the mounted disc)
  PS1_TRACK1  track 1 of the PlayStation disc (SLPS-00688), Japanese original or English-patched
  -o          where the PNGs go (default: out/). Copy them, or point -o straight at
              <DuckStation folder>/textures/SLPM-86205/replacements/
  --pc-colours  hall pictures keep the PC palette (default: the PlayStation picture's colours)
  --keep-work   keep the files taken from the discs and the generators' reports in work/

Needs: pip install -r requirements.txt (pillow, numpy, xxhash).
DuckStation: hardware renderer, texture cache and texture replacements on.
Parts: portraits (4x), battle map units (2x), battle maps (6x), halls and town overviews (2x);
see gen/hdfaces.py, hdunits.py, hdmaps.py, hdbacks.py for how each one is made.
"""
import glob, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'gen'))
GAME_ID = 'SLPM-86205'               # how DuckStation lists this disc
PS1_FILES = ['SNR/KAO.BIN', 'HEX/HEXU.BIN', 'HEX/HEXMAP.BIN', 'PM.BIN', 'SMAP.E2', 'SLPS_006.88']
PC_FILES = ['KAO.E2', 'PALET.E2', 'CHR_IDO.E2', 'CHR_ATT.E2', 'PMAPCHIP.E2', 'MMAP.E2'] + \
           ['M%02d.E2' % n for n in range(1, 51)]
PC_OPTIONAL = {'M44.E2', 'M45.E2'}   # not on the PC disc (those two maps stay PS1 pictures)


def pc_from_image(img, out):
    import disc
    d, got = disc.Disc(img), set()
    for name, (lba, size) in d.files().items():
        base = name.rsplit('/', 1)[-1]
        if base in PC_FILES and base not in got:
            open(os.path.join(out, base), 'wb').write(d.read(lba, size)); got.add(base)
    return got


def pc_from_dir(src, out):
    got = set()
    for dirpath, _, files in os.walk(src):
        for fn in files:
            if fn.upper() in PC_FILES and fn.upper() not in got:
                shutil.copyfile(os.path.join(dirpath, fn), os.path.join(out, fn.upper())); got.add(fn.upper())
    return got


def main():
    argv = sys.argv[1:]
    out = os.path.join(HERE, 'out')
    if '-o' in argv:
        i = argv.index('-o')
        if i + 1 >= len(argv):
            sys.exit(__doc__)
        out = argv[i + 1]; del argv[i:i + 2]
    flags = [a for a in argv if a.startswith('--')]
    pos = [a for a in argv if not a.startswith('-')]
    if len(pos) != 2 or len(flags) + len(pos) != len(argv) or set(flags) - {'--pc-colours', '--keep-work'}:
        sys.exit(__doc__)
    try:
        import numpy, xxhash, PIL                                           # noqa: F401
    except ImportError as e:
        sys.exit('%s: run  pip install -r requirements.txt' % e)
    import disc, hdfaces, hdunits, hdmaps, hdbacks
    pc, ps1 = pos
    out = os.path.abspath(out)
    for p, what in ((pc, 'PC disc'), (ps1, 'PlayStation track 1')):
        if not os.path.exists(p):
            sys.exit('%s not found: %s' % (what, p))
    if not os.path.isfile(ps1):
        sys.exit('PlayStation track 1 must be a disc image file: %s' % ps1)
    keep = '--keep-work' in flags
    work = os.path.join(HERE, 'work') if keep else tempfile.mkdtemp(prefix='hdpack_')
    try:
        pcdir, psdir = os.path.join(work, 'pc'), os.path.join(work, 'ps1')
        os.makedirs(pcdir, exist_ok=True)
        try:
            got = (pc_from_dir if os.path.isdir(pc) else pc_from_image)(pc, pcdir)
            d = disc.Disc(ps1)
            files = d.files()
        except ValueError as e:
            sys.exit(str(e))
        missing = sorted(set(PC_FILES) - got - PC_OPTIONAL)
        if missing:
            sys.exit('PC disc: %d files missing (%s%s)\n(is this the Windows 95 Sangokushi Koumeiden disc?)' % (
                len(missing), ', '.join(missing[:4]), ' ...' if len(missing) > 4 else ''))
        for rel in PS1_FILES:
            if rel not in files:
                sys.exit('%s: %s not found (is this track 1 of Sangokushi Koumeiden, SLPS-00688?)' % (ps1, rel))
            dst = os.path.join(psdir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, 'wb').write(d.read(*files[rel]))
        os.makedirs(out, exist_ok=True)
        extra = [f for f in flags if f == '--pc-colours']
        jobs = [('portraits', hdfaces, [os.path.join(pcdir, 'KAO.E2'), os.path.join(pcdir, 'PALET.E2')], []),
                ('battle units', hdunits, [pcdir], []),
                ('battle maps', hdmaps, [pcdir], []),
                ('halls and towns', hdbacks, [pcdir], extra)]
        total = 0
        for label, mod, args, more in jobs:
            mod.PS1 = psdir
            gen = os.path.join(work, 'gen', mod.__name__)
            print('%s:' % label, end=' ', flush=True)
            mod.main(args + [gen] + more)
            for p in glob.glob(os.path.join(gen, 'texupload-*.png')):
                shutil.copyfile(p, os.path.join(out, os.path.basename(p))); total += 1
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)
    print('\n%d replacement textures in %s' % (total, out))
    if os.path.basename(out) != 'replacements':
        print('Copy them to textures/%s/replacements/ in DuckStation\'s data folder'
              ' (DuckStation menu: Tools > Open Data Directory...)' % GAME_ID)
    print('DuckStation: hardware renderer, texture cache and texture replacements on (see README.md).')


if __name__ == '__main__':
    main()
