#!/bin/sh
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
PYTHONPATH="$root/c_instrument/vendor:$root" \
    python3 -c 'import sys; sys.path.append("c_instrument/compat_py37"); import runpy; runpy.run_module("c_instrument.sds1202x", run_name="__main__")' --backend @py "$@"
