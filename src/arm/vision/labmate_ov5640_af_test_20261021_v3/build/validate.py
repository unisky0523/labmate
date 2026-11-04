import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

root = Path(__file__).resolve().parents[1]
sdk = Path(r'D:\Xilinx\SDK\2018.3\gnu\aarch32\nt\gcc-arm-linux-gnueabi\bin')
elf = str(sdk / 'arm-linux-gnueabihf-readelf.exe')
target = root.parent / 'labmate_board_support_20261018_v2/build/target-libs'
def symbols(path):
    out = subprocess.check_output([elf, '-W', '--dyn-syms', str(path)], text=True)
    for line in out.splitlines():
        f = line.split()
        if len(f) >= 8 and f[0].endswith(':') and f[0][:-1].isdigit():
            yield f[4], f[6], f[7]
exports = set()
for lib in target.iterdir():
    for binding, section, name in symbols(lib):
        if section != 'UND' and binding in ('GLOBAL', 'WEAK', 'UNIQUE'):
            exports.add(name.replace('@@', '@'))
            if '@' not in name or '@@' in name:
                exports.add(name.split('@')[0])
binary = root / 'af_capture'
imports = {n for b, s, n in symbols(binary) if b == 'GLOBAL' and s == 'UND'}
assert not imports - exports, sorted(imports - exports)
header = subprocess.check_output([elf, '-h', '-A', '-l', '-d', '-W', str(binary)], text=True)
assert 'ELF32' in header and 'hard-float ABI' in header and 'ARM' in header
assert '/lib/ld-linux-armhf.so.3' in header
needed = re.findall(r'Shared library: \[(.*?)\]', header)
assert set(needed) <= {'libc.so.6', 'librt.so.1', 'libgcc_s.so.1'}, needed
for name in ('af_test.py', 'convert_images.py'):
    ast.parse((root/name).read_text(encoding='utf-8'), feature_version=(3, 7))
for name in ('run_af_test.sh', 'af_test.py', 'convert_images.py', 'af_capture.c'):
    assert b'\r' not in (root/name).read_bytes(), name
payload = re.search(r'ov5640_af_firmware\[\]\s*=\s*\{(.*?)\}', (root/'sources/ov5640_af_firmware.h').read_text(), re.S)[1]
firmware = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]{2})', payload))
assert 1024 < len(firmware) < 8192
report = {'validation':'STATIC_ONLY_NOT_PHYSICAL_BOARD_TESTED', 'needed':needed,
          'strong_imports':sorted(imports), 'unresolved':[], 'firmware_bytes':len(firmware),
          'firmware_sha256':hashlib.sha256(firmware).hexdigest(),
          'python_3_7_syntax':'PASS', 'elf':header}
(root/'build/validation.txt').write_text(json.dumps(report, indent=2), encoding='utf-8')
manifest = {str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.json'}
(root/'SHA256SUMS.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
archive = root.with_suffix('.zip')
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in root.rglob('*'):
        if p.is_file():
            z.write(p, root.name + '/' + str(p.relative_to(root)).replace('\\','/'))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
print('PASS ARM hard-float, all strong imports match factory, Python 3.7 syntax, ZIP CRC')
print('Firmware bytes:', len(firmware))
print('Archive:', archive, 'bytes=', archive.stat().st_size)
