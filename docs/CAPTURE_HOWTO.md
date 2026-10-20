# Capturing and analysing a flash

Nothing here talks to a phone except the capture step, and that only observes a flash the *vendor tool* performs.

## 1. Capture

1. Windows VM with USB passthrough (or a Linux host with `usbmon`). Install Wireshark with USBPcap.
2. Start the capture **before** plugging in the powered-off phone. Capture the whole run (OS + radio) in one file.
3. Run the autoloader of the exact firmware you intend to study. Keep the stock autoloader.
4. Save as `flash.pcapng`. Expect roughly 1 MB of capture per MB of firmware.

## 2. Export

```
analysis/tshark_extract.sh flash.pcapng 5 out      # 5 = USB bus id, optional
```

Produces `control.tsv`, `bulk_small.tsv`, `bulk_chunks.tsv` and a list of enumeration times.
Do not export the whole capture to a text file; the 16 KiB frames dominate and it grows to about 5x the pcapng.

## 3. Analyse

```
S=$(tail -n +2 out/sessions.txt | paste -sd, -)
python3 analysis/bb10_analyze.py hist   out/bulk_small.tsv  --sessions $S   # frame types, CRC checks
python3 analysis/bb10_analyze.py loader out/bulk_small.tsv  --sessions $S -o loader
python3 analysis/bb10_analyze.py chunks out/bulk_chunks.tsv --sessions $S --dump os_stream.bin
```

What good output looks like:

- `hist`: every stage-1 and stage-2 row says `crc_ok body_ok`. Any `BAD` is a framing assumption to revisit.
- `loader`: base `0x80200000`, size 245,468, `gaps 0`, and "all loader uploads are identical".
- `chunks`: `non-sequential 0`, `bad_crc_or_len 0`; payload bytes per session.

## 4. Check the stream against the package

1. Unpack the autoloader `.exe` (`7z x`, or `unar`).
2. For each `.signed` file: `sha256sum`, `ls -l`, `xxd -l 64`.
3. Find the start of `os_stream.bin` in the OS `.signed` file (`python3 -c "d=open(F,'rb').read(); print(d.find(open('os_stream.bin','rb').read(64)))"`).
   If it matches at offset 0 and runs to the end, the stage-2 data stream is the raw container.
4. Search the package for the first 64 bytes of the rebuilt loader. If found, a native tool can take the loader from
   the package. Also search for the 64-byte blob from stage-0 type `0f`.

## 5. Reverse the loader

Open `loader_sess0_80200000.bin` in Ghidra: ARM, 32-bit, little-endian, base `0x80200000`. The command
dispatcher gives the stage-1 and stage-2 command tables.

## 6. Before touching a device

```
python3 -m unittest discover -s tests -v
```

The unit tests rebuild captured frames byte-for-byte. The sequence for the prototype:

1. Enumerate only.
2. Enumerate, then control transfers (profile A), then stage 0 handshake with a fresh nonce, then read-only get-parameter
   commands (`05`/`06`) and the device-info exchange. Compare against the capture.
3. Anything that writes (`0f`, loader upload, stage 2) stays behind `--allow-flash` and should only be tried on a
   sacrificial device after steps 1-2 match the capture.

## What not to commit

Captures, `.signed` images, extracted loaders and device identifiers are device-specific and the images are
third-party software. Keep them out of the repo (see `.gitignore`). Share hashes and hex of short header fields instead.
