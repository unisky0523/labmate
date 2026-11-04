#!/bin/sh
set -eu
SD_PROJECT=$(CDPATH= cd "$(dirname "$0")" && pwd)
SOURCE="$SD_PROJECT/labmate_ov5640_af_test_20261021_v3"
APP="$HOME/labmate_reader_v2"
TOOL="$APP/labmate_ov5640_af_test_20261021_v3"
mkdir -p "$TOOL"
for name in af_capture af_test.py convert_images.py; do
    cp "$SOURCE/$name" "$TOOL/$name"
done
chmod +x "$TOOL/af_capture"
export LD_LIBRARY_PATH="$APP${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cd "$TOOL"
exec python3 af_test.py --autofocus
