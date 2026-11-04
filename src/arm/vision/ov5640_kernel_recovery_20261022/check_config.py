#!/usr/bin/env python3
"""Only the test release identifier may differ from the actual board config."""
import re
import sys


def read(path):
    result = {}
    with open(path, encoding='utf-8') as source:
        for line in source:
            line = line.strip()
            if line.startswith('CONFIG_') and '=' in line:
                key, value = line.split('=', 1)
                result[key] = value
            else:
                match = re.fullmatch(r'# (CONFIG_\w+) is not set', line)
                if match:
                    result[match.group(1)] = 'n'
    return result


if __name__ == '__main__':
    before, after = map(read, sys.argv[1:3])
    allowed = {'CONFIG_LOCALVERSION', 'CONFIG_LOCALVERSION_AUTO'}
    unexpected = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key, 'n'), after.get(key, 'n')
        if old != new:
            print('{}: {} -> {}'.format(key, old, new))
            if key not in allowed:
                unexpected.append(key)
    if unexpected:
        raise SystemExit('Unexpected config changes; review before building: ' + ', '.join(unexpected))
    for key, value in {'CONFIG_ARCH_ZYNQ': 'y', 'CONFIG_I2C_XILINX': 'y',
                       'CONFIG_MODULES': 'y', 'CONFIG_MODVERSIONS': 'y',
                       'CONFIG_LOCALVERSION': '"-xilinx-v2020.2-af-test-20261022"',
                       'CONFIG_LOCALVERSION_AUTO': 'n'}.items():
        if after.get(key) != value:
            raise SystemExit('Unexpected {}={}'.format(key, after.get(key)))
    print('CONFIG_MATCH_PASS: board settings preserved; only test release changed.')
