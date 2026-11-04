#!/bin/sh
set -eu
APP_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$APP_DIR"
export LD_LIBRARY_PATH="$APP_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec python3 -m c_vision_lite.board_reader --bundle "$APP_DIR" "$@"
