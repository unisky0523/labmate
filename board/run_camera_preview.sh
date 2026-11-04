#!/bin/sh
# Run the matched handoff sender at a requested 4 MHz / target 10 fps.
set -eu
if test "$#" -lt 1; then
    echo 'Usage: sh board/run_camera_preview.sh /absolute/path/to/labmate_repro [sender options]' >&2
    exit 2
fi
TASK_WORKSPACE=$1
shift
cd "$TASK_WORKSPACE/board_modules"
test -f c_camera_link/run_spi_emio_board.sh
exec sh c_camera_link/run_spi_emio_board.sh --spi-cs-high --preview --ten-fps --count 0 "$@"
