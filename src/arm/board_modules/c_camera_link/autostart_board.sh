#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$ROOT/vendor:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -B -m c_camera_link.autostart "$@"
