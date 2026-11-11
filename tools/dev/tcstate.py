"""python tools/dev/tcstate.py STATE.sav... [-a] (Python 3.14: compression.zstd): VRAM uploads DuckStation tracks in a hardware-renderer save state (texture cache
section): active rect, write rect, XXH3 hash, palette records (rect, source key page/mode/CLUT, palette hash; only
filled when the state was saved with DumpTextures on). Without -a only uploads in the battle texture area.
A map part with no palette record for its page = drawn outside the texture cache = no replacement."""
import struct, sys
from compression import zstd
def load(path):
    d = open(path, 'rb').read()
    i = d.find(b'\x28\xb5\x2f\xfd')
    while i >= 0:
        try:
            u = zstd.ZstdDecompressor().decompress(d[i:])
            if b'GPUTextureCache' in u: return u
        except zstd.ZstdError: pass
        i = d.find(b'\x28\xb5\x2f\xfd', i + 1)
for path in [a for a in sys.argv[1:] if a != '-a']:
    u = load(path); j = u.index(b'GPUTextureCache') + 15
    n, last = struct.unpack_from('<II', u, j); j += 8
    print(path, 'writes', n)
    for k in range(n):
        ar = struct.unpack_from('<4i', u, j); wr = struct.unpack_from('<4i', u, j + 16)
        h, sp, npr = struct.unpack_from('<QII', u, j + 32); j += 48
        recs = []
        for r in range(npr):
            rc = struct.unpack_from('<4i', u, j); key = u[j+16:j+20].hex(); fl = struct.unpack_from('<I', u, j+20)[0]; ph = struct.unpack_from('<Q', u, j+24)[0]
            recs.append((rc, key, '%016X' % ph)); j += 16 + 4 + 4 + 8 + 512
        if wr[2] > 800 and wr[3] > 256 and wr[1] < 448 or '-a' in sys.argv:
            print(' active', ar, 'write', wr, '%016X' % h, 'splits', sp, recs)
