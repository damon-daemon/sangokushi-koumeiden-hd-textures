"""Read files from an ISO9660 disc image: raw 2352-byte sectors (Mode 1 or Mode 2) or plain 2048-byte sectors."""
import struct

SYNC = b'\0' + b'\xff' * 10 + b'\0'


class Disc:
    def __init__(self, path):
        self.path, self.f = path, open(path, 'rb')
        head = self.f.read(16)
        self.raw, self.skip = (2352, 24 if head[15] == 2 else 16) if head[:12] == SYNC else (2048, 0)

    def read(self, lba, size):
        out = bytearray()
        for i in range((size + 2047) // 2048):
            self.f.seek((lba + i) * self.raw + self.skip); out += self.f.read(2048)
        return bytes(out[:size])

    def files(self):
        """{'DIR/NAME.EXT': (lba, size)} for every file, names upper case."""
        pvd = self.read(16, 2048)
        if pvd[1:6] != b'CD001':
            raise ValueError('%s: no ISO9660 file system found (not a disc image?)' % self.path)
        lba, size = struct.unpack_from('<I4xI', pvd, 156 + 2)
        out = {}
        self._dir(lba, size, '', out)
        return out

    def _dir(self, lba, size, prefix, out):
        d, o = self.read(lba, size), 0
        while o < len(d):
            n = d[o]
            if n == 0:
                o = (o // 2048 + 1) * 2048; continue
            l, s = struct.unpack_from('<I4xI', d, o + 2)
            name = d[o + 33:o + 33 + d[o + 32]]
            if name not in (b'\0', b'\1'):
                name = prefix + name.decode('ascii', 'replace').split(';')[0].upper()
                if d[o + 25] & 2:
                    self._dir(l, s, name + '/', out)
                else:
                    out[name] = (l, s)
            o += n
