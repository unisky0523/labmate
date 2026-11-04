"""Capture into a fresh directory using the existing board-native program."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def capture(program, output, timeout=20):
    program = Path(program).resolve(strict=True)
    output = Path(output).resolve()
    with tempfile.TemporaryDirectory(prefix='labmate_capture_') as directory:
        subprocess.run([str(program), '--capture-only'], cwd=directory, check=True, timeout=timeout)
        image = Path(directory) / 'before.ppm'
        if not image.is_file() or image.stat().st_size < 16:
            raise RuntimeError('Native capture did not produce a new before.ppm')
        shutil.copyfile(str(image), str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--program', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--timeout', type=float, default=20)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('timeout must be positive')
    capture(args.program, args.output, args.timeout)


if __name__ == '__main__':
    main()
