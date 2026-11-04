#!/usr/bin/env python3
"""Stage tests, optional local installation, and OpenCV native crash reports."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
LOADER = "/lib/ld-linux-armhf.so.3"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--install", action="store_true", help="Back up and install only after staged tests pass")
    args = parser.parse_args()
    app = args.app.resolve()
    if platform.machine() != "armv7l" or sys.version_info[:2] != (3, 7):
        raise RuntimeError("This package requires the reported ARMv7 Linux / CPython 3.7 board")
    manifest = json.loads((ROOT / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        path = ROOT / name
        if digest(path) != expected:
            raise RuntimeError("Package checksum mismatch: " + name)
    for name in ("libpaddle_light_api_shared.so", "PP-OCRv5_mobile_rec.nb", "rec_input.f32", "alphabet.bin", "rec_expected.json"):
        if not (app / name).is_file():
            raise RuntimeError("Application file missing: " + str(app / name))
    for name in ("smoke_infer", "libgomp.so.1", "native_fault.so"):
        path = PAYLOAD / name
        path.chmod(path.stat().st_mode | 0o500)
    report_dir = Path(tempfile.mkdtemp(prefix="board_report_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_", dir=str(ROOT)))
    summary = {"system": platform.uname()._asdict(), "python": sys.version, "app": str(app), "tests": {}, "installed": False}
    transcript = []

    def run(name, command, environment, timeout=60):
        print("Running " + name + " ...", flush=True)
        try:
            process = subprocess.run(command, cwd=str(report_dir), env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, errors="replace", timeout=timeout)
            result = {"returncode": process.returncode, "output": process.stdout}
        except subprocess.TimeoutExpired as error:
            raw = error.output or b""
            text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
            result = {"returncode": 124, "output": text + "\nTIMEOUT\n"}
        except OSError as error:
            result = {"returncode": 127, "output": str(error)}
        summary["tests"][name] = {"returncode": result["returncode"], "log": name + ".log"}
        (report_dir / (name + ".log")).write_text(result["output"], encoding="utf-8")
        transcript.append("\n=== " + name + " (exit " + str(result["returncode"]) + ") ===\n" + result["output"])
        print("  exit=" + str(result["returncode"]), flush=True)
        return result

    clean = os.environ.copy()
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME", "PYTHONFAULTHANDLER"):
        clean.pop(key, None)
    staged = clean.copy()
    staged["LD_LIBRARY_PATH"] = str(PAYLOAD) + ":" + str(app)
    staged["PYTHONPATH"] = str(PAYLOAD)
    validation = json.loads((ROOT / "STATIC_VALIDATION.json").read_text(encoding="utf-8"))
    file_comparison = {}
    for name, expected in validation["factory_file_sha256"].items():
        path = Path("/" + name.lstrip("./"))
        if path.is_file():
            actual = digest(path)
            file_comparison[str(path)] = {"sha256": actual, "matches_factory": actual == expected}
        else:
            file_comparison[str(path)] = {"missing": True}
    (report_dir / "factory_file_comparison.json").write_text(json.dumps(file_comparison, indent=2), encoding="utf-8")
    summary["factory_file_comparison"] = {"checked": len(file_comparison), "matches": sum(1 for item in file_comparison.values() if item.get("matches_factory")), "different_or_missing": {name: item for name, item in file_comparison.items() if not item.get("matches_factory")}}
    summary["application_lite_sha256"] = digest(app / "libpaddle_light_api_shared.so")
    summary["lite_matches_reviewed"] = summary["application_lite_sha256"] == validation["results"]["libpaddle_light_api_shared.so"]["sha256"]

    try:
        loader_checks = []
        for name, target in (("runner_dependencies", PAYLOAD / "smoke_infer"), ("lite_dependencies", app / "libpaddle_light_api_shared.so")):
            loader_checks.append(run(name, [LOADER, "--library-path", staged["LD_LIBRARY_PATH"], "--list", str(target)], clean)["returncode"] == 0)
        clipper_code = "import pyclipper as p; q=p.PyclipperOffset(); q.AddPath([(0,0),(10,0),(10,10),(0,10)],p.JT_ROUND,p.ET_CLOSEDPOLYGON); r=q.Execute(1); assert r and abs(p.Area(r[0]))>100; print('PYCLIPPER_OK',p.__version__,p.__file__)"
        clipper_ok = run("pyclipper_geometry", [sys.executable, "-u", "-X", "faulthandler", "-c", clipper_code], staged)["returncode"] == 0
        summary["pyclipper_geometry_pass"] = clipper_ok
        usage = run("runner_usage", [str(PAYLOAD / "smoke_infer")], staged)
        loader_checks.append(usage["returncode"] == 2 and "Usage:" in usage["output"])
        if all(loader_checks) and summary["lite_matches_reviewed"]:
            expected = json.loads((app / "rec_expected.json").read_text(encoding="utf-8"))
            result = run("recognition_sample", [str(PAYLOAD / "smoke_infer"), str(app / "PP-OCRv5_mobile_rec.nb"), "1,3,48,320", str(app / "rec_input.f32"), str(report_dir / "rec_output.f32"), str(app / "alphabet.bin")], staged, timeout=240)
            shape = re.search(r"output 0 shape:((?:\s+\d+)+)", result["output"])
            text = re.search(r"^decoded_text=(.*?) score=", result["output"], re.MULTILINE)
            sample_ok = result["returncode"] == 0 and shape is not None and text is not None and [int(value) for value in shape.group(1).split()] == expected["output_shape"] and text.group(1) == expected["text"]
            summary["recognition_sample_pass"] = bool(sample_ok)
            if args.install and sample_ok and clipper_ok:
                backup = Path(tempfile.mkdtemp(prefix="support_backup_", dir=str(app)))
                for name in ("smoke_infer", "libgomp.so.1", "pyclipper"):
                    old = app / name
                    if old.exists():
                        if old.is_dir():
                            shutil.copytree(str(old), str(backup / name))
                        else:
                            shutil.copy2(str(old), str(backup / name))
                for name in ("smoke_infer", "libgomp.so.1"):
                    shutil.copy2(str(PAYLOAD / name), str(app / name))
                if not (app / "pyclipper").exists():
                    shutil.copytree(str(PAYLOAD / "pyclipper"), str(app / "pyclipper"))
                elif (app / "pyclipper").is_dir():
                    for path in (PAYLOAD / "pyclipper").iterdir():
                        if path.is_file():
                            shutil.copy2(str(path), str(app / "pyclipper" / path.name))
                else:
                    raise RuntimeError("app/pyclipper exists but is not a directory; originals backed up at " + str(backup))
                summary["installed"] = True
                summary["backup"] = str(backup)
                print("INSTALLED: smoke_infer, libgomp.so.1, pyclipper; backup=" + str(backup), flush=True)
        else:
            summary["recognition_sample_pass"] = False
            print("Staged dependency checks failed or application Lite library changed; installation skipped.", flush=True)

        run("cv2_origin", [sys.executable, "-I", "-c", "import importlib.util as u; print(u.find_spec('cv2').origin)"], clean)
        diagnostic = clean.copy()
        diagnostic["LD_PRELOAD"] = str(PAYLOAD / "native_fault.so")
        cvfile = "/usr/lib/python3.7/site-packages/cv2.cpython-37m-arm-linux-gnueabi.so"
        run("cv2_dlopen", [sys.executable, "-I", "-u", "-c", "import ctypes; ctypes.CDLL(" + repr(cvfile) + "); print('DLOPEN_OK')"], diagnostic)
        diagnostic["LD_DEBUG"] = "files,reloc"
        cv2_result = run("cv2_import", [sys.executable, "-I", "-u", "-c", "import cv2; print('CV2_OK',cv2.__version__)"], diagnostic)
        summary["opencv_import_pass"] = cv2_result["returncode"] == 0
        run("memory", ["free", "-m"], clean)
    except Exception as error:
        summary["error"] = type(error).__name__ + ": " + str(error)
        print(summary["error"], flush=True)
    finally:
        (report_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (report_dir / "report.txt").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n" + "\n".join(transcript), encoding="utf-8")
        print("\nREPORT=" + str(report_dir / "report.txt"), flush=True)
        print("recognition_sample_pass=" + str(summary.get("recognition_sample_pass", False)), flush=True)
        print("pyclipper_geometry_pass=" + str(summary.get("pyclipper_geometry_pass", False)), flush=True)
        print("installed=" + str(summary["installed"]), flush=True)
        print("opencv_import_pass=" + str(summary.get("opencv_import_pass", False)), flush=True)
    return 0 if summary.get("recognition_sample_pass") and summary.get("opencv_import_pass") and not summary.get("error") else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("STOP: " + type(error).__name__ + ": " + str(error), file=sys.stderr)
        sys.exit(1)
