#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
if test ! -x "$ROOT/c_vision_lite/assets/smoke_infer"; then
    echo 'OCR is not board-validated: rebuild smoke_infer with the matching board SDK; see docs/BUILD.md.' >&2
    exit 2
fi
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$ROOT/c_vision_lite/assets${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec python3 -B -m c_vision_lite.board_reader --bundle "$ROOT/c_vision_lite/assets" --out "$ROOT/runs/ocr" "$@"
