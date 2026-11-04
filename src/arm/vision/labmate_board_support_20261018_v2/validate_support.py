"""Check strong dynamic imports against the reviewed factory rootfs exports."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
READELF = Path(r"D:\Xilinx\SDK\2018.3\gnu\aarch32\nt\gcc-arm-linux-gnueabi\bin\arm-linux-gnueabihf-readelf.exe")
ROOTFS = Path(r"D:\学科文件\大三上\FPGA创新赛\tmp\audio_source_review\资源文件\出厂镜像相关\rootfs.tar.gz")
TARGET = ROOT / "build/target-libs"
TARGET.mkdir(exist_ok=True)
libraries = ["./lib/libc.so.6", "./lib/libm.so.6", "./lib/libpthread.so.0", "./lib/libdl.so.2", "./lib/librt.so.1", "./lib/libgcc_s.so.1", "./lib/ld-linux-armhf.so.3", "./usr/lib/libstdc++.so.6", "./usr/lib/libpython3.7m.so.1.0"]
reference = {}
with tarfile.open(ROOTFS) as archive:
    for name in libraries:
        data = archive.extractfile(name).read()
        (TARGET / Path(name).name).write_bytes(data)
        reference[name] = hashlib.sha256(data).hexdigest()
    for name in ["./usr/lib/python3.7/site-packages/cv2.cpython-37m-arm-linux-gnueabi.so", "./usr/lib/libopencv_core.so.3.4.3", "./usr/lib/libopencv_highgui.so.3.4.3", "./usr/include/python3.7m/pyconfig-32.h"]:
        data = archive.extractfile(name).read()
        reference[name] = hashlib.sha256(data).hexdigest()


def dynsyms(path):
    output = subprocess.check_output([str(READELF), "-W", "--dyn-syms", str(path)], text=True)
    symbols = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[0].endswith(":") and fields[0][:-1].isdigit():
            symbols.append((fields[4], fields[6], fields[7]))
    return symbols


checks = [ROOT / "payload/smoke_infer", ROOT / "payload/libgomp.so.1", ROOT / "payload/pyclipper/_pyclipper.cpython-37m-arm-linux-gnueabi.so", Path(r"D:\FPGA\labmate_lite_image_reader_board_v2\libpaddle_light_api_shared.so"), ROOT / "payload/native_fault.so"]
providers = list(TARGET.iterdir()) + checks[1:2] + checks[3:]
exports = set()
for path in providers:
    for binding, section, symbol in dynsyms(path):
        if section != "UND" and binding in ("GLOBAL", "WEAK", "UNIQUE"):
            exports.add(symbol.replace("@@", "@"))
            if "@" not in symbol or "@@" in symbol:
                exports.add(symbol.split("@")[0])

extension_symbols = dynsyms(checks[2])
assert any(binding == "GLOBAL" and section != "UND" and name == "PyInit__pyclipper" for binding, section, name in extension_symbols), "CPython module initializer must be globally exported"

results = {}
for path in checks:
    imports = [name for binding, section, name in dynsyms(path) if section == "UND" and binding == "GLOBAL"]
    missing = sorted(set(imports) - exports)
    versions = sorted({name.split("@", 1)[1] for name in imports if "@" in name})
    header = subprocess.check_output([str(READELF), "-h", "-A", "-W", str(path)], text=True)
    assert "ELF32" in header and "Machine:                           ARM" in header and "hard-float ABI" in header
    results[path.name] = {"strong_imports": len(imports), "unresolved_against_factory": missing, "required_symbol_versions": versions, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    if missing:
        raise RuntimeError("Unresolved symbols in " + path.name + ": " + repr(missing))

report = {"validation": "STATIC_ONLY_NOT_PHYSICAL_BOARD_TESTED", "python_extension_initializer_export": "PyInit__pyclipper GLOBAL DEFINED", "compiler": "Xilinx SDK 2018.3 / Linaro GCC 7.3.1, its older Linux sysroot", "target_reference": "factory rootfs glibc 2.30, libstdc++ 6.0.27, CPython 3.7", "results": results, "factory_file_sha256": reference}
dependency_root = ROOT / "build/cv2-dependencies"
if (dependency_root / "paths.json").exists():
    for name in json.loads((dependency_root / "paths.json").read_text()):
        local = dependency_root / Path(name).name
        if local.is_file():
            reference["." + name] = hashlib.sha256(local.read_bytes()).hexdigest()
(ROOT / "STATIC_VALIDATION.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({name: {"imports": value["strong_imports"], "unresolved": value["unresolved_against_factory"]} for name, value in results.items()}, indent=2))
print("PASS: static ARM ABI and all strong imports matched against factory rootfs + supplied runtime.")
