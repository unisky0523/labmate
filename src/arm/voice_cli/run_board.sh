#!/bin/sh
DIR=$(cd "$(dirname "$0")" && pwd)
export LD_LIBRARY_PATH="$DIR/lib:$DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
cd "$DIR" || exit 1
exec python3 "$DIR/board_app.py" "$@"
