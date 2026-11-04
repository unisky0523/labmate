#!/bin/sh
set -eu
TEST_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
APP_DIR=$(CDPATH= cd "$TEST_DIR/.." && pwd)
export LD_LIBRARY_PATH="$APP_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cd "$TEST_DIR"
exec python3 af_test.py "$@"
