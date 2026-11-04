#!/bin/sh
set -u

echo "=== Linux ==="
uname -a
echo "=== Python ==="
python3 --version 2>&1 || true
python3 -m pip --version 2>&1 || true
echo "=== USB devices ==="
if command -v lsusb >/dev/null 2>&1; then
    lsusb
else
    echo "lsusb is not installed"
fi
echo "=== USB serial nodes ==="
found=0
for node in /dev/ttyUSB* /dev/ttyACM*; do
    if [ -e "$node" ]; then
        ls -l "$node"
        found=1
    fi
done
if [ "$found" -eq 0 ]; then
    echo "No /dev/ttyUSB* or /dev/ttyACM* node found"
fi
echo "=== Recent kernel messages ==="
dmesg 2>&1 | tail -n 40 || true
