"""Build a standalone Cortex-A9 Linux converter with Zig 0.13.0."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zig', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    header = root / 'third_party/stb_image_write.h'
    source = root / 'ppm_to_jpeg.c'
    output = root / 'ppm_to_jpeg_armv7'
    command = [str(args.zig.resolve()), 'cc', '-target', 'arm-linux-musleabihf',
               '-mcpu=cortex_a9', '-static', '-O2', '-s', '-ffunction-sections',
               '-Wl,--gc-sections', str(source), '-o', str(output), '-lm']
    subprocess.run(command, check=True)
    stream_source = root / 'camera_stream.c'
    stream_output = root / 'camera_stream_armv7'
    stream_command = command.copy()
    stream_command[stream_command.index(str(source))] = str(stream_source)
    stream_command[stream_command.index(str(output))] = str(stream_output)
    subprocess.run(stream_command, check=True)
    jpeg_stream_output = root / 'camera_jpeg_stream_armv7'
    jpeg_stream_command = stream_command.copy()
    jpeg_stream_command[jpeg_stream_command.index(str(stream_output))] = str(jpeg_stream_output)
    jpeg_stream_command.insert(2, '-DLM_CAMERA_JPEG=1')
    subprocess.run(jpeg_stream_command, check=True)
    binary = output.read_bytes()
    if binary[:6] != b'\x7fELF\x01\x01' or int.from_bytes(binary[18:20], 'little') != 40:
        raise ValueError('Expected 32-bit little-endian ARM ELF')
    offset = int.from_bytes(binary[28:32], 'little')
    size = int.from_bytes(binary[42:44], 'little')
    count = int.from_bytes(binary[44:46], 'little')
    for i in range(count):
        kind = int.from_bytes(binary[offset+i*size:offset+i*size+4], 'little')
        if kind in (2, 3):
            raise ValueError('Unexpected dynamic/interpreter segment in static executable')
    manifest = {'target': 'arm-linux-musleabihf', 'cpu': 'cortex_a9', 'static': True,
                'zig': subprocess.check_output([str(args.zig.resolve()), 'version']).decode().strip(),
                'bytes': len(binary), 'sha256': hashlib.sha256(binary).hexdigest(),
                'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'stb_sha256': hashlib.sha256(header.read_bytes()).hexdigest(),
                'preview_jpeg_sha256': hashlib.sha256((root / 'preview_jpeg.h').read_bytes()).hexdigest(),
                'stb_commit': '1ee679ca2ef753a528db5ba6801e1067b40481b8'}
    stream = stream_output.read_bytes()
    if stream[:6] != b'\x7fELF\x01\x01' or int.from_bytes(stream[18:20], 'little') != 40:
        raise ValueError('Expected ARM camera ELF')
    phoff = int.from_bytes(stream[28:32], 'little')
    phsize = int.from_bytes(stream[42:44], 'little')
    phcount = int.from_bytes(stream[44:46], 'little')
    if any(int.from_bytes(stream[phoff+i*phsize:phoff+i*phsize+4], 'little') in (2, 3)
           for i in range(phcount)):
        raise ValueError('Camera executable must be static with no interpreter')
    manifest['camera_stream'] = {'bytes': len(stream), 'sha256': hashlib.sha256(stream).hexdigest(),
                                 'source_sha256': hashlib.sha256(stream_source.read_bytes()).hexdigest()}
    jpeg_stream = jpeg_stream_output.read_bytes()
    if jpeg_stream[:6] != b'\x7fELF\x01\x01' or int.from_bytes(jpeg_stream[18:20], 'little') != 40:
        raise ValueError('Expected ARM JPEG camera ELF')
    phoff = int.from_bytes(jpeg_stream[28:32], 'little')
    phsize = int.from_bytes(jpeg_stream[42:44], 'little')
    phcount = int.from_bytes(jpeg_stream[44:46], 'little')
    if any(int.from_bytes(jpeg_stream[phoff+i*phsize:phoff+i*phsize+4], 'little') in (2, 3)
           for i in range(phcount)):
        raise ValueError('JPEG camera executable must be static')
    manifest['camera_jpeg_stream'] = {'bytes': len(jpeg_stream),
                                     'sha256': hashlib.sha256(jpeg_stream).hexdigest(),
                                     'defines': ['LM_CAMERA_JPEG=1']}
    (root / 'build_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
