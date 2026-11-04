#!/usr/bin/env python3
"""Patch this board's spidev match and guard the retained board configuration."""
import argparse
import difflib
import json
import re
from pathlib import Path


COMPATIBLE = 'labmate,esp32-image-link'
RELEASE_SUFFIX = '"-xilinx-v2020.2-spi-test-20261104"'


def patch_source(source_dir, patch_path):
    source_dir = Path(source_dir)
    makefile = (source_dir / 'Makefile').read_text(encoding='utf-8')
    for symbol, value in [('VERSION', '5'), ('PATCHLEVEL', '4'), ('SUBLEVEL', '0')]:
        if not re.search(r'^' + symbol + r'\s*=\s*' + value + r'\s*$', makefile, re.M):
            raise SystemExit('This kit expects the supplied Linux 5.4.0 source.')
    path = source_dir / 'drivers/spi/spidev.c'
    before = path.read_text(encoding='utf-8')
    pattern = r'(static\s+const\s+struct\s+of_device_id\s+spidev_dt_ids\s*\[\s*\]\s*=\s*\{)(.*?)(\n\s*\};)'
    matches = list(re.finditer(pattern, before, re.S))
    if len(matches) != 1:
        raise SystemExit('Expected exactly one spidev_dt_ids table; source unchanged.')
    match = matches[0]
    if COMPATIBLE in match.group(2):
        raise SystemExit('Source is already patched; use a fresh extraction for this kit.')
    if COMPATIBLE in before:
        raise SystemExit('Compatible appears outside the expected table; review source.')
    addition = '\n\t{ .compatible = "' + COMPATIBLE + '" },'
    after = before[:match.end(1)] + addition + before[match.end(1):]
    backup = path.with_name('spidev.c.before-esp32-spi')
    if backup.exists():
        raise SystemExit('Backup already exists; use a fresh extraction.')
    backup.write_bytes(path.read_bytes())
    with path.open('w', encoding='utf-8', newline='\n') as output:
        output.write(after)
    diff = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                      fromfile='a/drivers/spi/spidev.c',
                                      tofile='b/drivers/spi/spidev.c'))
    with Path(patch_path).open('w', encoding='utf-8', newline='\n') as output:
        output.write(diff)
    print('SPIDEV_MATCH_ADDED:', COMPATIBLE)


def read_config(path):
    values = {}
    for raw in Path(path).read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if line.startswith('CONFIG_') and '=' in line:
            key, value = line.split('=', 1)
            values[key] = value
        else:
            match = re.fullmatch(r'# (CONFIG_\w+) is not set', line)
            if match:
                values[match.group(1)] = 'n'
    return values


def check_config(before_path, after_path):
    before, after = read_config(before_path), read_config(after_path)
    expected = {
        'CONFIG_ARCH_ZYNQ': 'y',
        'CONFIG_SPI': 'y',
        'CONFIG_SPI_MASTER': 'y',
        'CONFIG_SPI_CADENCE': 'y',
        'CONFIG_SPI_SPIDEV': 'y',
        'CONFIG_GPIO_SYSFS': 'y',
        'CONFIG_GPIO_ZYNQ': 'y',
        'CONFIG_MODULES': 'y',
        'CONFIG_MODVERSIONS': 'y',
        'CONFIG_LOCALVERSION': RELEASE_SUFFIX,
        'CONFIG_LOCALVERSION_AUTO': 'n',
    }
    allowed = {'CONFIG_SPI', 'CONFIG_SPI_MASTER', 'CONFIG_SPI_CADENCE',
               'CONFIG_SPI_SPIDEV', 'CONFIG_GPIO_SYSFS',
               'CONFIG_LOCALVERSION', 'CONFIG_LOCALVERSION_AUTO'}
    unexpected = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key, 'n'), after.get(key, 'n')
        if old != new:
            print('{}: {} -> {}'.format(key, old, new))
            if key == 'CONFIG_BT_RTK_HCIBTUSB' and old == 'm' and new == 'n':
                print('CONFIG_NOTICE: supplied vendor source lacks the optional Realtek Bluetooth driver; candidate kernel omits it.')
                continue
            if key not in allowed:
                unexpected.append(key)
    if unexpected:
        raise SystemExit('Unexpected configuration changes: ' + ', '.join(unexpected))
    for key, value in expected.items():
        if after.get(key, 'n') != value:
            raise SystemExit('Required {}={}, found {}'.format(key, value, after.get(key, 'n')))
    print('CONFIG_MATCH_PASS: only SPI options and the test release may change.')


