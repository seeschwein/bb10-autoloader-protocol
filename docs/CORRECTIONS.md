# Corrections to earlier notes

The first README was written from a partial reading of the capture. These items were wrong or incomplete;
the full evidence is in [PROTOCOL.md](PROTOCOL.md).

| Earlier claim | Now |
|---|---|
| Frames begin with a u16 length followed by `0x1000`. | The u16 at offset 0 is a **stage** (0, 1 or 2) and the **length is at offset 2**. The "`0x1000` marker" came from misreading `00 00 10 00` (stage 0, length 16). The 22- and 18-byte examples (`16 00 00 10`, `12 00 00 10`) do not reproduce in the full capture. |
| Handshake bytes `... 05 ed 55 1f ...` are fixed. | That 4-byte field is a per-session nonce echoed by the device (`9a32e81a` in the second capture). A prototype that hardcodes it only matches one capture. Use `build_handshake(os.urandom(4))`. |
| One large RAM-loader payload, preceded by `30 00 80`. | Stage-1 `cmd 04` **memory writes**: 122 frames of 2048 bytes to `0x80200000`+, 245,468 bytes in total, each preceded by a 3-byte length notice (`00 08 00` in this capture). |
| `AB/AC/A5/AE/A8` are the control sequence before bulk traffic. | Two profiles. The Bootrom (profile A) uses only `A5`, `A8`, `A8`. `AB`, `AC` and `AE` occur only when the loader's own USB stack enumerates (profile B). |
| The phone re-enumerates between OS and radio stages. | Five enumerations: A, B, A, B, A. The loader is uploaded twice. |
| Command ID, chunk header and addressing of the OS transfer unknown. | Stage-2 write frame: tag `0xF7`, u64 index, 16,364 data bytes, CRC32 trailer. Ack: tag `0xDF`. Addressing is by chunk index, not byte offset. |
| 12-byte messages are acknowledgements/status. | Two different things: stage-2 acks (tag `0xDF`) and type-`13` counter messages. Their total (about 4 per chunk) does not yet reconcile with one of each per chunk; see PROTOCOL.md, open question 1. |
| `bb10_flash.py` can replay the handshake as captured. | Stage 0 `0f` carries a 64-byte blob and the handshake has a nonce; replaying a capture will fail. |
