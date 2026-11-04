#!/usr/bin/env python3
"""Build the delivered Vivado 2020.2 design in a prepared workspace."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--vivado', required=True, help='Vivado 2020.2 executable or vivado.bat')
    args = parser.parse_args()
    project = Path(args.workspace).expanduser().resolve()/'fpga/Navigator_7010'
    entry = project/'spi/scripts/build_from_rtl.py'
    if not entry.is_file():
        parser.error('Run build/prepare.py for fpga first.')
    subprocess.run([sys.executable, str(entry), '--vivado', args.vivado], cwd=str(project), check=True)


if __name__ == '__main__':
    main()
