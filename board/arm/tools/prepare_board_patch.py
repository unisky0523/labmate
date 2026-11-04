"""Build a small, hash-checked update for the confirmed board directory."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import zlib

WORKSPACE = Path(__file__).resolve().parents[1]
SOURCE = Path(r"D:\labmate_b")
ORIGINAL = WORKSPACE / "backups/board_original_20261021"
NAMES = ["board_mic.py", "board_app.py", "asr_cli.py", "vosk_lite.py",
         "run_board.sh", "README_board.md", "board_check.py"]
files = {name: (SOURCE / name).read_text(encoding="utf-8") for name in NAMES}
previous = {name: hashlib.sha256((ORIGINAL / name).read_text(encoding="utf-8").encode()).hexdigest()
            for name in NAMES if (ORIGINAL / name).is_file()}
bundle = json.dumps({"files": files, "previous": previous}, ensure_ascii=False).encode()
compressed = zlib.compress(bundle, 9)
digest = hashlib.sha256(compressed).hexdigest()
installer = '''import base64,hashlib,json,pathlib,shutil,zlib
root=pathlib.Path('/media/sd-mmcblk0p1/labmate_b_board_20261015')
data=base64.b64decode(pathlib.Path('/tmp/labmate_patch_20261021.b64').read_text())
assert hashlib.sha256(data).hexdigest()==DIGEST, 'upload SHA256 mismatch'
bundle=json.loads(zlib.decompress(data).decode('utf-8'))
assert (root/'board_app.py').is_file(), 'confirmed board directory is missing'
for name,expected in bundle['previous'].items():
    assert hashlib.sha256((root/name).read_text().encode()).hexdigest()==expected, 'board file changed: '+name
backup=root/'backup_before_20261021_serial_fix'
assert not backup.exists(), 'backup already exists; inspect before retrying'
backup.mkdir()
for name,text in bundle['files'].items():
    path=root/name
    if path.exists():
        shutil.copy2(str(path),str(backup/name))
    temporary=path.with_name(path.name+'.new_20261021')
    temporary.write_text(text,encoding='utf-8')
    temporary.replace(path)
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual==hashlib.sha256(text.encode()).hexdigest(), 'write mismatch: '+name
    print('UPDATED',name,actual)
print('DEPLOY_OK',root)
print('BACKUP',backup)
'''.replace("DIGEST", repr(digest))
installer64 = base64.b64encode(zlib.compress(installer.encode(), 9)).decode()
encoded = base64.b64encode(compressed).decode()
commands = ["python3 -c " + shlex.quote("import base64,zlib;open('/tmp/labmate_patch_20261021.b64','w').close();print('UPLOAD_CODEC_OK')")]
for offset in range(0, len(encoded), 512):
    code = "open('/tmp/labmate_patch_20261021.b64','a').write(%r)" % encoded[offset:offset + 512]
    commands.append("python3 -c " + shlex.quote(code))
code = "import base64,zlib;exec(zlib.decompress(base64.b64decode(%r)))" % installer64
commands.append("python3 -c " + shlex.quote(code))
command_file = WORKSPACE / "tmp/board_upload_20261021.cmd"
command_file.write_text("\n".join(commands) + "\n", encoding="utf-8", newline="\n")
(WORKSPACE / "dist/labmate_patch_20261021.json").write_bytes(bundle)
print("Update files:", ", ".join(NAMES))
print("Compressed bytes:", len(compressed), "SHA256:", digest)
print("Commands:", len(commands), "Longest line:", max(map(len, commands)))
print(command_file)
