"""Build board-local candidates; does not modify the original application."""
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SDK = Path(r"D:\Xilinx\SDK\2018.3\gnu\aarch32\nt\gcc-arm-linux-gnueabi")
CXX = SDK / "bin/arm-linux-gnueabihf-g++.exe"
READELF = SDK / "bin/arm-linux-gnueabihf-readelf.exe"
PAYLOAD = ROOT / "payload"
BASE = [str(CXX), "-O2", "-std=c++11", "-march=armv7-a", "-mfpu=neon", "-mfloat-abi=hard"]
commands = []


def run(args):
    commands.append(args)
    process = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, errors="replace")
    print(process.stdout, end="", flush=True)
    if process.returncode:
        raise RuntimeError("Build failed (exit {}): {}".format(process.returncode, args))


shutil.copyfile(SDK / "arm-linux-gnueabihf/lib/libgomp.so.1.0.0", PAYLOAD / "libgomp.so.1")
run(BASE + ["-Isources", "sources/smoke_infer.cc", "D:/FPGA/labmate_lite_image_reader_board_v2/libpaddle_light_api_shared.so", "-Lpayload", "-Wl,-rpath-link,payload", "-ldl", "-lpthread", "-o", "payload/smoke_infer"])

package = PAYLOAD / "pyclipper"
package.mkdir(exist_ok=True)
for filename in ("__init__.py", "_version.py"):
    shutil.copyfile(ROOT / "build/pyclipper-source/src/pyclipper" / filename, package / filename)
config32 = ROOT / "build/python-include/python3.7m/pyconfig-32.h"
config32.parent.mkdir(exist_ok=True)
shutil.copyfile(ROOT / "build/python-include/pyconfig-32.h", config32)
run(BASE + ["-shared", "-fPIC", "-Ibuild/python-include", "-Ibuild/pyclipper-source/src", "build/pyclipper-source/src/pyclipper/_pyclipper.cpp", "build/pyclipper-source/src/clipper.cpp", "-o", "payload/pyclipper/_pyclipper.cpython-37m-arm-linux-gnueabi.so"])
run([str(SDK / "bin/arm-linux-gnueabihf-gcc.exe"), "-shared", "-fPIC", "-O2", "-march=armv7-a", "-mfpu=neon", "-mfloat-abi=hard", "sources/native_fault.c", "-o", "payload/native_fault.so"])

run([str(READELF), "-h", "-A", "-W", "payload/smoke_infer"])
for filename in ("smoke_infer", "libgomp.so.1", "pyclipper/_pyclipper.cpython-37m-arm-linux-gnueabi.so"):
    report = subprocess.check_output([str(READELF), "-d", "-V", "-W", "payload/" + filename], cwd=ROOT, text=True, errors="replace")
    (ROOT / "build" / (Path(filename).name + ".elf.txt")).write_text(report, encoding="utf-8")
(ROOT / "build/commands.json").write_text(json.dumps(commands, indent=2), encoding="utf-8")
print("Built ARMv7 hard-float support candidates. Physical board validation is still required.")
