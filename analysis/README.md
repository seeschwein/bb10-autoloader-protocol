# Analysis status

## Confirmed

- Normal BlackBerry 10 USB mode uses VID `0x0fca` and PID `0x8017`.
- Bootrom mode uses VID `0x0fca` and PID `0x8001`.
- Bootrom mode exposes four bulk endpoints.
- The observed flasher uses endpoint `0x02` for commands/data and endpoint `0x82` for responses.
- The first framed bulk exchange is 16 bytes in each direction.
- A 16-bit little-endian length field followed by `0x1000` appears at the beginning of framed messages.
- The first host command sequence byte is `0x01`; the first device response sequence byte is `0x02`.
- A large ARM-code payload is uploaded at approximately 81.32 seconds and is provisionally identified as the RAM loader.
- OS firmware is transferred in 16 KiB chunks.
- 18,923 16,384-byte transfers were observed.
- 77,198 12-byte messages were observed and are provisionally interpreted as acknowledgements or status responses.
- The phone re-enumerates between OS and radio flashing stages.

## Unknown

- Exact meaning of every vendor control request.
- Full command/response state machine.
- Meaning of every bulk command ID.
- Whether the 16 KiB chunks are raw QCFM data or wrapped in an additional protocol layer.
- Whether each chunk has a sequence number, CRC, hash, or signature.
- The addressing or partition-selection scheme.
- The command that commits, verifies, or reboots the device.
- Whether radio flashing reuses the OS command IDs.

## Next research steps

1. Export the complete Bootrom-phase bulk stream.
2. Separate 16 KiB data chunks from small command/status messages.
3. Identify the repeating command immediately before each 16 KiB chunk.
4. Compare several chunk boundaries to determine sequence numbering and acknowledgement fields.
5. Correlate bulk messages with `cap.exe` and autoloader behavior in Ghidra.
6. Build a conservative libusb prototype that performs enumeration, control setup, handshake, and response logging.
7. Only after the handshake and RAM-loader upload are understood should firmware streaming be attempted.