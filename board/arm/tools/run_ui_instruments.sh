#!/bin/sh
# Opt-in instrument dispatch. Keep the original recognition launch untouched.
export LABMATE_INSTRUMENT_CONFIG="${LABMATE_INSTRUMENT_CONFIG:-/home/root/labmate_ui_test/instruments.json}"
exec sh /home/root/labmate_ui_test/run_ui_voice.sh
