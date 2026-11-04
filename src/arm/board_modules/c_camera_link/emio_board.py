"""Discover the handed-off SPI0 device and PS GPIO offset 65 on Linux."""

import argparse
from pathlib import Path
import sys
import time


def discover_spi(root=Path('/sys/bus/spi/devices')):
    matches = []
    for path in root.glob('spi*.*'):
        compatible = path / 'of_node/compatible'
        if compatible.is_file() and b'labmate,esp32-image-link' in compatible.read_bytes().split(b'\0'):
            matches.append('/dev/spidev' + path.name[3:])
    if len(matches) != 1:
        raise RuntimeError('Expected one labmate,esp32-image-link SPI device, found {}'.format(matches))
    if not Path(matches[0]).exists():
        raise RuntimeError('SPI exists but {} is absent; check spidev driver binding'.format(matches[0]))
    return matches[0]


def discover_ready(root=Path('/sys/class/gpio')):
    chips = []
    for chip in root.glob('gpiochip*'):
        label = (chip / 'label').read_text().strip().lower()
        if ('zynq' in label or 'e000a000' in label) and int((chip / 'ngpio').read_text()) > 65:
            chips.append(chip)
    if len(chips) != 1:
        raise RuntimeError('Cannot identify PS gpiochip; pass an explicitly configured --ready-path')
    number = int((chips[0] / 'base').read_text()) + 65
    gpio = root / ('gpio' + str(number))
    if not gpio.exists():
        try:
            (root / 'export').write_text(str(number))
        except OSError:
            if not gpio.exists():
                raise
        deadline = time.monotonic() + 1
        while not (gpio / 'direction').exists():
            if time.monotonic() >= deadline:
                raise RuntimeError('GPIO export did not complete')
            time.sleep(0.01)
    (gpio / 'direction').write_text('in')
    return str(gpio / 'value')


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--spi-device')
    parser.add_argument('--ready-path')
    parser.add_argument('--preview', action='store_true')
    presets = parser.add_mutually_exclusive_group()
    presets.add_argument('--fast', action='store_true',
                        help='320px quality50, frame-end ACK, no frame-rate cap (v3 token firmware)')
    presets.add_argument('--ten-fps', action='store_true',
                        help='Direct native JPEG, requested 4MHz SPI, 320px quality50, target 10fps')
    presets.add_argument('--max-fps', action='store_true',
                        help='Uncapped pipelined native JPEG, requested 8MHz SPI, 320px quality50')
    args, options = parser.parse_known_args()
    if (args.ten_fps or args.max_fps) and not args.preview:
        parser.error('--ten-fps / --max-fps requires --preview')
    if any(v == '--transport' or v.startswith('--transport=') for v in options):
        parser.error('This entry selects spi-emio automatically')
    try:
        print('SPI sender fps-v3-uncapped-20261104: module={}'.format(Path(__file__).resolve()),
              file=sys.stderr, flush=True)
        device = args.spi_device or discover_spi()
        ready = args.ready_path or discover_ready()
        print('SPI EMIO: device={} READY={} mode=1'.format(device, ready), file=sys.stderr)
        sys.argv = ['emio_board', '--transport', 'spi-emio', '--spi-device', device,
                    '--ready-path', ready, '--spi-speed', '2000000']
        if args.max_fps:
            sys.argv += ['--direct-jpeg', '--pipeline', '--spi-frame-poll', '--spi-set-speed',
                         '--spi-speed', '8000000', '--width', '320', '--quality', '50',
                         '--interval', '0', '--log-every', '30']
        elif args.ten_fps:
            sys.argv += ['--direct-jpeg', '--spi-frame-poll', '--spi-set-speed',
                         '--spi-speed', '4000000', '--width', '320', '--quality', '50',
                         '--interval', '0.1', '--log-every', '10']
        elif args.fast:
            sys.argv += ['--spi-frame-poll', '--width', '320', '--quality', '50', '--interval', '0']
        sys.argv += options
        if args.preview:
            from .native_preview import main as run
        else:
            from .sender import main as run
        run()
    except (OSError, RuntimeError, ValueError) as exc:
        print('SPI EMIO failed: {}'.format(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
