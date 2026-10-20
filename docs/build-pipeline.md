# BlackBerry 10 flashing pipeline

## Current reliable route

The most reliable current route is:

```text
macOS/Linux: bb10mt split, unpack, patch, repack
Windows VM: cap.exe packaging and Bootrom flashing
```

## AutoRoot v3 workflow

1. Start with the exact official stock autoloader for the device and firmware version.
2. Run the appropriate AutoRoot v3 build script.
3. It produces:

```text
<original-name>_root_v3.exe
<original-name>_radio.exe
```

4. Ensure the phone is already running the matching official stock firmware.
5. Flash `_root_v3.exe` first.
6. Flash `_radio.exe` afterward.

## Important distinction

`bb10mt autoloader create` is not the correct final packaging command in the observed workflow.

The Windows AutoRoot v3 script uses:

```powershell
.\cap.exe create "$UnsignedFile" "$OutputExe"
.\cap.exe create "$SmallSignedFile" "$OutputRadioExe"
```

A macOS script that instead calls:

```bash
./bb10mt autoloader create -i unsigned-image -o output.exe -c cap.exe
```

can produce an autoloader whose QCFM payload cannot be read by the Bootrom.

## Observed failure

Flashing a `bb10mt`-generated autoloader produced:

```text
Uploading RAM Image
--> Failed to read main QCFM header
Error: Failed to load images.
Error: Out of Windows memory
```

The QCFM-header failure is the meaningful error. The memory message is a generic failure reported after the invalid container is encountered.

## Native macOS/Linux goal

A native flasher would replace the Windows autoloader with a libusb/IOKit implementation:

```text
1. Detect VID 0x0fca / PID 0x8001
2. Perform vendor control-transfer setup
3. Open bulk endpoints 0x02 and 0x82
4. Send the initial framed handshake
5. Upload the RAM loader
6. Stream QCFM firmware images
7. Handle re-enumeration between OS and radio stages
```

This remains experimental research. Do not use it as a replacement for a known-good Windows flashing workflow.