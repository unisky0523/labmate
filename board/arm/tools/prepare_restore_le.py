"""Guarded single-file LE restoration plus saved-audio verification."""
import ast
import base64
import contextlib
import difflib
import hashlib
import io
import json
from pathlib import Path
import runpy
import tempfile
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/restore_le_20261022'
OUT.mkdir(parents=True, exist_ok=True)
old = (ROOT / 'backups/before_restore_le_20261022/board_mic.py').read_text(encoding='utf-8')
new = Path('D:/labmate_b/board_mic.py').read_text(encoding='utf-8')
verify = (ROOT / 'tools/verify_saved_le_audio.py').read_text(encoding='utf-8')
for source in (new, verify):
    ast.parse(source, feature_version=(3, 7))
digest = lambda value: hashlib.sha256(value.encode()).hexdigest()
ops = [(a, b, new[c:d]) for tag, a, b, c, d in
       difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes() if tag != 'equal']
payload = {'old': digest(old), 'new': digest(new), 'ops': ops, 'verify': verify}
encoded = base64.b64encode(zlib.compress(json.dumps(payload, ensure_ascii=True).encode(), 9)).decode()
lines = ['import ast,base64,hashlib,json,runpy,zlib', 'from pathlib import Path', 'parts=[']
lines += [repr(encoded[index:index + 1500]) + ',' for index in range(0, len(encoded), 1500)]
lines += [']']
installer = '\n'.join(lines) + '''
info=json.loads(zlib.decompress(base64.b64decode(''.join(parts))))
root=Path('/home/root/labmate_b_audio_test')
p=root/'board_mic.py'
raw=p.read_bytes()
s=raw.decode('utf-8').replace('\\r\\n','\\n')
digest=lambda value: hashlib.sha256(value.encode()).hexdigest()
if digest(s)!=info['new']:
 assert digest(s)==info['old'], 'VERSION_MISMATCH: no files changed'
 for a,b,t in reversed(info['ops']): s=s[:a]+t+s[b:]
 assert digest(s)==info['new'], 'PATCH_CHECK_FAILED'
 ast.parse(s)
 backup=p.with_name('board_mic.py.before_restore_le_'+info['old'][:8]+'.bak')
 assert not backup.exists() or backup.read_bytes()==raw, 'BACKUP_MISMATCH'
 if not backup.exists():
  with backup.open('xb') as stream: stream.write(raw)
 temp=p.with_name('board_mic.py.restore_le.tmp')
 with temp.open('xb') as stream: stream.write(s.encode('utf-8'))
 temp.replace(p)
 print('BACKUP',backup,flush=True)
print('LE_RESTORE_OK',flush=True)
tool_root=Path('/home/root/labmate_audio_debug')
tool_root.mkdir(parents=True,exist_ok=True)
tool=tool_root/('verify_saved_le_'+digest(info['verify'])[:10]+'.py')
if tool.exists(): assert tool.read_bytes()==info['verify'].encode('utf-8'), 'VERIFY_TOOL_MISMATCH'
else:
 with tool.open('xb') as stream: stream.write(info['verify'].encode('utf-8'))
runpy.run_path(str(tool),run_name='__main__')
'''
ast.parse(installer, feature_version=(3, 7))
with tempfile.TemporaryDirectory(prefix='check_', dir=str(OUT.resolve())) as directory:
    fixture = Path(directory).resolve()
    assert fixture.parent == OUT.resolve()
    (fixture / 'project').mkdir()
    path = fixture / 'project/board_mic.py'
    path.write_bytes(old.encode())
    trial = installer.replace("Path('/home/root/labmate_b_audio_test')", "Path(" + repr(str(fixture / 'project')) + ")")
    trial = trial.replace("Path('/home/root/labmate_audio_debug')", "Path(" + repr(str(fixture / 'diagnostic')) + ")")
    with patch.object(runpy, 'run_path') as run, contextlib.redirect_stdout(io.StringIO()):
        exec(compile(trial, 'installer', 'exec'), {})
        assert path.read_text(encoding='utf-8') == new
        assert path.with_name('board_mic.py.before_restore_le_' + digest(old)[:8] + '.bak').read_bytes() == old.encode()
        tool = Path(run.call_args.args[0])
        assert tool.read_text(encoding='utf-8') == verify
        exec(compile(trial, 'installer', 'exec'), {})
        assert run.call_count == 2
        path.write_bytes(b'# altered source\n')
        try:
            exec(compile(trial, 'installer', 'exec'), {})
        except AssertionError as error:
            assert 'VERSION_MISMATCH' in str(error)
        else:
            raise AssertionError('Version guard failed')
        assert path.read_bytes() == b'# altered source\n'
        assert run.call_count == 2
command = '''LD_LIBRARY_PATH="/home/root/labmate_b_audio_test/lib:/home/root/labmate_b_audio_test${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" PYTHONIOENCODING=utf-8 python3 - <<'PY'
''' + installer + '\nPY\n'
assert max(map(len, command.splitlines())) < 2000
(OUT / 'restore_and_verify_board_command.txt').write_text(command, encoding='ascii')
(OUT / 'manifest.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
print(json.dumps({'simulation': 'PASS', 'old_sha256': digest(old), 'new_sha256': digest(new),
                  'command_file': str(OUT / 'restore_and_verify_board_command.txt')}))
