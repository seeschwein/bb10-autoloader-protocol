# bb10-autoloader-protocol

Research notes, USB capture analysis and an experimental libusb prototype for flashing BlackBerry 10 devices from
macOS or Linux without Windows.

**Status: research. The wire protocol is mostly decoded; the prototype does not flash anything. Do not use this
project to flash production firmware.**

## Goal

Document the USB protocol the BB10 autoloader uses to talk to a phone in Bootrom mode, for archival,
interoperability and device-recovery purposes, with the long-term aim of a native macOS/Linux flasher.
Flashing incorrect firmware can permanently disable a device. A Windows VM with USB passthrough running the
vendor autoloader remains the only supported way to flash.

## Where things stand

| Area | State |
|---|---|
| Device modes, VID/PIDs, endpoints | Verified |
| Session structure (5 enumerations, 2 profiles) | Verified |
| Framing for all three protocol stages incl. CRC32 | Verified against a full successful flash |
| RAM-loader upload (address, size, block layout) | Verified |
| Stage-2 data stream (tag, index, ack) | Verified; payload = `.signed` container to be confirmed against the package |
| Stage-2 command set, the `0f` authorisation blob, vendor control payloads | Open |

Details and evidence levels: [docs/PROTOCOL.md](docs/PROTOCOL.md).
What changed from the first version of these notes: [docs/CORRECTIONS.md](docs/CORRECTIONS.md).

## Summary of findings

- Normal mode is `0fca:8017` (CDC-NCM + vendor interface). Bootrom/loader mode is `0fca:8001`, a vendor interface with
  bulk `0x02` OUT / `0x82` IN, 512-byte packets.
- One run enumerates the phone as `8001` five times: Bootrom (A) -> loader (B) -> Bootrom (A) -> loader (B) -> Bootrom (A).
  A and B use different vendor control requests (`A5`/`A8` vs `AB`/`AC`/`A5`/`AE`/`A8`).
- Three frame formats share the bulk endpoints, selected by a leading u16 stage field:
  - stage 0 Bootrom: `00 00 | len | type | flag | b6 | seq | payload`
  - stage 1 RAM loader: `01 00 | len | crc32 | body_len | seq | cmd | dir | payload`, `crc32 = zlib.crc32(frame[8:])`
  - stage 2 flasher: `02 00 | len | body_len | tag | payload | crc32`, `crc32 = zlib.crc32(frame[4:-4])`
- The Bootrom handshake carries a per-session nonce echoed by the device. A 245,468-byte ARM loader is written to
  `0x80200000` in 122 blocks (cmd `04`), twice per run (OS stage, then radio stage).
- Stage 2 writes 16,384-byte frames (tag `0xF7`, u64 chunk index, 16,364 data bytes, CRC32) and gets a constant
  12-byte ack (tag `0xDF`). The first chunk starts with `mfcq`, matching the `.signed` container.

## Repository layout

```
docs/PROTOCOL.md         wire protocol, evidence levels, open questions
docs/CORRECTIONS.md      what earlier versions of these notes got wrong
docs/CAPTURE_HOWTO.md    step-by-step: capture, export, analyse, compare, reverse
analysis/tshark_extract.sh   pcapng -> TSV exports (control, small bulk, 16 KiB chunks, session times)
analysis/bb10_analyze.py     histogram + CRC validation, loader rebuild, chunk stream check
prototype/bb10_frames.py     pure-Python frame builders/parsers (no USB access)
prototype/bb10_flash.py      conservative reconnaissance tool (non-flashing by default)
tests/test_frames.py         unit tests built from real captured frames
```

## Quick start (analysing a capture)

```
analysis/tshark_extract.sh flash.pcapng 5 out
S=$(tail -n +2 out/sessions.txt | paste -sd, -)
python3 analysis/bb10_analyze.py hist   out/bulk_small.tsv  --sessions $S
python3 analysis/bb10_analyze.py loader out/bulk_small.tsv  --sessions $S -o loader
python3 analysis/bb10_analyze.py chunks out/bulk_chunks.tsv --sessions $S --dump os_stream.bin
python3 -m unittest discover -s tests -v
```

See [docs/CAPTURE_HOWTO.md](docs/CAPTURE_HOWTO.md) for what correct output looks like and how to compare the stream
with the files inside the autoloader.

## Prototype

`prototype/bb10_flash.py` finds `0fca:8001`, prints descriptors and endpoints, can perform the profile-A control
sequence, opens `0x02`/`0x82`, sends a handshake and logs the reply. It must be updated to use
`prototype/bb10_frames.py` and a **fresh random nonce** (`build_handshake(os.urandom(4))`) instead of a captured
handshake. It will not upload a loader or send firmware unless `--allow-flash` is given, and that path is not
implemented against the decoded protocol yet.

## Safety

- Keep the original stock autoloader for your exact device and firmware version.
- Do not flash a patched autoloader built from a different firmware version than the one installed.
- Do not interrupt a flash.
- Any write beyond the read-only exchanges stays behind `--allow-flash` and should be tried only on a sacrificial device.
- This project reads and reproduces what the vendor tool sends. It does not generate or forge authorisation data.

## What not to commit

Captures, `.signed` images, extracted loaders and device identifiers are device-specific and the images are
third-party software. They are in `.gitignore`. Share hashes and short header fields instead.

## License

MIT
