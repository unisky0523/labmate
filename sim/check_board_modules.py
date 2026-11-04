#!/usr/bin/env python3
"""Check restored ESP32/web/ARM handoff files without accessing hardware."""
import argparse
import ast
import configparser
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tokenize
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--node', help='Optional Node.js executable for JavaScript syntax validation')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('labmate_prepare', str(ROOT / 'build/prepare.py'))
    prepare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepare)
    prepare.prepare(args.workspace, ['board_modules'])
    handoff = args.workspace.resolve() / 'board_modules'
    manifest = json.loads((handoff / 'MANIFEST.sha256.json').read_text(encoding='utf-8'))['files']
    failures = []
    checks = {}

    def require(condition, detail):
        if not condition:
            failures.append(detail)

    for name, info in manifest.items():
        path = handoff / name
        require(path.is_file() and path.stat().st_size == info['bytes'] and
                digest(path.read_bytes()) == info['sha256'], 'Handoff mismatch: ' + name)
    checks['handoff_manifest_files'] = len(manifest)
    count = 0
    for path in handoff.rglob('*.py'):
        try:
            with tokenize.open(path) as stream:
                source = stream.read()
            compile(source, str(path), 'exec')
            ast.parse(source, filename=str(path), feature_version=(3, 7))
            count += 1
        except (SyntaxError, UnicodeError) as exc:
            failures.append('Python syntax: {}: {}'.format(path.relative_to(handoff), exc))
    checks['python_files_parsed_for_3_7'] = count

    firmware = handoff / 'c_camera_link/firmware'
    image = (firmware / 'spi-emio.bin').read_bytes()
    image_info = json.loads((firmware / 'manifest.json').read_text(encoding='utf-8'))['spi-emio']
    require(len(image) == image_info['bytes'] and digest(image) == image_info['sha256'],
            'ESP32 firmware hash/size mismatch')
    page = (handoff / 'c_camera_link/esp32/web/index.html').read_bytes()
    require(page + b'\0' in image, 'Exact embedded HTML not found in supplied ESP32 firmware')
    checks['firmware_bytes'] = len(image)
    checks['embedded_html_matches'] = page + b'\0' in image
    checks['firmware_sha256'] = digest(image)

    ini = configparser.ConfigParser()
    ini.read(handoff / 'c_camera_link/esp32/platformio.ini', encoding='utf-8')
    require(ini['env']['platform'] == 'espressif32@6.9.0', 'Unpinned ESP32 platform')
    require(ini['env']['lib_deps'] == 'bblanchon/ArduinoJson@6.21.5', 'Unpinned ArduinoJson')
    require(ini['env']['board_build.embed_txtfiles'] == 'web/index.html', 'Embedded web path mismatch')
    flags = ini['env:esp32dev_spi_emio']['build_flags']
    for key, value in {'LM_SPI_SCLK': 18, 'LM_SPI_MOSI': 23, 'LM_SPI_MISO': 19,
                       'LM_SPI_CS': 27, 'LM_SPI_READY': 26, 'LINK_SPI': 1, 'LINK_SPI_TOKEN': 1}.items():
        require(re.search(r'-D\s+' + key + '=' + str(value) + r'(?:\s|$)', flags) is not None,
                'ESP32 pin/config mismatch: ' + key)
    checks['esp32_environment'] = ini['platformio']['default_envs']

    native = handoff / 'c_camera_link/native'
    build = json.loads((native / 'build_manifest.json').read_text(encoding='utf-8'))
    entries = [('ppm_to_jpeg_armv7', build), ('camera_stream_armv7', build['camera_stream']),
               ('camera_jpeg_stream_armv7', build['camera_jpeg_stream'])]
    for name, info in entries:
        data = (native / name).read_bytes()
        require(len(data) == info['bytes'] and digest(data) == info['sha256'], 'Native hash mismatch: ' + name)
        is_arm = data[:6] == b'\x7fELF\x01\x01' and struct.unpack_from('<H', data, 18)[0] == 40
        require(is_arm, 'Native ELF32 ARM mismatch: ' + name)
        if is_arm:
            offset = struct.unpack_from('<I', data, 28)[0]
            entry_size, entry_count = struct.unpack_from('<HH', data, 42)
            require(all(struct.unpack_from('<I', data, offset + i * entry_size)[0] not in (2, 3)
                        for i in range(entry_count)), 'Native program is not static: ' + name)
    for name, key in [('ppm_to_jpeg.c', 'source_sha256'), ('third_party/stb_image_write.h', 'stb_sha256'),
                      ('preview_jpeg.h', 'preview_jpeg_sha256')]:
        require(digest((native / name).read_bytes()) == build[key], 'Native source mismatch: ' + name)
    require(digest((native / 'camera_stream.c').read_bytes()) == build['camera_stream']['source_sha256'],
            'Camera source mismatch')
    checks['static_arm_executables'] = len(entries)

    # Exercise framing, CRC, padding and rejection behavior using the actual
    # supplied protocol implementation, with no device access or mocks of it.
    spec = importlib.util.spec_from_file_location('handoff_protocol', str(handoff / 'c_camera_link/protocol.py'))
    protocol = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(protocol)
    vectors = 0
    for size in [4, 995, 996, 997, 1015, 1016, 1017, 2032, 32768]:
        jpeg = b'\xff\xd8' + bytes((i % 251 for i in range(size - 4))) + b'\xff\xd9'
        for sequence in [0, 17, 0xffffffff]:
            framed = protocol.frame(jpeg, sequence)
            magic, seq, length, crc = protocol.HEADER.unpack_from(framed)
            require((magic, seq, length, crc) == (b'LMJPEG01', sequence, size, zlib.crc32(jpeg)),
                    'Frame header/CRC failed')
            recovered = bytearray()
            for packet in protocol.spi_packets(framed):
                tag, used, reserved = protocol.CHUNK.unpack_from(packet)
                require(len(packet) == 1024 and tag == b'LMCK' and reserved == 0 and used <= 1016,
                        'SPI chunk format failed')
                recovered.extend(packet[8:8 + used])
                require(not any(packet[8 + used:]), 'SPI padding failed')
            require(bytes(recovered) == framed, 'SPI reassembly failed')
            protocol.check_ack(protocol.ACK.pack(b'LMAK', sequence, 0), sequence)
            vectors += 1
    rejected = 0
    for data in [b'', b'1234', b'\xff\xd8' + b'x' * 32765 + b'\xff\xd9']:
        try:
            protocol.frame(data, 1)
        except ValueError:
            rejected += 1
    for ack in [b'', protocol.ACK.pack(b'FAIL', 1, 0), protocol.ACK.pack(b'LMAK', 2, 0),
                protocol.ACK.pack(b'LMAK', 1, 1), protocol.ACK.pack(b'LMAK', 1, 2)]:
        try:
            protocol.check_ack(ack, 1)
        except IOError:
            rejected += 1
    require(rejected == 8, 'Malformed frame/ACK rejection failed')
    checks['protocol_roundtrip_vectors'] = vectors
    checks['invalid_frames_or_acks_rejected'] = rejected

    # The current DTB permits 4 MHz; the teammate's max-fps preset requests 8 MHz.
    # Keep both source snapshots and explicitly record this integration boundary.
    dts = (ROOT / 'src/linux/kit/runtime/esp32-spi.dtsi').read_text(encoding='utf-8')
    require('spi-max-frequency = <4000000>' in dts and 'spi-cpha;' in dts, 'Unexpected current DT settings')
    checks['current_dtb_spi_limit_hz'] = 4000000
    checks['handoff_max_fps_requested_hz'] = 8000000
    checks['hardware_accessed'] = False
    checks['fresh_esp32_or_arm_cross_build'] = False
    node = args.node or shutil.which('node')
    if node:
        source = '\n'.join(re.findall(r'<script[^>]*>(.*?)</script>', page.decode('utf-8'), re.S))
        process = subprocess.run([node, '--check', '-'], input=source, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        require(process.returncode == 0, 'JavaScript syntax: ' + process.stdout)
        checks['javascript_syntax'] = 'passed' if process.returncode == 0 else 'failed'
    else:
        checks['javascript_syntax'] = 'not_run_node_unavailable'
    result = {'passed': not failures, 'checks': checks, 'failures': failures}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
