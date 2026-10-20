#!/usr/bin/env bash
# Export a USBPcap/usbmon capture of a BB10 autoloader run into the TSV files used by bb10_analyze.py.
# Usage: analysis/tshark_extract.sh flash.pcapng [bus_id] [outdir]
# Output (outdir, default ./out):
#   control.tsv       every control transfer (setup fields + data stage)
#   bulk_small.tsv    bulk transfers that are NOT exactly 16384 bytes   (frame, time, ep, len, hex)
#   bulk_chunks.tsv   bulk transfers of exactly 16384 bytes             (frame, time, ep, len, hex)
#   sessions.txt      candidate enumeration times (start of each GET_DESCRIPTOR(device) burst)
# Field names differ a little between Wireshark versions. If a column comes out empty, check
#   tshark -G fields | grep -i 'usb\.\(setup\|urb\|capdata\|control\)'
set -euo pipefail
PCAP=${1:?usage: $0 capture.pcapng [bus_id] [outdir]}
BUS=${2:-}
OUT=${3:-out}
mkdir -p "$OUT"
BUSF=""; [ -n "$BUS" ] && BUSF="usb.bus_id==$BUS && "

echo "[1/4] control transfers"
tshark -r "$PCAP" -Y "${BUSF}usb.transfer_type==0x02" -T fields -E separator=$'\t' \
  -e frame.number -e frame.time_relative -e usb.device_address -e usb.urb_type \
  -e usb.bmRequestType -e usb.setup.bRequest -e usb.setup.wValue -e usb.setup.wIndex \
  -e usb.setup.wLength -e usb.urb_status -e usb.data_len -e usb.capdata -e usb.control.Response \
  > "$OUT/control.tsv"

echo "[2/4] bulk payloads"
tshark -r "$PCAP" -Y "${BUSF}usb.transfer_type==0x03 && usb.capdata" -T fields -E separator=$'\t' \
  -e frame.number -e frame.time_relative -e usb.endpoint_address -e usb.capdata \
  | awk -F'\t' -v out="$OUT" 'BEGIN{OFS="\t"}
      { hex=$4; gsub(":","",hex); n=length(hex)/2
        ep=$3; if (ep !~ /^0x/) ep=sprintf("0x%02x", ep+0)
        f=(n==16384) ? out"/bulk_chunks.tsv" : out"/bulk_small.tsv"
        print $1,$2,ep,n,hex > f }'

echo "[3/4] session boundaries (device-descriptor requests, wLength 18)"
awk -F'\t' '$6==6 && $9==18 && $4!="" {print $2}' "$OUT/control.tsv" \
  | awk 'NR==1 || $1-prev>1.0 {print} {prev=$1}' > "$OUT/sessions.txt" || true
cat "$OUT/sessions.txt"

echo "[4/4] done. Next:"
echo "  S=\$(tail -n +2 $OUT/sessions.txt | paste -sd, -)   # drop t=0 (normal-mode enumeration) if present"
echo "  python3 analysis/bb10_analyze.py hist   $OUT/bulk_small.tsv  --sessions \$S"
echo "  python3 analysis/bb10_analyze.py loader $OUT/bulk_small.tsv  --sessions \$S -o loader"
echo "  python3 analysis/bb10_analyze.py chunks $OUT/bulk_chunks.tsv --sessions \$S"
