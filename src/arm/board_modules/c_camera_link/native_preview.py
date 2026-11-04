"""Connect existing native capture to the UART/SPI sender without OpenCV."""

import argparse
from pathlib import Path
import sys
import tempfile

from . import sender


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--program', type=Path, help='Original af_capture; used only with --legacy-capture')
    parser.add_argument('--legacy-capture', action='store_true')
    parser.add_argument('--direct-jpeg', action='store_true')
    args, options = parser.parse_known_args()
    program = args.program.resolve(strict=True) if args.legacy_capture and args.program else None
    if args.legacy_capture and program is None:
        parser.error('--legacy-capture requires --program')
    if args.direct_jpeg and args.legacy_capture:
        parser.error('--direct-jpeg cannot be combined with --legacy-capture')
    if any(option in ('--image', '--camera', '--capture-command', '--capture-file', '--native-stream', '--native-jpeg-stream') or
           option.startswith(('--image=', '--camera=', '--capture-command=', '--capture-file=', '--native-stream=', '--native-jpeg-stream='))
           for option in options):
        parser.error('native_preview selects its own capture source')
    old_argv = sys.argv
    if args.direct_jpeg:
        tool = Path(__file__).parent / 'native/camera_jpeg_stream_armv7'
        sys.argv = ['native_preview', '--capture-timeout', '30'] + options + [
            '--native-jpeg-stream', str(tool)]
        try:
            sender.main()
        finally:
            sys.argv = old_argv
        return
    if not args.legacy_capture:
        tool = Path(__file__).parent / 'native/camera_stream_armv7'
        sys.argv = ['native_preview', '--encoder', 'native', '--capture-timeout', '30'] + options + [
            '--native-stream', str(tool)]
        try:
            sender.main()
        finally:
            sys.argv = old_argv
        return
    with tempfile.TemporaryDirectory(prefix='labmate_preview_') as directory:
        output = str(Path(directory) / 'before.ppm')
        sys.argv = ['native_preview', '--encoder', 'native', '--capture-timeout', '30'] + options + [
            '--capture-file', output, '--capture-command', sys.executable, '-B', '-m',
            'c_camera_link.native_capture', '--program', str(program), '--output', output]
        try:
            sender.main()
        finally:
            sys.argv = old_argv


if __name__ == '__main__':
    main()
