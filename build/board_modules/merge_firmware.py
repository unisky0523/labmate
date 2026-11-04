"""Merge the final PlatformIO ESP32 SPI-EMIO build; never flash hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--framework-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, help='Optional isolated output directory')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    directory = args.output_dir or root / 'c_camera_link/firmware'
    directory.mkdir(parents=True, exist_ok=True)
    image = directory / 'spi-emio.bin'
    inputs = [('0x1000', args.build_dir / 'bootloader.bin'),
              ('0x8000', args.build_dir / 'partitions.bin'),
              ('0xe000', args.framework_dir / 'tools/partitions/boot_app0.bin'),
              ('0x10000', args.build_dir / 'firmware.bin')]
    for _, path in inputs:
        if not path.is_file():
            raise FileNotFoundError(path)
    command = [sys.executable, '-m', 'esptool', '--chip', 'esp32', 'merge_bin',
               '-o', str(image), '--flash_mode', 'dio', '--flash_freq', '40m', '--flash_size', '4MB']
    for offset, path in inputs:
        command.extend([offset, str(path)])
    subprocess.run(command, check=True)
    manifest = {'spi-emio': {'environment': 'esp32dev_spi_emio', 'chip': 'esp32',
                            'flash_offset': 0, 'bytes': image.stat().st_size,
                            'sha256': hashlib.sha256(image.read_bytes()).hexdigest()}}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
