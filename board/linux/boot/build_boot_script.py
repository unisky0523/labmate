from pathlib import Path
import struct
import time
import zlib

p = Path(__file__).resolve().parent
script = (p / 'boot.cmd').read_bytes().replace(b'\r\n', b'\n')
data = struct.pack('>II', len(script), 0) + script
fields = [0x27051956, 0, int(time.time()), len(data), 0, 0, zlib.crc32(data), 5, 2, 6, 0,
          b'LabMate SPI eMMC 20261104'.ljust(32, b'\0')]
header = struct.pack('>7I4B32s', *fields)
fields[1] = zlib.crc32(header)
header = struct.pack('>7I4B32s', *fields)
image = header + data
assert len(image) < 0x20000
assert zlib.crc32(header[:4] + bytes(4) + header[8:]) == fields[1]
assert zlib.crc32(image[64:]) == fields[6]
(p / 'boot.scr').write_bytes(image)
print('BOOT_SCRIPT_CREATED', len(image))
