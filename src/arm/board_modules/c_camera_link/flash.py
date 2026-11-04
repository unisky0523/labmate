"""Flash an explicitly selected ESP32 image; never runs during packaging."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--variant', choices=('spi-emio',), default='spi-emio')
    parser.add_argument('--firmware-dir', type=Path)
    parser.add_argument('--confirm-overwrite', action='store_true')
    args = parser.parse_args()
    if not args.confirm_overwrite:
        parser.error('Flashing replaces the existing ESP32 application; add --confirm-overwrite')
    base = args.firmware_dir or Path(__file__).parent / 'firmware'
    if not base.exists() and args.firmware_dir is None:
        base = Path(__file__).parent / 'generated/firmware'
    manifest = json.loads((base / 'manifest.json').read_text(encoding='utf-8'))
    image = base / (args.variant + '.bin')
    if hashlib.sha256(image.read_bytes()).hexdigest() != manifest[args.variant]['sha256']:
        raise ValueError('Firmware checksum mismatch; do not flash')
    subprocess.run([sys.executable, '-m', 'esptool', '--chip', 'esp32', '--port', args.port,
                    '--baud', '115200', 'write_flash', '--flash_mode', 'dio',
                    '--flash_freq', '40m', '--flash_size', '4MB', '0x0', str(image)], check=True)


if __name__ == '__main__':
    main()
