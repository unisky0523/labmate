"""Run on the board: real USB with explicit text commands, no microphone use.

Acceptance records live outside ordinary experiment history. This is not a
speech-recognition accuracy test or a panel/measurement-accuracy calibration.
"""
import base64
from datetime import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import queue
import sys
import threading
import uuid


def main():
    root = Path('/home/root/labmate_ui_test')
    sys.path.insert(0, str(root))
    from backend import Backend
    from command_executor import CommandExecutor
    from record_store import RecordStore
    folder = root/'data'/('instrument_acceptance_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    store = RecordStore(root/'asr_runtime', folder/'records')
    executor = CommandExecutor.from_file(root/'instruments.json', store)
    executor.directory = folder/'receipts'
    messages = queue.Queue()
    requests = queue.Queue()
    events = []
    commands = iter([
        dict(text='读取数据（文字联调，随后取消）', command=dict(intent='read')),
        dict(text='记录数据（文字联调）', command=dict(intent='record_device', count=1)),
        dict(text='拍一下波形（文字联调，保存示波器屏幕截图）', command=dict(intent='capture_image')),
    ])

    class Recognizer:
        def prepare(self, shutdown, progress):
            pass

        def recognize(self, cancelled, progress):
            return dict(next(commands), simulated=False, reason=None)

        def close(self):
            pass

    class Input:
        def readline(self, *args):
            return requests.get()

    class Output:
        def write(self, text):
            value = json.loads(text)
            events.append(value)
            messages.put(value)

        def flush(self):
            pass

    backend = Backend(Output(), recognizer=Recognizer(), record_store=store, command_executor=executor)
    worker = threading.Thread(target=backend.run, args=(Input(),))
    worker.start()

    def send(action, operation=None, target=None):
        requests.put(json.dumps(dict(protocol=1, id=operation or uuid.uuid4().hex,
                                     action=action, target=target))+'\n')

    def take(expected):
        while True:
            event = messages.get(timeout=80)
            if event['event'] in ('error', 'fatal', 'rejected'):
                raise RuntimeError(json.dumps(event, ensure_ascii=True))
            if event['event'] == expected:
                return event

    try:
        take('ready')
        send('start', 'acceptance-read-' + uuid.uuid4().hex)
        preview = take('result')
        send('cancel', target=preview['operation_id'])
        take('cancelled')
        if store.list_page()['total'] != 0:
            raise RuntimeError('cancelled preview unexpectedly wrote experiment history')
        saved = []
        for label in ('readings', 'screen'):
            operation = 'acceptance-' + label + '-' + uuid.uuid4().hex
            send('start', operation)
            take('result')
            send('confirm', target=operation)
            saved.append(take('confirmed')['record'])
        history = store.list_page(0, 4)
        if history['total'] != 2:
            raise RuntimeError('expected two archived instrument results')
        records = [json.loads(path.read_text(encoding='utf-8')) for path in sorted((folder/'records').glob('record_*.json'))]
        result = dict(test_kind='explicit_text_real_usb', directory=str(folder),
                      cancelled_preview_history_count=0, saved=saved, history=history,
                      records=records, events=events)
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        result['files'] = {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
                           for name in ('backend.py', 'record_store.py', 'instrument_adapter.py', 'command_executor.py',
                                        'instruments.json', 'asr_adapter.py', 'asr_runtime/board_listen.py')}
        print('__LM_INSTRUMENT_ACCEPTANCE__=' + base64.b64encode(gzip.compress(
            json.dumps(result, ensure_ascii=False).encode('utf-8'))).decode('ascii'), flush=True)
    finally:
        requests.put('')
        worker.join(90)
        if worker.is_alive():
            raise RuntimeError('backend did not close')


if __name__ == '__main__':
    main()
