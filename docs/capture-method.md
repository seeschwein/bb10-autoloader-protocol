# Capturing a successful Windows flash

## Goal

Capture the USB conversation used by a successful BlackBerry 10 autoloader flash so that a native macOS/Linux implementation can be developed.

## Requirements

- UTM or another virtual-machine hypervisor with USB passthrough
- Windows guest
- USBPcap
- Wireshark
- Known-good stock and patched BlackBerry 10 autoloaders
- BlackBerry 10 device

## Procedure

1. In the Windows guest, install Wireshark and USBPcap.
2. Reboot the Windows guest after installing USBPcap.
3. Start Wireshark as Administrator.
4. Select a USBPcap interface.
5. Enable capture for newly connected USB devices if available.
6. Start the capture.
7. Run the autoloader.
8. Wait until it says it is waiting for Bootrom mode.
9. Attach the powered-off BlackBerry through UTM’s USB menu.
10. Let the flash complete without interruption.
11. Stop and save the capture as `.pcapng`.

Capture the OS and radio autoloaders separately:

```text
os-flash.pcapng
radio-flash.pcapng
```

## Wireshark filters

Isolate the BlackBerry:

```text
usb.device_address == 1
```

Show only the Bootrom session:

```text
usb.device_address == 1 && frame.time_relative >= 78
```

Show commands:

```text
usb.device_address == 1 && frame.time_relative >= 78 && usb.endpoint_address == 0x02
```

Show responses:

```text
usb.device_address == 1 && frame.time_relative >= 78 && usb.endpoint_address == 0x82
```

Show bulk transfers:

```text
usb.device_address == 1 && frame.time_relative >= 78 && usb.transfer_type == 0x03
```

Exclude USB URB completion records:

```text
usb.device_address == 1 && frame.time_relative >= 78 && usb.data_len > 0
```

## Export commands

Export all meaningful Bootrom-phase bulk packets:

```bash
tshark -r flash.pcapng \
  -Y 'usb.device_address == 1 && frame.time_relative >= 78 && usb.transfer_type == 0x03 && usb.data_len > 0' \
  -T fields \
  -e frame.number \
  -e frame.time_relative \
  -e usb.endpoint_address \
  -e usb.data_len \
  -e usb.capdata \
  > bootrom-bulk.tsv
```

Separate small protocol messages from 16 KiB firmware chunks:

```bash
awk -F'\t' '$4 != 16384' bootrom-bulk.tsv > bootrom-small.tsv
awk -F'\t' '$4 == 16384' bootrom-bulk.tsv > bootrom-chunks.tsv
```

Export a sample of 12-byte acknowledgements:

```bash
tshark -r flash.pcapng \
  -Y 'usb.device_address == 1 && frame.time_relative >= 78 && usb.data_len == 12' \
  -T fields \
  -e frame.number \
  -e frame.time_relative \
  -e usb.endpoint_address \
  -e usb.capdata \
  > bootrom-acks.tsv
```

## Safety

- Use only captures from a flash that completed successfully.
- Do not interrupt the phone or virtual machine during a flash.
- Retain the original stock autoloader.
- Do not flash files intended for another BlackBerry model or firmware version.