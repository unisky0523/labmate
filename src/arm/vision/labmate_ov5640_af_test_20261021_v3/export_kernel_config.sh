#!/bin/sh
set -eu
DEST=$(CDPATH= cd "$(dirname "$0")" && pwd)
CONFIG_OUT="$DEST/board_kernel_config_20261022.txt"
zcat /proc/config.gz > "$CONFIG_OUT"
sync
wc -c "$CONFIG_OUT"
echo "CONFIG_EXPORTED=$CONFIG_OUT"
