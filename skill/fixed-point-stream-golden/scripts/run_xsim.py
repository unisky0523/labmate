#!/usr/bin/env python3
"""Run the bundled fixed-point streaming regression with AMD XSim."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vivado-bin", type=Path, required=True, help="Vivado bin directory")
    bin_dir = parser.parse_args().vivado_bin.resolve()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="stream-golden-") as temp:
        work = Path(temp)
        shutil.copytree(root / "rtl", work / "rtl")
        for name in ("input.hex", "expected.hex", "tb_frontend.sv"):
            shutil.copy2(root / "tests" / name, work / name)

        def run(tool, *options):
            executable = bin_dir / (tool + (".bat" if os.name == "nt" else ""))
            result = subprocess.run([str(executable), *options], cwd=work, check=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, errors="replace")
            print(result.stdout, end="", flush=True)
            return result.stdout

        run("xvlog", "-sv", "-i", "rtl", "rtl/asr_audio_frontend.v", "tb_frontend.sv")
        for bypass in (0, 1):
            snapshot = f"frontend_{bypass}"
            run("xelab", f"tb_mode{bypass}", "-s", snapshot)
            log = run("xsim", snapshot, "-runall")
            epochs = re.findall(rf"^PASS BYPASS=\s*{bypass}\s+epoch=\s*([01])\s+samples=\s*6000\s*$", log, re.M)
            if epochs != ["0", "1"] or "Fatal:" in log or "ERROR:" in log:
                raise SystemExit(f"Mode {bypass} did not pass both epochs")
        print("PASS: 2 modes x 2 epochs x 6000 samples")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(error.stdout or "", end="")
        raise SystemExit(error.returncode)
