"""Build and simulate a version-checked board update for command grammar."""
import ast
import base64
import contextlib
import difflib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work/command_grammar_20261022"
OUT.mkdir(parents=True, exist_ok=True)
digest = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()
payload = []
sources = {}
for name in ("asr_cli.py", "board_app.py"):
    old = (ROOT / "backups/before_command_grammar_20261022" / name).read_text(encoding="utf-8")
    new = (Path("D:/labmate_b") / name).read_text(encoding="utf-8")
    ast.parse(new, feature_version=(3, 7))
    ops = [(i, j, new[k:l]) for tag, i, j, k, l in
           difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes() if tag != "equal"]
    payload.append(dict(name=name, old=digest(old), new=digest(new), ops=ops))
    sources[name] = (old, new)

script = '''import ast,hashlib,json
from pathlib import Path
items=json.loads(PAYLOAD)
root=Path('/home/root/labmate_b_audio_test')
digest=lambda s: hashlib.sha256(s.encode('utf-8')).hexdigest()
changes=[]
for item in items:
 p=root/item['name']
 raw=p.read_bytes()
 s=raw.decode('utf-8').replace('\\r\\n','\\n')
 if digest(s)==item['new']: continue
 assert digest(s)==item['old'], 'VERSION_MISMATCH: '+item['name']+'; no files changed'
 for a,b,t in reversed(item['ops']): s=s[:a]+t+s[b:]
 assert digest(s)==item['new'], 'PATCH_CHECK_FAILED'
 ast.parse(s)
 backup=p.with_name(p.name+'.before_command_'+item['old'][:8]+'.bak')
 assert not backup.exists() or backup.read_bytes()==raw, 'BACKUP_MISMATCH'
 temp=p.with_name(p.name+'.command.tmp')
 assert not temp.exists(), 'TEMP_EXISTS: '+str(temp)
 changes.append((p,raw,s,backup,temp))
replaced=[]
try:
 for p,raw,s,backup,temp in changes:
  if not backup.exists():
   with backup.open('xb') as f: f.write(raw)
  print('BACKUP',backup)
  with temp.open('xb') as f: f.write(s.encode('utf-8'))
 for p,raw,s,backup,temp in changes:
  temp.replace(p)
  replaced.append((p,raw))
except Exception:
 for p,raw in reversed(replaced): p.write_bytes(raw)
 for p,raw,s,backup,temp in changes:
  if temp.exists(): temp.unlink()
 raise
print('COMMAND_MODE_OK' if changes else 'COMMAND_MODE_ALREADY_INSTALLED')
'''.replace("PAYLOAD", repr(json.dumps(payload, ensure_ascii=True)))
ast.parse(script, feature_version=(3, 7))
with tempfile.TemporaryDirectory(prefix="check_", dir=str(OUT.resolve())) as directory:
    fixture = Path(directory).resolve()
    assert fixture.parent == OUT.resolve()
    trial = script.replace("Path('/home/root/labmate_b_audio_test')", "Path(" + repr(str(fixture)) + ")")
    for name, (old, new) in sources.items():
        (fixture / name).write_bytes(old.encode())
    with contextlib.redirect_stdout(io.StringIO()) as log:
        exec(compile(trial, "installer", "exec"), {})
        for name, (old, new) in sources.items():
            assert (fixture / name).read_text(encoding="utf-8") == new
            backup = fixture / (name + ".before_command_" + digest(old)[:8] + ".bak")
            assert backup.read_bytes() == old.encode()
        exec(compile(trial, "installer", "exec"), {})
    assert "COMMAND_MODE_OK" in log.getvalue()
    assert "COMMAND_MODE_ALREADY_INSTALLED" in log.getvalue()
    # A mismatch in the second file must leave the first original untouched.
    (fixture / "asr_cli.py").write_bytes(sources["asr_cli.py"][0].encode())
    (fixture / "board_app.py").write_bytes(b"# changed version\n")
    try:
        exec(compile(trial, "installer", "exec"), {})
    except AssertionError as error:
        assert "VERSION_MISMATCH" in str(error)
    else:
        raise AssertionError("version guard not enforced")
    assert (fixture / "asr_cli.py").read_text(encoding="utf-8") == sources["asr_cli.py"][0]

encoded = base64.b64encode(zlib.compress(script.encode(), 9)).decode()
command = 'python3 -c "import base64,zlib;exec(zlib.decompress(base64.b64decode(\'' + encoded + '\')))"'
assert len(command) < 3900, len(command)
(OUT / "install_board_command.txt").write_text(command + "\n", encoding="ascii")
(OUT / "installer.py").write_text(script, encoding="utf-8")
(OUT / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps({"command_length": len(command), "simulation": "PASS", "command_file": str(OUT / "install_board_command.txt")}))
