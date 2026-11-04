#!/usr/bin/env python3
"""Check naming, source hashes, Qt resources, ARM images and package integrity."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT/'build/package_manifest.json'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-manifest', action='store_true', help='Record a new complete package hash manifest after review')
    args = parser.parse_args()
    errors = []
    all_paths = sorted(p for p in ROOT.rglob('*') if '.git' not in p.relative_to(ROOT).parts and p.relative_to(ROOT).as_posix() not in ('.gitattributes', '.gitignore'))
    files = [p for p in all_paths if p.is_file() and p != MANIFEST]
    for p in all_paths:
        if not re.fullmatch(r'[a-z0-9_.-]+', p.name):
            errors.append('Invalid name: '+str(p.relative_to(ROOT)))
        if p.is_dir() and p.name in ('__pycache__', '.venv', '.git', '.pio'):
            errors.append('Unwanted directory: '+str(p.relative_to(ROOT)))
    for name in ('src', 'sim', 'build', 'board', 'data', 'skill', 'report'):
        if not (ROOT/name).is_dir():
            errors.append('Missing top-level directory: '+name)
    rows = json.loads((ROOT/'build/source_map.json').read_text(encoding='utf-8'))['files']
    actual = {p.relative_to(ROOT).as_posix(): digest(p) for p in files}
    for row in rows:
        if actual.get(row['packaged']) != row['sha256']:
            errors.append('Source mismatch: '+row['packaged'])
    modules = {r['restore']: r for r in rows if r['component']=='board_modules'}
    required = ('c_camera_link/esp32/platformio.ini', 'c_camera_link/esp32/src/main.cpp',
                'c_camera_link/esp32/web/index.html', 'c_camera_link/firmware/spi-emio.bin',
                'c_camera_link/firmware/manifest.json', 'MANIFEST.sha256.json')
    for target in required:
        if target not in modules:
            errors.append('Missing board handoff: '+target)
    if all(target in modules for target in required):
        firmware = (ROOT/modules['c_camera_link/firmware/spi-emio.bin']['packaged']).read_bytes()
        metadata = json.loads((ROOT/modules['c_camera_link/firmware/manifest.json']['packaged']).read_text(encoding='utf-8'))['spi-emio']
        page = (ROOT/modules['c_camera_link/esp32/web/index.html']['packaged']).read_bytes()
        if len(firmware) != metadata['bytes'] or hashlib.sha256(firmware).hexdigest() != metadata['sha256']:
            errors.append('ESP32 firmware manifest mismatch')
        if page+b'\0' not in firmware:
            errors.append('ESP32 embedded webpage does not match HTML source')
        handoff = json.loads((ROOT/modules['MANIFEST.sha256.json']['packaged']).read_text(encoding='utf-8'))['files']
        for target, info in handoff.items():
            row = modules.get(target)
            if not row or row['sha256'] != info['sha256'] or row['bytes'] != info['bytes']:
                errors.append('Original handoff manifest mismatch: '+target)
    arm = {r['restore']: r for r in rows if r['component']=='arm'}
    for target in ('dist/armhf/labassistant', 'work/desktop_entry_20261102/QMainApp'):
        data = (ROOT/arm[target]['packaged']).read_bytes()[:52]
        if data[:6] != b'\x7fELF\x01\x01' or struct.unpack_from('<H', data, 18)[0] != 40:
            errors.append('Not ARM ELF32: '+target)
    for resource in ('work/labmate_ui/resources.qrc', 'work/vendor_desktop_labmate/iconres.qrc'):
        parent = resource.rsplit('/', 1)[0]
        document = ET.parse(str(ROOT/arm[resource]['packaged']))
        for item in document.findall('.//file'):
            if parent+'/'+item.text not in arm:
                errors.append('Missing Qt resource: '+parent+'/'+item.text)
    board = {r['restore']: r for r in rows if r['component']=='board'}
    zi = (ROOT/board['board_files/zImage']['packaged']).read_bytes()
    ui = (ROOT/board['board_files/uImage']['packaged']).read_bytes()
    magic, crc, stamp, size, load, entry, data_crc = struct.unpack_from('>7I', ui)
    header = ui[:4]+b'\0'*4+ui[8:64]
    if magic!=0x27051956 or zlib.crc32(header)!=crc or zlib.crc32(ui[64:])!=data_crc or ui[64:]!=zi or size!=len(zi):
        errors.append('Kernel uImage CRC or payload mismatch')
    if struct.unpack_from('<I', zi, 0x24)[0] != 0x016f2818:
        errors.append('Invalid ARM zImage header')
    dtb=(ROOT/board['board_files/system-spi.dtb']['packaged']).read_bytes()
    if dtb[:4] != bytes.fromhex('d00dfeed'):
        errors.append('Invalid DTB header')
    if args.write_manifest and not errors:
        data = {'schema_version': 1, 'date': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
                'files': actual, 'file_count': len(actual), 'bytes': sum(p.stat().st_size for p in files)}
        MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    elif MANIFEST.exists():
        expected = json.loads(MANIFEST.read_text(encoding='utf-8'))['files']
        if set(actual) != set(expected):
            errors.append('Files added/removed since package manifest')
        for name, sha in expected.items():
            if actual.get(name) != sha:
                errors.append('Package hash mismatch: '+name)
    else:
        errors.append('No package manifest; finish assembly and run --write-manifest once.')
    result = {'passed': not errors, 'file_count': len(files), 'source_records': len(rows),
              'source_files': len(set(r['packaged'] for r in rows)),
              'bytes': sum(p.stat().st_size for p in files), 'errors': errors,
              'checks': ['lowercase_ascii_paths', 'esp32_firmware_included', 'esp32_embedded_html', 'original_handoff_manifest', 'source_hashes',
                         'qt_resource_completeness', 'arm_elf32', 'kernel_uimage_crc', 'dtb_header', 'package_hashes']}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
