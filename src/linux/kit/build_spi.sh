#!/usr/bin/env bash
# Ubuntu 18.04 offline build, using the same SDK as the existing ARM app package.
set -eo pipefail
KIT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
case "${1:-}" in
    --help|-h)
        printf '%s\n' 'Usage: bash build_spi.sh [--check]' \
            'Uses the existing PetaLinux 2020.2 SDK; new host tools are included offline.'
        exit 0 ;;
    ''|--check) ;;
    *) printf '%s\n' 'Usage: bash build_spi.sh [--check]' >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { echo 'Too many arguments.' >&2; exit 2; }

for needed in python3 dpkg-deb gcc g++ make tar gzip sha256sum perl; do
    command -v "$needed" >/dev/null || {
        printf 'Existing Ubuntu build environment is missing: %s\n' "$needed" >&2
        exit 2
    }
done
source /etc/os-release
if [[ ${ID:-} != ubuntu || ${VERSION_ID:-} != 18.04 || $(uname -m) != x86_64 ]]; then
    echo 'This offline bundle targets the established Ubuntu 18.04 x86_64 VM.' >&2
    exit 2
fi
printf '%s\n' 'Checking bundled files...'
(cd "$KIT" && sha256sum -c INPUT_SHA256SUMS > /dev/null)

ENV_NAME=environment-setup-cortexa9t2hf-neon-xilinx-linux-gnueabi
sdk_env=${LABMATE_SDK_ENV:-${SDK_ENV:-}}
if [[ -z "$sdk_env" ]]; then
    for candidate in "$HOME/petalinux_sdk_2020_2/$ENV_NAME" \
                     "/home/labmat/petalinux_sdk_2020_2/$ENV_NAME" \
                     "$HOME/tools/xilinx-sdk/2020.2/$ENV_NAME" \
                     "/opt/petalinux/2020.2/$ENV_NAME"; do
        if [[ -f "$candidate" ]]; then sdk_env=$candidate; break; fi
    done
fi
if [[ ! -f "$sdk_env" ]]; then
    echo 'Existing ARM SDK was not found. Expected /home/labmat/petalinux_sdk_2020_2.' >&2
    echo 'If it was moved, set LABMATE_SDK_ENV to its environment-setup file.' >&2
    exit 2
fi

# Extract native tools under HOME; this does not install or replace system packages.
HOST_ROOT=$(python3 "$KIT/helpers/setup_host_tools.py" "$KIT/offline-host-tools" \
    "$HOME/.cache/labmate-spi-host-tools")
unset LD_LIBRARY_PATH
source "$sdk_env"
unset CFLAGS CPPFLAGS CXXFLAGS LDFLAGS
export ARCH=arm CROSS_COMPILE=arm-xilinx-linux-gnueabi-
export PATH="$HOST_ROOT/wrappers:$HOST_ROOT/usr/bin:$HOST_ROOT/bin:$HOST_ROOT/sbin:$HOST_ROOT/usr/sbin:$PATH"
export LD_LIBRARY_PATH="$HOST_ROOT/usr/lib/x86_64-linux-gnu:$HOST_ROOT/lib/x86_64-linux-gnu"
export PKG_CONFIG_SYSROOT_DIR="$HOST_ROOT"
export PKG_CONFIG_LIBDIR="$HOST_ROOT/usr/lib/x86_64-linux-gnu/pkgconfig:$HOST_ROOT/usr/share/pkgconfig"
export PKG_CONFIG_PATH=
export BISON_PKGDATADIR="$HOST_ROOT/usr/share/bison"
export M4="$HOST_ROOT/usr/bin/m4"
for needed in bc bison flex mkimage dtc fdtget depmod pkg-config \
              "${CROSS_COMPILE}gcc" "${CROSS_COMPILE}readelf"; do
    command -v "$needed" >/dev/null || { echo "Missing bundled tool: $needed" >&2; exit 2; }
done
bc --version > /dev/null
bison --version > /dev/null
flex --version > /dev/null
mkimage -V > /dev/null
dtc --version > /dev/null
depmod --version > /dev/null
pkg-config --exists libcrypto libelf
compiler_version=$("${CROSS_COMPILE}gcc" -dumpfullversion -dumpversion)
[[ "$compiler_version" == 9.2.0 ]] || {
    echo "Expected the board SDK GCC 9.2.0; found $compiler_version" >&2; exit 2;
}
printf 'SDK=%s\nARM_GCC=%s\nOFFLINE_HOST_TOOLS=%s\n' "$sdk_env" "$compiler_version" "$HOST_ROOT"
if [[ ${1:-} == --check ]]; then
    echo 'PREFLIGHT_PASS'
    exit 0
fi