def prepare_device_tree(source_dir, spi_path, bootargs_path, patch_path):
    directory = Path(source_dir) / 'arch/arm/boot/dts'
    soc = (directory / 'zynq-7000.dtsi').read_text(encoding='utf-8')
    for label, node, address in [('spi0', 'spi', 'e0006000'),
                                 ('uart0', 'serial', 'e0000000'),
                                 ('uart1', 'serial', 'e0001000'),
                                 ('can0', 'can', 'e0008000'),
                                 ('gpio0', 'gpio', 'e000a000')]:
        pattern = r'\b' + label + r':\s*' + node + '@' + address + r'\s*\{'
        if not re.search(pattern, soc):
            raise SystemExit('Expected hardware label/address is missing: ' + label)
    board = directory / 'atk-navigator-7010.dts'
    before = board.read_text(encoding='utf-8')
    wrapper_name = 'labmate-spi-board.dtsi'
    if wrapper_name in before:
        raise SystemExit('Device tree already prepared; use a fresh extraction.')
    lines = [line.strip() for line in Path(bootargs_path).read_text(encoding='utf-8').splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if len(lines) != 1 or 'root=/dev/mmcblk1p1' not in lines[0].split():
        raise SystemExit('Expected the recorded eMMC bootargs baseline.')
    spi = Path(spi_path).read_text(encoding='utf-8')
    if 'labmate,esp32-image-link' not in spi or '&spi0' not in spi:
        raise SystemExit('Expected the original supplied ESP32 device-tree fragment.')
    wrapper = ('/* SPI additions to the retained factory board tree. */\n'
               '#include "esp32-spi.dtsi"\n\n'
               '&gpio0 { emio-gpio-width = <12>; };\n\n'
               '/ {\n    chosen {\n        bootargs = ' + json.dumps(lines[0]) + ';\n'
               '    };\n};\n')
    after = before.rstrip('\n') + '\n#include "' + wrapper_name + '"\n'
    changes = [(board, before, after), (directory / wrapper_name, '', wrapper),
               (directory / 'esp32-spi.dtsi', '', spi)]
    diff = ''
    for path, old, new in changes:
        if not old and path.exists():
            raise SystemExit('Unexpected existing device-tree file: ' + str(path))
        relative = 'arch/arm/boot/dts/' + path.name
        diff += ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                           fromfile='a/' + relative if old else '/dev/null',
                                           tofile='b/' + relative))
    backup = board.with_name(board.name + '.before-esp32-spi')
    if backup.exists():
        raise SystemExit('Device-tree backup already exists; use a fresh extraction.')
    backup.write_bytes(board.read_bytes())
    for path, old, new in changes:
        with path.open('w', encoding='utf-8', newline='\n') as output:
            output.write(new)
    with Path(patch_path).open('w', encoding='utf-8', newline='\n') as output:
        output.write(diff)
    print('DEVICE_TREE_PREPARED: original nodes retained; supplied SPI fragment added.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command')
    patch = sub.add_parser('patch')
    patch.add_argument('source_dir')
    patch.add_argument('patch_path')
    check = sub.add_parser('check-config')
    check.add_argument('before')
    check.add_argument('after')
    tree = sub.add_parser('device-tree')
    tree.add_argument('source_dir')
    tree.add_argument('spi_path')
    tree.add_argument('bootargs_path')
    tree.add_argument('patch_path')
    args = parser.parse_args()
    if args.command is None:
        parser.error('Choose patch, device-tree, or check-config.')
    if args.command == 'patch':
        patch_source(args.source_dir, args.patch_path)
    elif args.command == 'check-config':
        check_config(args.before, args.after)
    else:
        prepare_device_tree(args.source_dir, args.spi_path, args.bootargs_path, args.patch_path)


if __name__ == '__main__':
    main()
