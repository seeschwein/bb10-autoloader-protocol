#!/usr/bin/env python3
"""Experimental BlackBerry 10 Bootrom protocol reconnaissance tool.

This script is for research and interoperability testing. It does not flash
firmware by default.

Default behaviour:
- Find a USB device with VID 0x0fca and PID 0x8001.
- Print descriptors and endpoints.
- Optionally perform the observed vendor control-transfer sequence.
- Optionally open bulk endpoints 0x02 and 0x82.
- Optionally send the observed 16-byte handshake and print the response.

Firmware flashing requires --allow-flash and is not implemented.
"""

import argparse
import sys
import usb.core
import usb.util

RIM_VID = 0x0FCA
BOOTROM_PID = 0x8001
COMMAND_EP = 0x02
RESPONSE_EP = 0x82

HANDSHAKE = bytes.fromhex(
    "0000100001ff000005ed551f02000000"
)


def find_bootrom():
    device = usb.core.find(idVendor=RIM_VID, idProduct=BOOTROM_PID)
    if device is None:
        raise SystemExit(
            "No BlackBerry Bootrom device found. "
            "Expected VID 0x0fca / PID 0x8001."
        )
    return device


def describe(device):
    print("Found BlackBerry Bootrom device")
    print(f"  VID: 0x{device.idVendor:04x}")
    print(f"  PID: 0x{device.idProduct:04x}")
    print(f"  Bus: {device.bus}")
    print(f"  Address: {device.address}")
    print(f"  Configurations: {device.bNumConfigurations}")

    for configuration in device:
        print(f"  Configuration {configuration.bConfigurationValue}")
        for interface in configuration:
            print(
                f"    Interface {interface.bInterfaceNumber}, "
                f"class 0x{interface.bInterfaceClass:02x}"
            )
            for endpoint in interface:
                print(
                    f"      Endpoint 0x{endpoint.bEndpointAddress:02x}, "
                    f"attributes 0x{endpoint.bmAttributes:02x}, "
                    f"max packet {endpoint.wMaxPacketSize}"
                )


def control_sequence(device):
    """Replay the observed vendor control-transfer sequence."""
    requests = [
        # bmRequestType, bRequest, wValue, wIndex, data
        (0x40, 0xAB, 0x0000, 0x0000,
         bytes.fromhex("5e040100644a000a23000204")),
        (0x40, 0xAC, 0xBFBF, 0x0000, b""),
        (0xC0, 0xA5, 0x0000, 0x0001, b""),
        (0xC0, 0xAE, 0x0000, 0x0001, b""),
        (0xC0, 0xA8, 0x0000, 0x0001, b""),
        (0xC0, 0xA8, 0x0000, 0x0001, b""),
    ]

    for index, (request_type, request, value, interface, payload) in enumerate(
        requests, start=1
    ):
        try:
            response = device.ctrl_transfer(
                request_type=request_type,
                request=request,
                value=value,
                index=interface,
                data_or_wLength=payload if payload else 0,
                timeout=2000,
            )
            print(
                f"Control request {index}: 0x{request:02x} -> "
                f"{response.hex() if isinstance(response, bytes) else response}"
            )
        except usb.core.USBError as error:
            print(
                f"Control request {index}: 0x{request:02x} -> "
                f"USB error: {error}"
            )


def bulk_handshake(device):
    """Send the observed 16-byte handshake and read one response."""
    device.write(COMMAND_EP, HANDSHAKE, timeout=5000)
    print("Sent 16-byte handshake on endpoint 0x02")

    response = device.read(RESPONSE_EP, 512, timeout=5000)
    response = bytes(response)
    print(f"Received {len(response)} bytes on endpoint 0x82:")
    print(response.hex())


def main():
    parser = argparse.ArgumentParser(
        description="BlackBerry 10 Bootrom protocol reconnaissance"
    )
    parser.add_argument(
        "--control",
        action="store_true",
        help="Replay the observed vendor control-transfer sequence",
    )
    parser.add_argument(
        "--handshake",
        action="store_true",
        help="Send the observed 16-byte bulk handshake",
    )
    parser.add_argument(
        "--allow-flash",
        action="store_true",
        help="Acknowledge awareness that flashing can permanently disable a device",
    )
    args = parser.parse_args()

    device = find_bootrom()
    describe(device)

    if args.control:
        control_sequence(device)

    if args.handshake:
        if not args.allow_flash:
            parser.error(
                "--handshake requires --allow-flash because it changes device state."
            )
        bulk_handshake(device)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)