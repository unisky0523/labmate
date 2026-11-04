#!/usr/bin/env bash
# Build on the Linux VM using the board's SDK. This script only builds files.
set -eo pipefail
KIT=$(cd -- "$(dirname -- "$0")" && pwd)
ENV_NAME=environment-setup-cortexa9t2hf-neon-xilinx-linux-gnueabi
if [[ -z ${SDK_ENV:-} ]]; then
    if [[ -f "$HOME/tools/xilinx-sdk/2020.2/$ENV_NAME" ]]; then
        SDK_ENV="$HOME/tools/xilinx-sdk/2020.2/$ENV_NAME"
    else
        SDK_ENV="/opt/petalinux/2020.2/$ENV_NAME"
    fi
fi
if [[ ! -f "$SDK_ENV" ]]; then
    echo "SDK environment not found: $SDK_ENV"
    echo 'Set SDK_ENV to your installed SDK environment-setup file and run again.'
    exit 2
fi
source "$SDK_ENV"
export ARCH=arm CROSS_COMPILE=arm-xilinx-linux-gnueabi-
# SDK application flags must not override the kernel's own compiler options.
unset CFLAGS CPPFLAGS CXXFLAGS LDFLAGS
for command in make gcc g++ perl python3 patch bc bison flex tar gzip sha256sum \
               "${CROSS_COMPILE}gcc" "${CROSS_COMPILE}readelf"; do
    command -v "$command" >/dev/null || { echo "Missing build command: $command"; exit 2; }
done
VERSION=$("${CROSS_COMPILE}gcc" -dumpfullversion -dumpversion)
echo "SDK_ENV=$SDK_ENV"
echo "ARM_COMPILER=$VERSION"
if [[ "$VERSION" != 9.2.0 ]]; then
    echo 'This kit targets the board SDK GCC 9.2.0; select its SDK_ENV.'
    exit 2
fi
(cd "$KIT" && sha256sum -c INPUT_SHA256SUMS)
if [[ ${1:-} == --check ]]; then
    echo 'PREFLIGHT_PASS (kernel has not been compiled)'
    exit 0
fi
if [[ $# != 0 ]]; then
    echo 'Usage: bash build_kernel.sh [--check]'
    exit 2
fi
PARENT=${BUILD_PARENT:-"$HOME/labmate-kernel-build"}
mkdir -p "$PARENT"
WORK=$(mktemp -d "$PARENT/xiic-20261022.XXXXXX")
exec > >(tee "$WORK/build.log") 2>&1
trap 'echo "BUILD_FAILED line=$LINENO; log=$WORK/build.log"' ERR
echo "WORK_DIR=$WORK"
tar -xJf "$KIT/atk-zynq-linux-xlnx.tar.xz" -C "$WORK"
SRC="$WORK/atk-zynq-linux-xlnx"
BUILD="$WORK/build"
ARTIFACTS="$WORK/artifacts"
mkdir -p "$BUILD" "$ARTIFACTS"
patch --batch --forward -d "$SRC" -p1 < "$KIT/xiic-factory-busy-recovery.patch"
cp "$KIT/board_kernel_config_20261022.txt" "$BUILD/.config"
# Separate the test kernel's module directory from the original kernel.
"$SRC/scripts/config" --file "$BUILD/.config" \
    --set-str LOCALVERSION '-xilinx-v2020.2-af-test-20261022' \
    --disable LOCALVERSION_AUTO
ARGS=(-C "$SRC" O="$BUILD" ARCH=arm CROSS_COMPILE="$CROSS_COMPILE" \
      HOSTCC=gcc HOSTCXX=g++ LOCALVERSION=)
make "${ARGS[@]}" olddefconfig
python3 "$KIT/check_config.py" "$KIT/board_kernel_config_20261022.txt" \
    "$BUILD/.config" | tee "$ARTIFACTS/config-changes.txt"
JOBS=${JOBS:-2}
make "${ARGS[@]}" -j"$JOBS" zImage atk-navigator-7010.dtb modules
RELEASE=$(make -s "${ARGS[@]}" kernelrelease)
[[ "$RELEASE" == 5.4.0-xilinx-v2020.2-af-test-20261022 ]]
make "${ARGS[@]}" INSTALL_MOD_PATH="$ARTIFACTS/modules-root" modules_install
cp "$BUILD/arch/arm/boot/zImage" "$ARTIFACTS/zImage-af-test"
cp "$BUILD/arch/arm/boot/dts/atk-navigator-7010.dtb" "$ARTIFACTS/atk-navigator-7010-af-test.dtb"
cp "$BUILD/.config" "$ARTIFACTS/kernel.config"
cp "$BUILD/Module.symvers" "$ARTIFACTS/Module.symvers"
"${CROSS_COMPILE}readelf" -h "$BUILD/vmlinux" > "$ARTIFACTS/vmlinux-elf-header.txt"
printf '%s\n' "$RELEASE" > "$ARTIFACTS/kernel-release.txt"
tar -czf "$ARTIFACTS/modules-$RELEASE.tar.gz" -C "$ARTIFACTS/modules-root" lib
cp "$KIT/xiic-factory-busy-recovery.patch" "$ARTIFACTS/"
(cd "$ARTIFACTS" && sha256sum zImage-af-test atk-navigator-7010-af-test.dtb \
    kernel.config Module.symvers "modules-$RELEASE.tar.gz" > SHA256SUMS)
echo "BUILD_COMPLETE=$ARTIFACTS"
echo 'Candidate only: no board flash, boot files, or boot environment were modified.'
