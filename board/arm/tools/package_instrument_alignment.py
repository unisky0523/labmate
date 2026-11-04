"""Package the installed instrument/PCM update without replacing old releases."""
import difflib
import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
ui = root/'work/labmate_ui'
evidence = root/'work/instrument_alignment_20261102'
backup = Path((evidence/'baseline_backup.txt').read_text(encoding='utf-8'))
report = root/'docs/语音与仪表对齐_改动与验收_20261102.md'
tools = ['upload_ui_serial.ps1', 'ui_serial_receiver.py', 'run_ui_voice.sh',
         'run_ui_instruments.sh', 'run_ui_test.sh', 'restore_ui_voice_baseline.py',
         'audit_ui_voice.py', 'check_ui_voice_serial.ps1', 'board_serial_command.ps1',
         'verify_instruments_board.py', 'start_ui_instruments_session.py',
         'read_instrument_status.py', 'package_instrument_alignment.py']
patch = {name: ui/name for name in ('backend.py', 'record_store.py', 'instrument_adapter.py',
         'command_executor.py', 'instruments.json', 'asr_runtime/board_listen.py')}
patch.update({name: root/'tools'/name for name in ('run_ui_voice.sh', 'run_ui_instruments.sh')})
source = {p.relative_to(root).as_posix(): p for p in ui.rglob('*')
          if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
source.update({'tools/'+name: root/'tools'/name for name in tools})
source[report.relative_to(root).as_posix()] = report
diff = []
changes = []
for name, path in sorted(source.items()):
    previous = backup/name
    old = previous.read_bytes() if previous.is_file() else b''
    new = path.read_bytes()
    if old != new:
        changes.append(dict(path=name, change='modified' if previous.is_file() else 'added',
                            sha256=hashlib.sha256(new).hexdigest()))
        diff.extend(difflib.unified_diff(old.decode('utf-8-sig').splitlines(True),
                    new.decode('utf-8-sig').splitlines(True), fromfile='before/'+name, tofile='after/'+name))
(evidence/'changes.diff').write_text(''.join(diff), encoding='utf-8')
(evidence/'changed_files.json').write_text(json.dumps(changes, ensure_ascii=False, indent=2), encoding='utf-8')
for stem, files in (('labmate_ui_instruments_20261102', patch),
                    ('labmate_ui_instruments_source_20261102', source)):
    destination = root/'dist'/(stem+'.zip')
    payloads = {name: path.read_bytes() for name, path in files.items()}
    manifest = {name: hashlib.sha256(content).hexdigest() for name, content in payloads.items()}
    payloads['MANIFEST_SHA256.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(payloads.items()):
            archive.writestr(name, content)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Archive CRC check failed')
        for name, digest in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise RuntimeError('Archive hash mismatch: '+name)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.zip.sha256').write_text(digest+'  '+destination.name+'\n', encoding='ascii')
    print(destination.name, destination.stat().st_size, 'bytes', len(files), 'files; CRC/SHA256 OK')
