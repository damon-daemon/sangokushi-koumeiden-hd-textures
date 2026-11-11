import sys, struct, os
def decode(data, usize, dic):
    out = bytearray(); pos = 0; bit = 0
    n = len(data)
    def code():
        nonlocal pos, bit
        b = 0; l = 0
        while True:
            v = (data[pos] >> (7-bit)) & 1
            bit += 1
            if bit == 8: bit = 0; pos += 1
            b = (b << 1) | v; l += 1
            if not v: break
        b2 = 0
        for _ in range(l):
            v = (data[pos] >> (7-bit)) & 1
            bit += 1
            if bit == 8: bit = 0; pos += 1
            b2 = (b2 << 1) | v
        return b + b2
    while len(out) < usize:
        c = code()
        if c < 256: out.append(dic[c])
        else:
            off = c - 256; ln = code() + 3
            for _ in range(ln): out.append(out[-off])
    return bytes(out[:usize])
def entries(d):
    assert d[:4] == b'LS11'
    dic = d[16:272]; p = 272; ents = []
    while True:
        c, u, o = struct.unpack('>III', d[p:p+12])
        if c == 0: break
        ents.append((c, u, o)); p += 12
    return dic, ents
if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    dic, ents = entries(d)
    print(os.path.basename(sys.argv[1]), len(ents), 'entries; sizes', sorted(set(u for c,u,o in ents))[:12], 'total', sum(u for c,u,o in ents))
    if len(sys.argv) > 2:
        os.makedirs(sys.argv[2], exist_ok=True)
        for i, (c, u, o) in enumerate(ents):
            raw = d[o:o+c]
            open(os.path.join(sys.argv[2], '%04d.bin' % i), 'wb').write(raw if c == u else decode(raw, u, dic))
