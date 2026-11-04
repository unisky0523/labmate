#!/usr/bin/env python3
"""Restore original case-sensitive source names into an external build workspace."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def under(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def prepare(out, components):
    out = Path(out).expanduser().resolve()
    if under(out, ROOT):
        raise ValueError('Choose a build workspace outside the submission directory.')
    rows = json.loads((ROOT/'build/source_map.json').read_text(encoding='utf-8'))['files']
    selected = [r for r in rows if r['component'] and ('all' in components or r['component'] in components)]
    checked = set()
    count = 0
    for row in selected:
        relative = PurePosixPath(row['restore'])
        if relative.is_absolute() or '..' in relative.parts or '\\' in row['restore']:
            raise ValueError('Invalid restore path: ' + row['restore'])
        source = (ROOT/row['packaged']).resolve()
        if not under(source, ROOT):
            raise ValueError('Invalid source path: ' + row['packaged'])
        if row['packaged'] not in checked:
            if sha256(source) != row['sha256']:
                raise ValueError('Source hash mismatch: ' + row['packaged'])
            checked.add(row['packaged'])
        target = out/row['component']/Path(*relative.parts)
        resolved = target.resolve()
        if not under(resolved, out):
            raise ValueError('Restore path escapes build workspace: ' + str(target))
        if target.exists():
            if not target.is_file() or sha256(target) != row['sha256']:
                raise ValueError('Different existing file preserved: ' + str(target))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        if os.name != 'nt':
            target.chmod(row['mode'])
        count += 1
    if not selected:
        raise ValueError('No sources selected.')
    print('PREPARED {} files in {}'.format(count, out))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='External, preferably empty build workspace')
    parser.add_argument('--component', nargs='+', default=['all'],
                        choices=['all', 'arm', 'fpga', 'linux', 'vision', 'board', 'boot', 'board_modules', 'skill'])
    args = parser.parse_args()
    prepare(args.out, args.component)


if __name__ == '__main__':
    main()
