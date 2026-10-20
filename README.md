# bb10-autoloader-protocol

Research notes, USB capture analysis, and an experimental libusb prototype for flashing BlackBerry 10 devices from macOS or Linux without Windows.

**Status: early research / experimental. Do not use this project to flash production firmware.**

## Goal

This repository documents a reverse-engineering effort to understand the USB protocol used by BlackBerry 10 autoloader utilities, with the long-term goal of implementing a native macOS/Linux Bootrom flasher.

It is intended for archival, interoperability, and device-recovery research. Flashing incorrect firmware can permanently disable a BlackBerry 10 device.

## Current findings

- Normal BlackBerry 10 USB mode uses RIM VID `0x0fca` and PID `0x8017`.
- The normal configuration includes CDC-NCM networking interfaces and a vendor-specific interface.
- After an autoloader is waiting for Bootrom mode, the phone re-enumerates as RIM VID `0x0fca`, PID `0x8001`.
- The Bootrom device exposes a vendor-specific interface with four bulk endpoints.
- The observed flasher uses bulk endpoint `0x02` for host-to-device commands/data and `0x82` for device-to-host responses.
- The observed maximum bulk packet size is 512 bytes.
- Vendor control requests observed before bulk traffic include `0xAB`, `0xAC`, `0xA5`, `0xAE`, and `0xA8`.
- The first bulk exchange is 16 bytes in each direction.
- The bulk messages appear to use a length-prefixed framing format beginning with a little-endian 16-bit message length followed by `0x1000`.
- The first host command uses sequence/command byte `0x01`; the device response uses `0x02`.
- A large binary payload containing ARM machine code is uploaded around 81.3 seconds; this is likely the RAM loader.
- OS firmware is subsequently transferred in 18,923 transfers of exactly 16,384 bytes.
- 77,198 twelve-byte messages were observed; these are likely acknowledgements or status responses.
- The phone re-enumerates between the OS and radio flashing stages.

## Protocol hypothesis

A likely framed bulk-message layout is:

```text
offset 0: u16 LE  message length
offset 2: u16 LE  protocol/version marker, observed as 0x1000
offset 4: u8      sequence or command ID
offset 5: u8      0xff
offset 6: payload
```

For example, the first 16-byte host command begins:

```text
00 00 10 00 01 ff 00 00 05 ed 55 1f 02 00 00 00
```

The device response begins:

```text
00 00 10 00 02 ff 01 00 05 ed 55 1f 02 00 00 00
```

This suggests:

```text
length = 0x0010
protocol/version = 0x1000
sequence = 0x01
marker = 0xff
```

Larger observed messages support this hypothesis: a 22-byte message begins `16 00 00 10`, and an 18-byte response begins `12 00 00 10`.

## RAM-loader upload

At approximately 81.32 seconds, the capture changes from short framed commands to a large binary payload containing ARM machine code.

The observed sequence is:

```text
host -> phone: 3-byte command, 30 00 80
host -> phone: large binary payload
phone -> host: 24-byte response
phone -> host: 18-byte response
```

This is provisionally identified as the RAM-loader upload. It does not appear to use the same 16-bit length header as the earlier short commands.

## OS transfer

The OS image is transferred in 16 KiB chunks:

```text
16,384 bytes = 16 KiB
```

The capture contains 18,923 such transfers. The likely repeating exchange is:

```text
small command -> 16 KiB data -> 12-byte response
```

or:

```text
16 KiB data -> 12-byte response
```

The exact command ID, chunk header, addressing scheme, and acknowledgement semantics remain unknown.

## Capture method

1. Run the BlackBerry 10 autoloader inside a Windows virtual machine.
2. Install USBPcap and Wireshark in the Windows guest.
3. Start a USBPcap/Wireshark capture before attaching the BlackBerry.
4. Run the autoloader and wait for it to wait for Bootrom mode.
5. Attach the powered-off BlackBerry through the virtual machine’s USB passthrough.
6. Capture the complete OS flash separately from the radio flash.
7. Export packets with payload bytes as `.pcapng`.

## Prototype

`prototype/bb10_flash.py` is a conservative reconnaissance tool. By default it only:

- Finds a USB device with VID `0x0fca` and PID `0x8001`.
- Prints its descriptors and endpoints.
- Optionally performs the observed vendor control-transfer sequence.
- Opens bulk endpoints `0x02` and `0x82`.
- Sends the observed 16-byte handshake.
- Logs the response.

It will not upload a RAM loader or firmware unless `--allow-flash` is explicitly supplied.

## Safety

- Always retain the original stock autoloader for your exact device and firmware version.
- Do not flash a patched autoloader built from a firmware version different from the one already installed.
- Do not interrupt a flash.
- A Windows virtual machine with USB passthrough remains the most reliable current route for completing a flash.
- This project is research documentation and an experimental prototype, not a supported flashing tool.

## License

MIT