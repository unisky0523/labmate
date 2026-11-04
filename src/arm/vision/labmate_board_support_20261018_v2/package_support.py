import ast
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
ast.parse((ROOT / "board_support.py").read_text(encoding="utf-8"), feature_version=(3, 7))
files = [ROOT / name for name in ("board_support.py", "README_CN.md", "SOURCES.md", "STATIC_VALIDATION.json")]
files.extend(path for path in (ROOT / "payload").rglob("*") if path.is_file() and "__pycache__" not in path.parts)
files.extend(path for path in (ROOT / "licenses").iterdir() if path.is_file())
files.extend([ROOT / "sources/native_fault.c", ROOT / "sources/smoke_infer.cc"])
manifest = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}
(ROOT / "PACKAGE_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
files.append(ROOT / "PACKAGE_MANIFEST.json")
archive = ROOT.parent / (ROOT.name + ".zip")
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
    for path in files:
        package.write(path, ROOT.name + "/" + path.relative_to(ROOT).as_posix())
with zipfile.ZipFile(archive) as package:
    assert package.testzip() is None
    for name, expected in manifest.items():
        assert hashlib.sha256(package.read(ROOT.name + "/" + name)).hexdigest() == expected
report = {"archive": str(archive), "bytes": archive.stat().st_size, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "files": len(files), "python37_syntax": "PASS", "zip_crc_and_manifest": "PASS", "board_execution": "NOT_TESTED"}
(ROOT / "PACKAGE_RESULT.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