JOBS=${JOBS:-2}
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo 'JOBS must be a positive integer.' >&2; exit 2; }
PARENT=${BUILD_PARENT:-"$HOME/labmate_spi_kernel_build_20261104"}
mkdir -p "$PARENT"
WORK=$(mktemp -d "$PARENT/build.XXXXXX")
exec > >(tee "$WORK/build.log") 2>&1
trap 'printf "BUILD_FAILED line=%s; log=%s/build.log\n" "$LINENO" "$WORK"' ERR
printf 'WORK_DIR=%s\n' "$WORK"
tar -xJf "$KIT/source/atk-zynq-linux-xlnx.tar.xz" -C "$WORK"
SRC="$WORK/atk-zynq-linux-xlnx"
OUT="$WORK/build"
ARTIFACTS="$WORK/board-files"
mkdir -p "$OUT" "$ARTIFACTS"
python3 "$KIT/helpers/prepare_kernel.py" patch "$SRC" "$ARTIFACTS/spidev-compatible.patch"
python3 "$KIT/helpers/prepare_kernel.py" device-tree "$SRC" \
    "$KIT/runtime/esp32-spi.dtsi" "$KIT/config/board-bootargs.txt" \
    "$ARTIFACTS/device-tree-changes.patch"
cp "$KIT/config/board.config" "$OUT/.config"
"$SRC/scripts/config" --file "$OUT/.config" \
    --enable SPI --enable SPI_MASTER --enable SPI_CADENCE \
    --enable SPI_SPIDEV --enable GPIO_SYSFS \
    --set-str LOCALVERSION '-xilinx-v2020.2-spi-test-20261104' \
    --disable LOCALVERSION_AUTO

ARGS=(-C "$SRC" O="$OUT" ARCH=arm CROSS_COMPILE="$CROSS_COMPILE" \
    HOSTCC=/usr/bin/gcc HOSTCXX=/usr/bin/g++ LOCALVERSION= \
    "HOSTCFLAGS=-O2 -Wall -Wmissing-prototypes -Wstrict-prototypes -std=gnu89 -fomit-frame-pointer -I$HOST_ROOT/usr/include -I$HOST_ROOT/usr/include/x86_64-linux-gnu" \
    "HOSTLDFLAGS=-L$HOST_ROOT/usr/lib/x86_64-linux-gnu -L$HOST_ROOT/lib/x86_64-linux-gnu -Wl,-rpath,$HOST_ROOT/usr/lib/x86_64-linux-gnu -Wl,-rpath,$HOST_ROOT/lib/x86_64-linux-gnu")
make "${ARGS[@]}" olddefconfig
python3 "$KIT/helpers/prepare_kernel.py" check-config "$KIT/config/board.config" \
    "$OUT/.config" | tee "$ARTIFACTS/config-changes.txt"
make "${ARGS[@]}" -j"$JOBS" LOADADDR=0x8000 zImage uImage atk-navigator-7010.dtb modules
RELEASE=$(make -s "${ARGS[@]}" kernelrelease)
[[ "$RELEASE" == 5.4.0-xilinx-v2020.2-spi-test-20261104 ]]
make "${ARGS[@]}" INSTALL_MOD_PATH="$WORK/modules-root" modules_install

cp "$OUT/arch/arm/boot/zImage" "$ARTIFACTS/zImage"
cp "$OUT/arch/arm/boot/uImage" "$ARTIFACTS/uImage"
cp "$OUT/arch/arm/boot/dts/atk-navigator-7010.dtb" "$ARTIFACTS/system-spi.dtb"
cp "$OUT/.config" "$ARTIFACTS/kernel.config"
cp "$OUT/Module.symvers" "$ARTIFACTS/Module.symvers"
cp "$KIT/config/board-bootargs.txt" "$ARTIFACTS/board-bootargs.txt"
printf '%s\n' "$RELEASE" > "$ARTIFACTS/kernel-release.txt"
cp -r "$KIT/runtime" "$ARTIFACTS/runtime"
cp -r "$KIT/handoff/FPGA" "$ARTIFACTS/FPGA"
cp "$KIT/boot/uboot_spi_clock.txt" "$ARTIFACTS/"
python3 "$KIT/helpers/verify_build.py" "$OUT" "$WORK/modules-root" \
    "$ARTIFACTS" "$RELEASE" | tee "$ARTIFACTS/verification.txt"
tar -czf "$ARTIFACTS/modules-$RELEASE.tar.gz" -C "$WORK/modules-root" lib
"${CROSS_COMPILE}readelf" -h "$OUT/vmlinux" > "$ARTIFACTS/vmlinux-elf-header.txt"
dumpimage -l "$ARTIFACTS/uImage" > "$ARTIFACTS/uImage-info.txt"
cp "$KIT/编译说明.txt" "$ARTIFACTS/编译说明.txt"
(cd "$ARTIFACTS" && find . -type f ! -name SHA256SUMS -print0 | \
    sort -z | xargs -0 sha256sum > SHA256SUMS)
mkdir -p "$KIT/output"
tar -czf "$KIT/output/spi_board_files_20261104.tar.gz" -C "$ARTIFACTS" .
cp "$ARTIFACTS/verification.txt" "$KIT/output/verification.txt"
cp "$WORK/build.log" "$KIT/output/build.log"
(cd "$KIT/output" && sha256sum spi_board_files_20261104.tar.gz > SHA256SUMS)
printf '\nBUILD_OK: %s/output/spi_board_files_20261104.tar.gz\n' "$KIT"
printf '%s\n' 'Copy this archive back to Windows for the board deployment step.'
