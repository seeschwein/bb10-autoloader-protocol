# USB protocol notes

## Device modes

| Mode | VID | PID | Class | Notes |
|---|---:|---:|---|---|
| Normal BlackBerry 10 mode | `0x0fca` | `0x8017` | Miscellaneous / CDC-NCM | Network interfaces and vendor interface |
| Bootrom / Download mode | `0x0fca` | `0x8001` | Vendor Specific | Four bulk endpoints |

## Bootrom endpoints

| Endpoint | Direction | Type | Maximum packet size |
|---|---|---|---:|
| `0x01` | OUT | Bulk | 512 |
| `0x81` | IN | Bulk | 512 |
| `0x02` | OUT | Bulk | 512 |
| `0x82` | IN | Bulk | 512 |

The observed autoloader uses `0x02` as its command/data channel and `0x82` as its response channel.

## Vendor control requests

| bRequest | Decimal | Direction | Observed result |
|---:|---:|---|---|
| `0xAB` | 171 | Host-to-device | 12-byte payload; device stalls |
| `0xAC` | 172 | Host-to-device | `wValue = 0xbfbf`; likely clears stall |
| `0xA5` | 165 | Device-to-host | Returns `0x0020` |
| `0xAE` | 174 | Device-to-host | Stalls |
| `0xA8` | 168 | Device-to-host | Returns 5- or 11-byte capability/interface information |

## Framed bulk messages

The first bulk exchange is 16 bytes in each direction.

Host to device:

```text
00 00 10 00 01 ff 00 00 05 ed 55 1f 02 00 00 00
```

Device to host:

```text
00 00 10 00 02 ff 01 00 05 ed 55 1f 02 00 00 00
```

Hypothesis:

```text
u16 LE total message length
u16 LE protocol/version marker, observed 0x1000
u8 sequence/command ID
u8 marker, observed 0xff
payload
```

The first exchange appears to use:

```text
command sequence: 0x01
response sequence: 0x02
```

## Observed command IDs

| ID | Direction | Provisional interpretation |
|---:|---|---|
| `0x01` | Host-to-device | Initial handshake / open |
| `0x02` | Device-to-host | Handshake response |
| `0x05` | Host-to-device | Parameterised command |
| `0x06` | Device-to-host | Response |
| `0x07` | Host-to-device | Repeated query / parameter command |
| `0x08` | Device-to-host | Response |
| `0x0f` | Host-to-device | Larger signed/encrypted command |
| `0x10` | Device-to-host | Response |
| `0x11` | Host-to-device | Device-information request |
| `0x12` | Device-to-host | Device identity response |

## RAM-loader upload

At approximately 81.32 seconds, the capture changes from short framed commands to a large binary payload containing ARM machine code.

```text
host -> phone: 30 00 80
host -> phone: large ARM code payload
phone -> host: 24-byte response
phone -> host: 18-byte response
```

This is provisionally identified as the RAM-loader upload. Its framing differs from the earlier short messages.

## OS transfer

The OS image is transferred in 16 KiB chunks:

```text
16,384 bytes
```

A capture showed 18,923 such transfers. There were also 77,198 twelve-byte messages, provisionally interpreted as acknowledgements or status responses.

## Open questions

- What is the exact command ID preceding each 16 KiB chunk?
- Does the command contain a flash offset, partition identifier, sequence number, or hash?
- What fields are present in the 12-byte acknowledgement?
- Is the OS image sent as raw QCFM data or is it additionally wrapped by the bulk protocol?
- Which command triggers write, verify, commit, or reboot?
- Does the radio flash reuse the same command IDs after re-enumeration?