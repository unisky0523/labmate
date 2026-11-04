"""Fetch official source inputs and prepare headers for ARM cross compilation."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources"
BUILD = ROOT / "build"
ROOTFS = Path(r"D:\学科文件\大三上\FPGA创新赛\tmp\audio_source_review\资源文件\出厂镜像相关\rootfs.tar.gz")
records = []


def fetch(url, name, expected=None):
    target = SOURCES / name
    if not target.exists():
        with urllib.request.urlopen(url, timeout=60) as response:
            target.write_bytes(response.read())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if expected and digest != expected:
        raise RuntimeError("SHA256 mismatch: " + name)
    records.append({"url": url, "file": name, "sha256": digest})
    return target


fetch("https://raw.githubusercontent.com/PaddlePaddle/Paddle-Lite/v2.14-rc/lite/api/paddle_api.h", "paddle_api.h")
fetch("https://raw.githubusercontent.com/PaddlePaddle/Paddle-Lite/v2.14-rc/lite/api/paddle_place.h", "paddle_place.h")
python_source = fetch("https://www.python.org/ftp/python/3.7.6/Python-3.7.6.tgz", "Python-3.7.6.tgz")
with urllib.request.urlopen("https://pypi.org/pypi/pyclipper/1.3.0.post5/json", timeout=30) as response:
    package_metadata = json.load(response)
sdist = next(item for item in package_metadata["urls"] if item["packagetype"] == "sdist")
clipper_source = fetch(sdist["url"], sdist["filename"], sdist["digests"]["sha256"])


def copy_member(archive, member, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.extractfile(member) as source:
        destination.write_bytes(source.read())


with tarfile.open(python_source) as archive:
    prefix = "Python-3.7.6/Include/"
    for member in archive.getmembers():
        if member.isfile() and member.name.startswith(prefix):
            relative = Path(member.name[len(prefix):])
            if ".." in relative.parts or relative.is_absolute():
                raise RuntimeError("Unsafe archive path")
            copy_member(archive, member, BUILD / "python-include" / relative)
    copy_member(archive, archive.getmember("Python-3.7.6/LICENSE"), SOURCES / "CPython-LICENSE")

with tarfile.open(ROOTFS) as archive:
    for filename in ("pyconfig.h", "pyconfig-32.h"):
        copy_member(archive, archive.getmember("./usr/include/python3.7m/" + filename), BUILD / "python-include" / filename)

with tarfile.open(clipper_source) as archive:
    prefix = "pyclipper-1.3.0.post5/"
    for member in archive.getmembers():
        if not member.isfile() or not member.name.startswith(prefix):
            continue
        relative = Path(member.name[len(prefix):])
        if ".." in relative.parts or relative.is_absolute():
            raise RuntimeError("Unsafe archive path")
        copy_member(archive, member, BUILD / "pyclipper-source" / relative)

(SOURCES / "download_manifest.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
print("Prepared official Paddle-Lite v2.14-rc, CPython 3.7.6 and pyclipper 1.3.0.post5 source inputs.")
