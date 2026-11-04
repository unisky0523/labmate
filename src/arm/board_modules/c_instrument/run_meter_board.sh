#!/bin/sh
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
PYTHONPATH="$root/c_instrument/vendor:$root" \
    python3 -m c_instrument.sa5041 --port cp210x-usb "$@"
