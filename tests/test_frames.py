"""Run: python3 -m unittest discover -s tests -v   (from the repo root). Needs no hardware."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "prototype"))
import bb10_frames as F

H = bytes.fromhex

class CapturedFrames(unittest.TestCase):
    def test_handshake_roundtrip(self):
        host = H("0000100001ff00009a32e81a02000000")
        self.assertEqual(F.build_handshake(H("9a32e81a")), host)
        p = F.parse_s0(host)
        self.assertEqual((p["type"], p["flag"], p["seq"]), (1, 0xFF, 0))
        self.assertEqual(F.parse_s0(H("0000100002ff00009a32e81a02000000"))["type"], 2)

    def test_stage0_get_param(self):
        f = H("00000c0005ff000114000100")
        p = F.parse_s0(f)
        self.assertEqual((p["type"], p["seq"], p["payload"]), (5, 1, H("14000100")))
        self.assertEqual(F.build_s0(5, 0xFF, 1, H("14000100")), f)

    def test_stage1_crc_vectors(self):
        for h in ("010010007b092b960c000000000001f0",
                  "010018006f5d179014000000ffff00ff0600000000000080",
                  "01001000948678d40c00000001000bf0",
                  "01001c00b2d5adf01800000001000bff060000000000008000000000"):
            f = H(h)
            p = F.parse_s1(f)                      # raises on CRC/length error
            self.assertEqual(F.build_s1(p["seq"], p["cmd"], p["dir"], p["payload"]), f)

    def test_stage1_write_memory_header(self):
        f = F.build_s1_write_memory(4, 0x80200000, b"\x02\x00\x00\xea" * 506)  # 2024 bytes
        self.assertEqual(len(f), 2048)
        self.assertEqual(f[:4], H("01000008"))
        self.assertEqual(f[12:20], H("040004f0") + H("00002080")[:4])  # seq=4, cmd=04, dir=f0, addr lo
        self.assertEqual(F.parse_s1(f)["payload"][:8], H("00002080e8070000"))

    def test_stage2_vectors(self):
        for h in ("020014001000b0000000000000000000aaa03bf9",
                  "02000c000800b4004f9c5964",
                  "02000c000800df00232e50e2",
                  "020018001400fa0000000000000000000000000070bf8665",
                  "02002800240031004d524d430200000001000000000000004d4f44454d00000000000000f4684d8d"):
            f = H(h)
            p = F.parse_s2(f)
            self.assertEqual(F.build_s2(p["tag"], p["payload"]), f)
        self.assertEqual(F.parse_s2(H("02000c000800df00232e50e2"))["tag"], F.S2_TAG_WRITE_ACK)

    def test_stage2_chunk_geometry(self):
        f = F.build_s2_chunk(7, b"\xff" * F.S2_CHUNK_DATA)
        self.assertEqual(len(f), 16384)
        self.assertEqual(f[:8], H("02000040fc3ff700"))
        self.assertEqual(f[8:16], H("0700000000000000"))
        self.assertEqual(F.parse_s2(f)["tag"], F.S2_TAG_WRITE_CHUNK)

    def test_bad_crc_rejected(self):
        bad = bytearray(H("02000c000800df00232e50e2")); bad[-1] ^= 1
        with self.assertRaises(F.FrameError): F.parse_s2(bytes(bad))

if __name__ == "__main__":
    unittest.main()
