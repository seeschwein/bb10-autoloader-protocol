# BB10 Bootrom / loader / flasher USB protocol

Evidence level is marked on every claim:

- **[V]** verified programmatically against a full capture of a successful flash (patched, signed OS + radio).
  Frame layouts and CRCs below were checked on real frames; see `tests/test_frames.py`.
- **[H]** hypothesis. Plausible from the traffic, not proven.

Everything here describes what the Windows autoloader does on the wire. Nothing in this repo generates or
bypasses authorisation data; a native tool is expected to read what the autoloader package supplies.

## 1. Device modes [V]

| Mode | VID:PID | Notes |
|---|---|---|
| Normal BB10 | `0fca:8017` | CDC-NCM networking + vendor interface |
| Bootrom / loader | `0fca:8001` | vendor interface, bulk `0x02` OUT / `0x82` IN (also `0x01`/`0x81`, unused in the capture), 512-byte max packet |

## 2. Session structure [V]

One full autoloader run enumerates the phone as `0fca:8001` **five** times. There are two distinct
enumeration profiles:

| Time (s) | Profile | Role |
|---|---|---|
| 78.0 | A | Bootrom: stage 0 handshake, then RAM-loader upload (stage 1) |
| 98.8 | B | RAM loader's own USB stack: stage 2 flasher protocol (OS image) |
| 1172.6 | A | Bootrom again, loader uploaded a second time |
| 1191.8 | B | Stage 2 again (radio image, about 30 s) |
| 1227.9 | A | Bootrom, no loader upload, ends at 1230.2 s |

A `SET_CONFIGURATION(0)` precedes each re-enumeration (e.g. 93.5 s, 1187.1 s, 1221.2 s).

### Control transfers

Both profiles start with `GET_DESCRIPTOR` (device 18 B, config 9 B then 46 B), `GET_STATUS` (2 B), then:

| Profile | Vendor requests after the standard ones | Then |
|---|---|---|
| A (Bootrom) | `0xC0 / 165` (IN, wIndex 1, 2 B), `0xC0 / 168` (IN, 5 B), `0xC0 / 168` (IN, 11 B) | `SET_CONFIGURATION` |
| B (loader) | `0x40 / 171 = 0xAB` (OUT, 12 B), `0x40 / 172 = 0xAC` (OUT, wValue `0xBFBF`, no data), `0xC0 / 165`, `0xC0 / 174 = 0xAE` (IN, returns 0 B, probably stalls), `0xC0 / 168` ×2 | `SET_CONFIGURATION` |

> Correction: earlier notes listed `AB/AC/AE` as a pre-bulk sequence for the Bootrom. They only occur in
> profile B, i.e. after the loader is running. Not yet captured: the 12 data bytes of `AB`, and the replies
> to `165` / `168` (the export did not include data stages). **[H]** `AB`+`AC` open or reset the loader's
> bulk pipe, `AE` is a probe that is expected to fail.

## 3. Framing

All integers little-endian. Three framings share endpoints `0x02` / `0x82`; the first u16 is a **stage** field.

### Stage 0 - Bootrom [V]

```
00 00 | len u16 | type u8 | flag u8 | b6 u8 | seq u8 | payload
```

`len` is the whole frame. Host and device messages use different `type` values (request/response pairs):

| type | dir | Meaning |
|---|---|---|
| `01` / `02` | H / D | Hello. Payload = 4-byte nonce + `02 00 00 00`. **[V]** the device echoes the host nonce; it changes every session, so a captured handshake cannot be replayed. **[H]** the `2` is a protocol version. |
| `05` / `06` | H / D | Get-parameter. **[H]** request payload = `(size u16, id u16)`. Id 1 returns 20 bytes (looks like a hash or ID); id 2 (size `0x07d0`) returns a 1276-byte partition table. |
| `07` / `08` | H / D | Name exchange. **[V]** payload is the ASCII string `RIM-BootLoader`. |
| `0a` / `0e` | H / D | Device-information request / reply (device identity). |
| `0f` / `10` | H / D | 76-byte request carrying a 64-byte blob after a 4-byte prefix. **[H]** authorisation data for the loader. **Open:** whether it is derived from a device challenge or a constant read from the autoloader package. |
| `13` | D | 12-byte counter message: `00 00 0c 00 13 <stage> 00 00 <counter u32>`. `flag` is `01` while stage 1 is active and `02` in stage 2 **[H: stage number]**. The counter increments per device reply. |

