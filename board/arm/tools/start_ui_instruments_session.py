"""Restart the board GUI through its permanent backend and little PCM source."""
from datetime import datetime
import glob
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def processes():
    result = []
    for folder in glob.glob('/proc/[0-9]*'):
        try:
            with open(folder + '/cmdline', 'rb') as stream:
                args = stream.read().decode('utf-8', 'replace').split('\0')
            if args[0] in ('./labassistant', 'arecord', 'aplay'):
                result.append((int(Path(folder).name), args[0]))
        except OSError:
            pass
    return result


def main():
    root = Path('/home/root/labmate_ui_test')
    expected = '0f9436a90036db6895746f38c1d2b79d3015965b81b80a50fe583c7a6f639b0f'
    if hashlib.sha256((root/'asr_runtime/board_listen.py').read_bytes()).hexdigest() != expected:
        raise RuntimeError('Permanent little PCM source is not installed; existing GUI left running')
    sys.path.insert(0, str(root))
    from command_executor import CommandExecutor
    from record_store import RecordStore
    store = RecordStore(root/'asr_runtime', root/'data/records')
    CommandExecutor.from_file(root/'instruments.json', store)
    launcher = (root/'run_ui_voice.sh').read_text(encoding='utf-8')
    if 'export LABMATE_BACKEND=/home/root/labmate_ui_test/backend.py' not in launcher:
        raise RuntimeError('Unexpected backend entry; existing GUI left running')
    previous = []
    for pid, name in processes():
        if name == './labassistant':
            if Path(os.readlink('/proc/%d/cwd' % pid)) != root:
                raise RuntimeError('Different assistant owns display; existing GUI left running')
            previous.append(pid)
    for pid in previous:
        os.kill(pid, signal.SIGTERM)
    for _ in range(80):
        if not processes():
            break
        time.sleep(0.25)
    else:
        raise RuntimeError('Previous audio process has not closed; new session not started')
    log = root/'launch_instruments_20261102.log'
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    with log.open('ab') as output:
        process = subprocess.Popen(['sh', str(root/'run_ui_instruments.sh')], cwd=str(root),
                                   stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                   env=environment, start_new_session=True)
    time.sleep(3)
    if process.poll() is not None:
        raise RuntimeError('New launcher exited: ' + log.read_text(errors='replace')[-3000:])
    report = dict(pid=process.pid, previous_gui_pids=previous,
                  backend=str(root/'backend.py'), launcher=str(root/'run_ui_instruments.sh'),
                  pcm='permanent_little', source_sha256=expected,
                  started_at=datetime.now().astimezone().isoformat(), log=str(log))
    (root/'data/instrument_session.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('__LM_INSTRUMENT_SESSION__=' + json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
