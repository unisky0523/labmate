"""Generate a guarded one-line board patch; never changes board files on PC."""
import ast
import base64
import difflib
import hashlib
import json
import contextlib
import io
from pathlib import Path
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
old = (ROOT / "backups/before_pcm_msb24_20261022/board_mic.py").read_text(encoding="utf-8")
new = Path("D:/labmate_b/board_mic.py").read_text(encoding="utf-8")
ast.parse(new, feature_version=(3, 7))
digest = lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
operations = [(i1, i2, new[j1:j2]) for tag, i1, i2, j1, j2 in
              difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
              if tag != "equal"]
payload = {"old": digest(old), "new": digest(new), "operations": operations}
script = '''import ast,hashlib,json
from pathlib import Path
info=json.loads(PAYLOAD)
p=Path('/home/root/labmate_b_audio_test/board_mic.py')
raw=p.read_bytes()
s=raw.decode('utf-8').replace('\\r\\n','\\n')
h=lambda t: hashlib.sha256(t.encode('utf-8')).hexdigest()
if h(s)==info['new']:
 print('PCM_FIX_ALREADY_INSTALLED')
else:
 assert h(s)==info['old'], 'VERSION_MISMATCH: no files changed; send this output'
 for start,end,replacement in reversed(info['operations']):
  s=s[:start]+replacement+s[end:]
 assert h(s)==info['new'], 'PATCH_CHECK_FAILED'
 ast.parse(s)
 backup=p.with_name('board_mic.py.before_msb24_'+info['old'][:8]+'.bak')
 if backup.exists():
  assert backup.read_bytes()==raw, 'BACKUP_MISMATCH'
 else:
  with backup.open('xb') as f: f.write(raw)
 temp=p.with_name('board_mic.py.msb24.tmp')
 with temp.open('xb') as f: f.write(s.encode('utf-8'))
 temp.replace(p)
 print('BACKUP',backup)
 print('PCM_FIX_OK')
'''.replace('PAYLOAD', repr(json.dumps(payload, ensure_ascii=True)))
ast.parse(script, feature_version=(3, 7))
encoded = base64.b64encode(zlib.compress(script.encode(), 9)).decode()
command = 'python3 -c "import base64,zlib;exec(zlib.decompress(base64.b64decode(\'' + encoded + '\')))"'
assert len(command) < 3900, len(command)
out = ROOT / "work/pcm_fix_20261022"
out.mkdir(parents=True, exist_ok=True)
(out / "install_board_command.txt").write_text(command + "\n", encoding="ascii")
(out / "board_patch_source.py").write_text(script, encoding="utf-8")
(out / "patch_manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
# Reconstruct independently and verify before handing it to the user.
reconstructed = old
for start, end, replacement in reversed(operations):
    reconstructed = reconstructed[:start] + replacement + reconstructed[end:]
assert reconstructed == new
# Exercise the exact installer against an isolated fixture, including guards.
with tempfile.TemporaryDirectory(prefix="labmate_patch_check_", dir=str(out.resolve())) as directory:
    assert Path(directory).resolve().parent == out.resolve()
    fixture = Path(directory) / "board_mic.py"
    fixture.write_bytes(old.encode("utf-8"))
    trial = script.replace("Path('/home/root/labmate_b_audio_test/board_mic.py')",
                           "Path(" + repr(str(fixture)) + ")")
    with contextlib.redirect_stdout(io.StringIO()) as log:
        exec(compile(trial, "board_patch_source.py", "exec"), {})
        assert fixture.read_text(encoding="utf-8") == new
        assert fixture.with_name("board_mic.py.before_msb24_" + digest(old)[:8] + ".bak").read_bytes() == old.encode("utf-8")
        exec(compile(trial, "board_patch_source.py", "exec"), {})
    assert "PCM_FIX_OK" in log.getvalue()
    assert "PCM_FIX_ALREADY_INSTALLED" in log.getvalue()
    fixture.write_text("# different version\n", encoding="utf-8")
    try:
        exec(compile(trial, "board_patch_source.py", "exec"), {})
    except AssertionError as error:
        assert "VERSION_MISMATCH" in str(error)
    else:
        raise AssertionError("Expected version mismatch")
    assert fixture.read_text(encoding="utf-8") == "# different version\n"
print(json.dumps({"command_length": len(command), "old_sha256": digest(old),
                  "new_sha256": digest(new), "command_file": str(out / "install_board_command.txt")}))
