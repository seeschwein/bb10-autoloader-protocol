#!/usr/bin/env python3
"""
bb10_analyze.py - offline analysis of BB10 bootrom/flasher USB captures exported as TSV
(columns: frame, time, endpoint, length, hex-payload). Touches no USB device.

  hist   small.tsv [--sessions T1,T2,...]      per-session frame-type histogram + CRC validation
  loader small.tsv --sessions ... [-o PREFIX]  rebuild RAM-loader image(s) from stage-1 cmd 04 writes
  chunks chunks.tsv [--sessions ...] [--dump FILE]
                                               validate 16 KiB stage-2 write frames, check index
                                               continuity, optionally concatenate payloads

Framing (verified against your capture):
  stage 0: 00 00 | len u16 | type u8 | flag u8 | seq u16 | payload
  stage 1: 01 00 | len u16 | crc32 u32 | body_len u32 | seq u16 | cmd u8 | dir u8 | payload
           crc32 = zlib.crc32(frame[8:]) ; body_len = len-4 ; dir f0=request ff=response
  stage 2: 02 00 | len u16 | body_len u16 | tag u16 | payload | crc32 u32 (trailer)
           body_len = len-4 ; crc32 = zlib.crc32(frame[4:-4])
"""
import sys, struct, zlib, argparse, hashlib, collections, bisect

def rows(path):
    with open(path) as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 5: continue
            try:
                yield int(p[0]), float(p[1]), p[2], int(p[3]), bytes.fromhex(p[4])
            except ValueError:
                continue   # truncated / non-hex line

def session_of(t, bounds):
    return bisect.bisect_right(bounds, t)

def decode(b):
    n = len(b)
    if n < 6: return ("short", "", "")
    stage = struct.unpack_from("<H", b, 0)[0]
    ln = struct.unpack_from("<H", b, 2)[0]
    if stage == 0 and ln == n and n >= 8:
        return ("s0", f"type={b[4]:02x} flag={b[5]:02x}", "len_ok")
    if stage == 1 and ln == n and n >= 16:
        crc = struct.unpack_from("<I", b, 4)[0] == zlib.crc32(b[8:]) & 0xffffffff
        bl = struct.unpack_from("<I", b, 8)[0] == n - 4
        return ("s1", f"cmd={b[14]:02x} dir={b[15]:02x}", f"crc_{'ok' if crc else 'BAD'} body_{'ok' if bl else 'BAD'}")
    if stage == 2 and ln == n and n >= 12:
        crc = struct.unpack_from("<I", b, n-4)[0] == zlib.crc32(b[4:n-4]) & 0xffffffff
        bl = struct.unpack_from("<H", b, 4)[0] == n - 4
        return ("s2", f"tag={struct.unpack_from('<H', b, 6)[0]:04x}", f"crc_{'ok' if crc else 'BAD'} body_{'ok' if bl else 'BAD'}")
    return ("other", "", "")

def cmd_hist(a):
    bounds = [float(x) for x in a.sessions.split(",")] if a.sessions else []
    hist = collections.Counter()
    for fr, t, ep, ln, b in rows(a.file):
        k, d, c = decode(b)
        size = ln if ln in (12, 16384, 16380, 2048) else ("<=64" if ln <= 64 else ">64")
        hist[(session_of(t, bounds), ep, k, d, c, size)] += 1
    for k, v in sorted(hist.items(), key=lambda kv: (kv[0][0], -kv[1])):
        print(f"{v:8d}  sess{k[0]}  " + "  ".join(map(str, k[1:])))

def cmd_loader(a):
    bounds = [float(x) for x in a.sessions.split(",")] if a.sessions else []
    blocks = collections.defaultdict(list)
    for fr, t, ep, ln, b in rows(a.file):
        if ep != "0x02" or len(b) < 24: continue
        if b[:2] == b"\x01\x00" and b[14] == 0x04 and b[15] == 0xf0 and struct.unpack_from("<H", b, 2)[0] == len(b):
            if struct.unpack_from("<I", b, 4)[0] != zlib.crc32(b[8:]) & 0xffffffff:
                print(f"frame {fr}: CRC mismatch, skipped", file=sys.stderr); continue
            addr, dlen = struct.unpack_from("<II", b, 16)
            data = b[24:24+dlen]
            if len(data) != dlen:
                print(f"frame {fr}: data length {len(data)} != {dlen}", file=sys.stderr); continue
            blocks[session_of(t, bounds)].append((fr, addr, data))
    hashes = {}
    for s, bl in sorted(blocks.items()):
        base = min(x[1] for x in bl); end = max(x[1] + len(x[2]) for x in bl)
        img = bytearray(end - base); expect = base; gaps = 0
        for fr, addr, data in bl:
            if addr != expect: gaps += 1; print(f"sess{s}: non-contiguous at frame {fr} (got {addr:#x}, expected {expect:#x})", file=sys.stderr)
            img[addr-base:addr-base+len(data)] = data; expect = addr + len(data)
        h = hashlib.sha256(img).hexdigest(); hashes[s] = h
        out = f"{a.o}_sess{s}_{base:08x}.bin"
        open(out, "wb").write(img)
        print(f"sess{s}: {len(bl)} blocks, base {base:#x}, size {len(img)}, gaps {gaps}, sha256 {h}  -> {out}")
    if len(set(hashes.values())) == 1 and len(hashes) > 1: print("all loader uploads are identical")

def cmd_chunks(a):
    bounds = [float(x) for x in a.sessions.split(",")] if a.sessions else []
    out = open(a.dump, "wb") if a.dump else None
    st = collections.defaultdict(lambda: dict(n=0, bad=0, nonseq=0, last=None, first=None, bytes=0))
    for fr, t, ep, ln, b in rows(a.file):
        if ep != "0x02" or len(b) < 24 or b[:2] != b"\x02\x00": continue
        s = st[session_of(t, bounds)]
        k, d, c = decode(b)
        s["n"] += 1
        if "BAD" in c: s["bad"] += 1
        idx = struct.unpack_from("<Q", b, 8)[0]
        if s["last"] is not None and idx != s["last"] + 1: s["nonseq"] += 1
        if s["first"] is None: s["first"] = idx
        s["last"] = idx; s["bytes"] += len(b) - 20
        if out: out.write(b[16:-4])
    for k, s in sorted(st.items()):
        print(f"sess{k}: frames {s['n']}, bad_crc_or_len {s['bad']}, index {s['first']}..{s['last']}, "
              f"non-sequential {s['nonseq']}, payload bytes {s['bytes']}")
    if out: out.close(); print(f"payloads (frame[16:-4]) written to {a.dump}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="c", required=True)
    for name, fn in (("hist", cmd_hist), ("loader", cmd_loader), ("chunks", cmd_chunks)):
        p = sp.add_parser(name); p.add_argument("file"); p.add_argument("--sessions", default="")
        if name == "loader": p.add_argument("-o", default="loader")
        if name == "chunks": p.add_argument("--dump")
        p.set_defaults(fn=fn)
    a = ap.parse_args(); a.fn(a)
