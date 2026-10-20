"""
bb10_frames.py - pure-Python framing for the BB10 Bootrom / RAM-loader USB protocol.

No USB access happens here. This module only builds and parses byte strings, so it can be
unit-tested against captured frames (see tests/test_frames.py) before anything touches a device.

Three framings share the same bulk endpoints (0x02 OUT / 0x82 IN):

  stage 0  Bootrom     00 00 | len | type u8 | flag u8 | b6 u8 | seq u8 | payload
  stage 1  RAM loader  01 00 | len | crc32 | body_len u32 | seq u16 | cmd u8 | dir u8 | payload
  stage 2  Flasher     02 00 | len | body_len u16 | tag u16 | payload | crc32 (trailer)

All integers are little-endian. See docs/PROTOCOL.md for what is verified and what is guessed.
"""
import struct
import zlib

DIR_REQUEST = 0xF0   # stage 1: host -> device
DIR_RESPONSE = 0xFF  # stage 1: device -> host


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


class FrameError(ValueError):
    pass


# ---------------------------------------------------------------- stage 0 (Bootrom)
def build_s0(ftype: int, flag: int, seq: int, payload: bytes = b"", b6: int = 0) -> bytes:
    n = 8 + len(payload)
    return b"\x00\x00" + struct.pack("<HBBBB", n, ftype, flag, b6, seq) + payload


def parse_s0(frame: bytes) -> dict:
    if len(frame) < 8 or frame[:2] != b"\x00\x00":
        raise FrameError("not a stage-0 frame")
    n, ftype, flag, b6, seq = struct.unpack_from("<HBBBB", frame, 2)
    if n != len(frame):
        raise FrameError(f"length field {n} != frame size {len(frame)}")
    return dict(type=ftype, flag=flag, b6=b6, seq=seq, payload=frame[8:])


def build_handshake(nonce: bytes, version: int = 2) -> bytes:
    """First host frame. The device echoes the nonce back (type 0x02); it differs every session."""
    if len(nonce) != 4:
        raise ValueError("nonce must be 4 bytes")
    return build_s0(0x01, 0xFF, 0, nonce + struct.pack("<I", version))


# ---------------------------------------------------------------- stage 1 (RAM loader)
def build_s1(seq: int, cmd: int, direction: int, payload: bytes = b"") -> bytes:
    total = 16 + len(payload)
    body = struct.pack("<IHBB", total - 4, seq, cmd, direction) + payload
    return b"\x01\x00" + struct.pack("<HI", total, crc32(body)) + body


def parse_s1(frame: bytes) -> dict:
    if len(frame) < 16 or frame[:2] != b"\x01\x00":
        raise FrameError("not a stage-1 frame")
    total, crc = struct.unpack_from("<HI", frame, 2)
    if total != len(frame):
        raise FrameError(f"length field {total} != frame size {len(frame)}")
    if crc != crc32(frame[8:]):
        raise FrameError("stage-1 CRC mismatch")
    body_len, seq, cmd, direction = struct.unpack_from("<IHBB", frame, 8)
    if body_len != total - 4:
        raise FrameError("stage-1 body_len mismatch")
    return dict(seq=seq, cmd=cmd, dir=direction, payload=frame[16:])


def build_s1_write_memory(seq: int, addr: int, data: bytes) -> bytes:
    """cmd 0x04: write `data` to RAM at `addr` (observed: 2024-byte blocks into 0x80200000+)."""
    return build_s1(seq, 0x04, DIR_REQUEST, struct.pack("<II", addr, len(data)) + data)


# ---------------------------------------------------------------- stage 2 (flasher)
def build_s2(tag: int, payload: bytes = b"") -> bytes:
    n = 12 + len(payload)
    head = struct.pack("<HHHH", 2, n, n - 4, tag)
    return head + payload + struct.pack("<I", crc32((head + payload)[4:]))


def parse_s2(frame: bytes) -> dict:
    if len(frame) < 12 or frame[:2] != b"\x02\x00":
        raise FrameError("not a stage-2 frame")
    n, body_len, tag = struct.unpack_from("<HHH", frame, 2)
    if n != len(frame):
        raise FrameError(f"length field {n} != frame size {len(frame)}")
    if body_len != n - 4:
        raise FrameError("stage-2 body_len mismatch")
    if struct.unpack_from("<I", frame, n - 4)[0] != crc32(frame[4:n - 4]):
        raise FrameError("stage-2 CRC mismatch")
    return dict(tag=tag, payload=frame[8:n - 4])


S2_TAG_WRITE_CHUNK = 0x00F7  # observed for every 16 KiB data frame
S2_TAG_WRITE_ACK = 0x00DF    # device's constant 12-byte reply to a chunk write
S2_CHUNK_FRAME = 16384
S2_CHUNK_DATA = S2_CHUNK_FRAME - 8 - 8 - 4  # header + u64 index + crc = 20 bytes -> 16364


def build_s2_chunk(index: int, data: bytes) -> bytes:
    if len(data) > S2_CHUNK_DATA:
        raise ValueError("chunk data too large")
    return build_s2(S2_TAG_WRITE_CHUNK, struct.pack("<Q", index) + data)
