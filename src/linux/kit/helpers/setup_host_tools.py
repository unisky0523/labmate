#!/usr/bin/env python3
"""Unpack verified Ubuntu native tools in an isolated user-owned cache."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def elf_binary(candidates):
    for path in candidates:
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as source:
                if source.read(4) == b'\x7fELF':
                    return path
    raise SystemExit('Expected native binary was not present in the offline packages.')


def main():
    inputs, parent = map(Path, sys.argv[1:3])
    raw_manifest = (inputs / 'manifest.json').read_bytes()
    identity = hashlib.sha256(raw_manifest).hexdigest()
    cache = parent / identity[:16]
    marker = cache / '.complete'
    if marker.is_file() and marker.read_text().strip() == identity:
        print(cache)
        return
    manifest = json.loads(raw_manifest.decode('utf-8'))
    cache.mkdir(parents=True, exist_ok=True)
    print('Preparing bundled native tools (no sudo, no network)...', file=sys.stderr)
    for package in manifest['packages']:
        path = inputs / 'debs' / Path(package['Filename']).name
        if hashlib.sha256(path.read_bytes()).hexdigest() != package['SHA256']:
            raise SystemExit('Offline package hash mismatch: ' + path.name)
        subprocess.check_call(['dpkg-deb', '-x', str(path), str(cache)])
    if any(path.name == 'libc.so.6' for path in cache.rglob('libc.so.6')):
        raise SystemExit('An unexpected libc was included; do not use this tool cache.')
    wrappers = cache / 'wrappers'
    wrappers.mkdir(exist_ok=True)
    kmod = elf_binary([cache / 'bin/kmod', cache / 'usr/bin/kmod'])
    pkgconfig = elf_binary([cache / 'usr/bin/pkg-config',
                           cache / 'usr/bin/x86_64-linux-gnu-pkg-config'])
    for name, target in [('depmod', kmod), ('modinfo', kmod), ('pkg-config', pkgconfig)]:
        link = wrappers / name
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            raise SystemExit('Unexpected file in tool wrappers: ' + str(link))
        link.symlink_to(os.path.relpath(str(target), str(wrappers)))
    marker.write_text(identity + '\n')
    print(cache)


if __name__ == '__main__':
    main()