The partition table in the `06` reply (and again in stage 1 `cmd 01`) contains the ASCII names `nvram`,
`cal_work`, `cal_backup`, `dmi`, `dmi_mbr`, `dmi_sig`, `dmi_fsys`, `os`, `os_mbr`, `os_sig`, `system`,
`os_fsys`, `radio`, `radio_mbr`, `radio_sig`, `radio_fsys`, `user` **[V]**, plus a build string
(`RIM BlackBerry Device ... Jul 8 2014`).

### Stage 1 - RAM loader [V]

```
01 00 | len u16 | crc32 u32 | body_len u32 | seq u16 | cmd u8 | dir u8 | payload
crc32    = zlib.crc32(frame[8:])        # verified on every stage-1 frame in the capture
body_len = len - 4
dir      = 0xF0 host request, 0xFF device response
```

A 6-byte frame `01 00 06 00 06 06` switches the Bootrom to stage-1 framing (no CRC, no body). It is
sent twice before the first real command.

| cmd | Observed |
|---|---|
| `01` | Request with no payload; the reply (1296-byte body) repeats the partition table. |
| `0b` | Small setup request/response. |
| `09` | **[V]** payload `addr u32, size u32` = `0x80200000`, `0x0003BEDC` (245,468 bytes): sets up the upload. |
| `0d` | Setup request; **[H]** the reply carries `0x000007FC` (2044), the body size used for the data blocks. |
| `04` | **[V]** write memory: payload `addr u32, len u32, data`. 2048-byte frames = 24-byte header + 2024 bytes; address advances by `0x7E8` per block. 122 blocks (121 full + one of 564 bytes). The data starts `02 00 00 ea` (ARM `b`). |
| `0a`, `05` | After the last block. **[H]** verify and jump/execute. |

Each `04` block is preceded by a 3-byte message `00 08 00` (**[H]** length announcement `0x0800`) and answered by
a 24-byte stage-1 response plus a 12-byte type-`13` counter. One block every ~100 ms, about 12 s per upload.
The loader is uploaded **twice** per run (once for the OS stage, once for the radio stage); 242 full blocks
plus two short ones in the capture.

The loader contains strings such as `OS not found or invalid OS present`, `Boot count exceeded!!!`,
`Branding Erase error`, `HALT: err=%d, fileId=%d, line=%d`. Load it as 32-bit ARM LE at `0x80200000`.

### Stage 2 - flasher [V]

```
02 00 | len u16 | body_len u16 | tag u16 | payload | crc32 u32
body_len = len - 4
crc32    = zlib.crc32(frame[4:-4])      # verified on 11 frames of different sizes
```

| Frame | Tag | Layout |
|---|---|---|
| Data write (host) | `0x00F7` | 16,384-byte frame: `02 00 00 40 fc 3f f7 00`, u64 chunk **index** (0, 1, 2...), 16,364 bytes of data, CRC. |
| Ack (device) | `0x00DF` | Constant 12 bytes `02 00 0c 00 08 00 df 00 23 2e 50 e2` for every data write. |
| Read reply (device) | `0x00C8` | 16,380-byte frames returned for several different request tags. |
| Other commands | various | Request tags such as `b0, b4, b2, bd, bf, cb, d3, d8, d9, de, e1, e9, ee` and a request carrying `00000000 <crc> <crc>`. **Mapping unknown.** |

The first data chunk begins with ASCII `mfcq`, followed by `pfcq` records, and later blocks look like QNX6 inodes
**[H]**, so the host streams the autoloader's `.signed` container (not a different encoding). This is checked
with `bb10_analyze.py chunks --dump` by comparing the concatenated payloads against the extracted files.

## 4. Open questions

1. **Ack count.** The capture has about 38.3k stage-2 acks and 38.5k type-`13` counters, roughly 4 twelve-byte
   device messages per 16 KiB chunk across 18,923 chunks, but in a sample of session B every chunk gets exactly
   one ack and one counter. Either there are more host writes than the chunk export holds, or something is
   duplicated. Run `bb10_analyze.py hist` with `--sessions`.
2. **The 64-byte `0f` blob**: per-session or constant? Search the autoloader package for it. Capture a second
   run of the same autoloader and diff.
3. **The 12 data bytes of `AB`**, and replies to `165` / `168`: re-export with data stages.
4. **Stage 2 command tags**: disassemble the loader and find its dispatch table.
5. **Radio stage**: whether it uses the same tags and index scheme (the chunk header suggests yes).
6. **The final bootrom session at 1227.9 s**: what it does (probably a reboot or exit command).
