#!/bin/sh
# Existing real recognition; save completed results and display history.
cd /home/root/labmate_ui_test || exit 1
assets=${LABMATE_ASR_ASSETS:-/home/root/labmate_b_audio_test}
if [ ! -f "$assets/libvosk.so" ] || [ ! -f "$assets/models/vosk-model-small-cn-0.22/am/final.mdl" ]; then
    echo "Missing Vosk library or model under: $assets"
    exit 1
fi
for program in python3 arecord aplay i2cset amixer; do
    command -v "$program" >/dev/null 2>&1 || { echo "Missing command: $program"; exit 1; }
done
python3 -c 'import numpy' || exit 1
if pidof arecord >/dev/null 2>&1 || pidof aplay >/dev/null 2>&1; then
    echo 'Audio device already in use. Stop the previous voice/audio test first.'
    exit 1
fi
# Runtime sources are a separate copy of the selected version, not the old
# audio-test directory. Only its large existing model and native library are reused.
ln -sfn "$assets/libvosk.so" asr_runtime/libvosk.so || exit 1
if [ -d "$assets/lib" ]; then
    ln -sfn "$assets/lib" asr_runtime/lib || exit 1
fi
export LABMATE_ASR_ROOT=/home/root/labmate_ui_test/asr_runtime
export LABMATE_MODEL_PATH="$assets/models/vosk-model-small-cn-0.22"
export LABMATE_BACKEND=/home/root/labmate_ui_test/backend.py
if [ -f /home/root/labmate_ui_test/instruments.json ]; then
    export LABMATE_INSTRUMENT_CONFIG="${LABMATE_INSTRUMENT_CONFIG:-/home/root/labmate_ui_test/instruments.json}"
fi
export LABMATE_RECORD_DIR="${LABMATE_RECORD_DIR:-/home/root/labmate_ui_test/data/records}"
export LABMATE_HISTORY_DIRS="${LABMATE_HISTORY_DIRS:-$assets/data/records:/media/sd-mmcblk0p1/labmate_b_board_20261015/data/records}"
# JSON retains original timezone-aware timestamps; the UI renders UTC+08:00.
# This affects local time formatting only; it does not set the board's clock.
export TZ=Asia/Shanghai
export LD_LIBRARY_PATH="$assets/lib:$assets${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONIOENCODING=utf-8
# Show import errors on the serial console before opening the GUI. Importing
# these modules does not start ASR, touch the microphone or save any records.
python3 -c 'import backend, record_store, asr_adapter; print("Backend imports OK")' || exit 1
python3 -c 'from datetime import datetime; print("Board time:", datetime.now().astimezone().isoformat()); print("WARNING: set board time before saving new records") if datetime.now().year < 2026 else None'
exec sh ./run_ui_test.sh
