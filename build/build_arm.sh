#!/usr/bin/env bash
# Usage: bash build/build_arm.sh /path/to/prepared_workspace
set -eo pipefail
[[ $# == 1 ]] || { echo 'Usage: bash build_arm.sh PREPARED_WORKSPACE' >&2; exit 2; }
task_root=$(cd -- "$1" && pwd)
task_sdk_env="${LABMATE_SDK_ENV:-/home/labmat/petalinux_sdk_2020_2/environment-setup-cortexa9t2hf-neon-xilinx-linux-gnueabi}"
[[ -f "$task_sdk_env" ]] || { echo "Set LABMATE_SDK_ENV: $task_sdk_env not found" >&2; exit 2; }
[[ -f "$task_root/arm/work/labmate_ui/labassistant.pro" ]] || { echo 'Run build/prepare.py for arm first.' >&2; exit 2; }
source "$task_sdk_env"
mkdir -p "$task_root/arm/build/ui" "$task_root/arm/build/desktop" "$task_root/arm/dist/armhf" "$task_root/arm/work/desktop_entry_20261102"
cd "$task_root/arm/build/ui"
qmake "$task_root/arm/work/labmate_ui/labassistant.pro"
make -j"${LABMATE_BUILD_JOBS:-2}"
cp labassistant "$task_root/arm/dist/armhf/labassistant"
cd "$task_root/arm/build/desktop"
qmake "$task_root/arm/work/vendor_desktop_labmate/QMainUI.pro"
make -j"${LABMATE_BUILD_JOBS:-2}"
cp QMainApp "$task_root/arm/work/desktop_entry_20261102/QMainApp"
file "$task_root/arm/dist/armhf/labassistant" "$task_root/arm/work/desktop_entry_20261102/QMainApp"
sha256sum "$task_root/arm/dist/armhf/labassistant" "$task_root/arm/work/desktop_entry_20261102/QMainApp"
