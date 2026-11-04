#!/usr/bin/env python3
"""Try the factory shape DSO privately, then install locally only on success."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
NAME = "libopencv_shape.so.3.4"
EXPECTED = "311b18ae66685a764d0a36053bf3d39198f1318203f3b806e8019630e5713cda"


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    if platform.machine() != "armv7l" or sys.version_info[:2] != (3, 7):
        raise RuntimeError("Requires ARMv7 Linux / CPython 3.7")
    manifest = json.loads((ROOT / "PACKAGE_MANIFEST.json").read_text())
    for name, expected in manifest.items():
        if sha(ROOT / name) != expected:
            raise RuntimeError("Package checksum mismatch: " + name)
    candidate = ROOT / "payload" / NAME
    if sha(candidate) != EXPECTED:
        raise RuntimeError("Factory shape library checksum mismatch")
    app = args.app.resolve()
    if not (app / "c_vision_lite/board_reader.py").is_file():
        raise RuntimeError("Application directory is not the v2 image reader")
    report_dir = Path(tempfile.mkdtemp(prefix="shape_report_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_", dir=str(ROOT)))
    summary = {"app": str(app), "expected_shape_sha256": EXPECTED, "installed": False, "original_shape": {}}
    for name in ("/usr/lib/libopencv_shape.so.3.4", "/usr/lib/libopencv_shape.so.3.4.3"):
        path = Path(name)
        if path.exists():
            digest = sha(path)
            summary["original_shape"][name] = {"resolved": str(path.resolve()), "bytes": path.stat().st_size, "sha256": digest, "matches_factory": digest == EXPECTED}
        else:
            summary["original_shape"][name] = {"missing": True}
    base_env = os.environ.copy()
    for name in list(base_env):
        if name.startswith("LD_") or name in ("PYTHONPATH", "PYTHONHOME", "PYTHONFAULTHANDLER"):
            base_env.pop(name, None)
    logs = []
    tests = {}

    def run(name, code, env, timeout=90):
        print("Running " + name + " ...", flush=True)
        try:
            result = subprocess.run([sys.executable, "-I", "-u", "-c", code], env=env, cwd=str(report_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, errors="replace", timeout=timeout)
            status, output = result.returncode, result.stdout
        except subprocess.TimeoutExpired as error:
            output = error.output or b""
            if isinstance(output, bytes):
                output = output.decode("utf-8", "replace")
            status, output = 124, output + "\nTIMEOUT\n"
        tests[name] = {"returncode": status, "log": name + ".log"}
        (report_dir / (name + ".log")).write_text(output, encoding="utf-8")
        logs.append("\n=== " + name + " (exit " + str(status) + ") ===\n" + output)
        print("  exit=" + str(status), flush=True)
        if status == 0:
            print(output, end="", flush=True)
        return status == 0

    def smoke_code(library):
        return "\n".join([
            "import numpy as np",
            "import cv2",
            "print('CV2_OK',cv2.__version__,cv2.__file__)",
            "assert " + repr(str(library)) + " in open('/proc/self/maps').read(), 'Candidate DSO was not selected'",
            "a=np.zeros((64,96,3),dtype=np.uint8)",
            "cv2.rectangle(a,(10,12),(60,44),(255,255,255),-1)",
            "gray=cv2.cvtColor(a,cv2.COLOR_BGR2GRAY)",
            "_,mask=cv2.threshold(gray,127,255,cv2.THRESH_BINARY)",
            "contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)[-2:]",
            "assert contours and max(cv2.contourArea(c) for c in contours)>100",
            "assert cv2.boxPoints(cv2.minAreaRect(contours[0])).shape==(4,2)",
            "assert cv2.resize(a,(48,32)).shape==(32,48,3)",
            "assert cv2.imwrite('opencv_probe.png',a)",
            "assert np.array_equal(cv2.imread('opencv_probe.png'),a)",
            "print('OPENCV_GEOMETRY_AND_PNG_OK')",
        ])

    try:
        staged = base_env.copy()
        staged["LD_LIBRARY_PATH"] = str(ROOT / "payload") + ":" + str(app)
        passed = run("staged_opencv", smoke_code(candidate), staged)
        summary["staged_opencv_pass"] = passed
        if passed and args.install:
            backup = Path(tempfile.mkdtemp(prefix="opencv_shape_backup_", dir=str(app)))
            destination = app / NAME
            if destination.is_symlink():
                (backup / "original_symlink.txt").write_text(os.readlink(str(destination)), encoding="utf-8")
                shutil.copy2(str(destination), str(backup / NAME))
            elif destination.exists():
                shutil.copy2(str(destination), str(backup / NAME))
            temporary = app / (NAME + ".support-new")
            shutil.copyfile(str(candidate), str(temporary))
            if sha(temporary) != EXPECTED:
                raise RuntimeError("Copy verification failed")
            os.replace(str(temporary), str(destination))
            installed = base_env.copy()
            installed["LD_LIBRARY_PATH"] = str(app)
            if not run("installed_opencv", smoke_code(destination), installed):
                saved = backup / NAME
                if (backup / "original_symlink.txt").exists():
                    old_link = app / (NAME + ".restore-link")
                    os.symlink((backup / "original_symlink.txt").read_text(), str(old_link))
                    os.replace(str(old_link), str(destination))
                elif saved.exists():
                    shutil.copyfile(str(saved), str(temporary))
                    os.replace(str(temporary), str(destination))
                else:
                    destination.unlink()
                raise RuntimeError("Installed check failed; application override restored")
            summary["installed"] = True
            summary["backup"] = str(backup)
            print("INSTALLED: " + str(destination), flush=True)
        if not passed:
            diagnostic = staged.copy()
            fault = app / "labmate_board_support_20261018_v2/payload/native_fault.so"
            if fault.is_file():
                diagnostic["LD_PRELOAD"] = str(fault)
            diagnostic["LD_DEBUG"] = "files,reloc"
            run("failed_import_trace", "import cv2; print(cv2.__version__)", diagnostic)
    except Exception as error:
        summary["error"] = type(error).__name__ + ": " + str(error)
        print(summary["error"], flush=True)
    finally:
        summary["tests"] = tests
        content = json.dumps(summary, ensure_ascii=False, indent=2)
        (report_dir / "summary.json").write_text(content, encoding="utf-8")
        (report_dir / "report.txt").write_text(content + "\n" + "\n".join(logs), encoding="utf-8")
        print("\nREPORT=" + str(report_dir / "report.txt"), flush=True)
        print("staged_opencv_pass=" + str(summary.get("staged_opencv_pass", False)), flush=True)
        print("installed=" + str(summary["installed"]), flush=True)
    return 0 if summary.get("staged_opencv_pass") and not summary.get("error") else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("STOP: " + type(error).__name__ + ": " + str(error), file=sys.stderr)
        sys.exit(1)
