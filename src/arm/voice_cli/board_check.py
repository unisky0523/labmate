"""Read-only dependency/model check. Run on the board, not in the PC venv."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import struct
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--load-model", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    failures = []
    print("PROJECT", root)
    print("SYSTEM", " ".join(os.uname()) if hasattr(os, "uname") else sys.platform)
    print("PYTHON", sys.version.replace("\n", " "))
    try:
        import numpy
        import wave
        import board_app
        import asr_cli
        print("NUMPY", numpy.__version__)
        print("WAVE", wave.__file__)
        print("APPLICATION_IMPORTS OK")
    except Exception as error:
        failures.append("Python dependencies: %s" % error)
    for name in ("arecord", "aplay", "i2cset"):
        path = shutil.which(name)
        print("TOOL", name, path or "MISSING")
        if path is None:
            failures.append("Missing tool: " + name)
    for name in ("libvosk.so", "lib/libatomic.so.1"):
        try:
            header = (root / name).read_bytes()[:52]
            if header[:6] != b"\x7fELF\x01\x01" or struct.unpack_from("<H", header, 18)[0] != 40:
                raise ValueError("expected 32-bit little-endian ARM ELF")
            print("ARM_LIBRARY", name, "OK")
        except Exception as error:
            failures.append("%s: %s" % (name, error))
    for name in ("am/final.mdl", "conf/mfcc.conf", "graph/HCLr.fst", "graph/Gr.fst",
                 "graph/phones/word_boundary.int", "ivector/final.ie"):
        path = root / "models/vosk-model-small-cn-0.22" / name
        if not path.is_file() or path.stat().st_size == 0:
            failures.append("Missing model file: " + str(path))
    if args.load_model:
        try:
            from asr_backend import BACKEND
            from board_app import load_vosk_model
            model, error = load_vosk_model(root / "models/vosk-model-small-cn-0.22")
            if model is None:
                raise RuntimeError(error)
            print("VOSK_MODEL OK", BACKEND)
        except Exception as error:
            failures.append("Vosk: %s" % error)
    print(json.dumps({"dependency_check": "FAIL" if failures else "PASS",
                      "failures": failures, "microphone_tested": False}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
