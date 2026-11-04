#!/usr/bin/env python3
"""Verify the candidate kernel, DT properties, and all installed module releases."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib


def main():
    out, module_root, artifacts = map(Path, sys.argv[1:4])
    release = sys.argv[4]
    with (out / 'vmlinux').open('rb') as source:
        elf = source.read(52)
    if elf[:6] != b'\x7fELF\x01\x01' or struct.unpack_from('<H', elf, 18)[0] != 40:
        raise SystemExit('vmlinux must be ELF32 little-endian ARM.')
    image = (artifacts / 'zImage').read_bytes()
    if struct.unpack_from('<I', image, 0x24)[0] != 0x016f2818:
        raise SystemExit('Unexpected ARM zImage header.')
    wrapped = (artifacts / 'uImage').read_bytes()
    magic, header_crc, timestamp, size, load, entry, data_crc = struct.unpack_from('>7I', wrapped)
    header = wrapped[:4] + b'\0' * 4 + wrapped[8:64]
    if (magic != 0x27051956 or zlib.crc32(header) != header_crc or
            size != len(wrapped) - 64 or zlib.crc32(wrapped[64:]) != data_crc or
            wrapped[64:] != image or load != 0x8000):
        raise SystemExit('uImage header, payload, or CRC verification failed.')

    dtb = str(artifacts / 'system-spi.dtb')
    def get(path, prop, kind='s'):
        return subprocess.check_output(['fdtget', '-t', kind, dtb, path, prop],
                                       universal_newlines=True).strip()
    required_status = {'/amba/spi@e0006000': 'okay', '/amba/serial@e0000000': 'okay',
                       '/amba/serial@e0001000': 'disabled', '/amba/can@e0008000': 'disabled'}
    for path, value in required_status.items():
        if get(path, 'status') != value:
            raise SystemExit('Incorrect status for ' + path)
    spi = '/amba/spi@e0006000'
    peripheral = spi + '/image-link@0'
    if get(peripheral, 'compatible') != 'labmate,esp32-image-link':
        raise SystemExit('Incorrect ESP32 compatible.')
    if get(spi, 'num-cs', 'u') != '1' or get(peripheral, 'reg', 'u') != '0':
        raise SystemExit('Incorrect chip select configuration.')
    if get(peripheral, 'spi-max-frequency', 'u') != '4000000':
        raise SystemExit('Incorrect SPI frequency limit.')
    properties = subprocess.check_output(['fdtget', '-p', dtb, peripheral],
                                         universal_newlines=True).splitlines()
    if 'spi-cpha' not in properties or 'spi-cpol' in properties:
        raise SystemExit('ESP32 must use SPI mode1.')
    if get('/amba/gpio@e000a000', 'emio-gpio-width', 'u') != '12':
        raise SystemExit('EMIO GPIO width must match the new XSA.')
    if 'root=/dev/mmcblk1p1' not in get('/chosen', 'bootargs').split():
        raise SystemExit('Expected this board baseline to use the eMMC root partition.')

    modules = list((module_root / 'lib/modules' / release / 'kernel').rglob('*.ko'))
    for module in modules:
        data = module.read_bytes()
        key = b'vermagic=' + release.encode('ascii') + b' '
        if key not in data:
            raise SystemExit('Module release does not match: ' + str(module))
    print(json.dumps({'kernel_release': release, 'elf': 'ARM ELF32 little-endian',
                      'spi0': 'e0006000 / CS0 / mode1', 'dtb_checked': True,
                      'uImage_crc_checked': True, 'modules_checked': len(modules),
                      'board_tested': False}, indent=2))
    print('ARTIFACT_CHECK_PASS')


if __name__ == '__main__':
    main()
