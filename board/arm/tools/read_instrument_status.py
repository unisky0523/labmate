"""Read-only board deployment and recent instrument-record evidence."""
import base64
import glob
import gzip
import hashlib
import json
from pathlib import Path


root = Path('/home/root/labmate_ui_test')
report = dict(processes=[], files={}, records=[], session=None)
for name in ('backend.py', 'record_store.py', 'instrument_adapter.py', 'command_executor.py',
             'instruments.json', 'run_ui_voice.sh', 'run_ui_instruments.sh',
             'asr_adapter.py', 'asr_runtime/board_listen.py'):
    path = root/name
    report['files'][name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
session = root/'data/instrument_session.json'
if session.exists():
    report['session'] = json.loads(session.read_text(encoding='utf-8'))
for folder in glob.glob('/proc/[0-9]*'):
    try:
        with open(folder+'/cmdline', 'rb') as stream:
            args = stream.read().decode('utf-8', 'replace').split('\0')
        if (args[0] in ('./labassistant', 'arecord', 'aplay') or
                (len(args) > 2 and args[0].endswith('python3') and
                 args[1] == '-u' and args[2].startswith(str(root)))):
            with open(folder+'/environ', 'rb') as stream:
                values = stream.read().split(b'\0')
            report['processes'].append(dict(pid=int(Path(folder).name), args=args,
                environment=[x.decode('utf-8', 'replace') for x in values if x.startswith(b'LABMATE_')]))
    except OSError:
        pass
for path in sorted((root/'data/records').glob('record_*.json'),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:8]:
    try:
        report['records'].append(dict(path=str(path), document=json.loads(path.read_text(encoding='utf-8'))))
    except (OSError, ValueError):
        pass
print('__LM_INSTRUMENT_STATUS__=' + base64.b64encode(gzip.compress(
    json.dumps(report, ensure_ascii=False).encode('utf-8'))).decode('ascii'), flush=True)
