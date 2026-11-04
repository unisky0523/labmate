#!/bin/sh
set -u

echo '=== Kernel and Python ==='
uname -a
python3 --version 2>&1 || true
echo '=== USB devices ==='
if command -v lsusb >/dev/null 2>&1; then lsusb; else echo 'lsusb is unavailable'; fi
echo '=== Userspace USB backend ==='
python3 -c "import ctypes.util; print('libusb:', ctypes.util.find_library('usb-1.0'))" 2>&1 || true
if [ -d "$(dirname "$0")/vendor/usb" ]; then
    echo 'Bundled PyUSB is present'
else
    echo 'Bundled PyUSB is absent; use the updated board bundle'
fi
echo '=== USBTMC device nodes ==='
found=0
for node in /dev/usbtmc[0-9]*; do
    if [ -e "$node" ]; then ls -l "$node"; found=1; fi
done
if [ "$found" -eq 0 ]; then echo 'No /dev/usbtmcN node found'; fi
echo '=== Driver ==='
if command -v lsmod >/dev/null 2>&1; then lsmod | grep usbtmc || true; fi
if [ -r /proc/config.gz ] && command -v zcat >/dev/null 2>&1; then
    zcat /proc/config.gz | grep '^CONFIG_USB_TMC=' || true
fi
echo '=== Recent kernel messages ==='
dmesg 2>&1 | tail -n 40 || true
