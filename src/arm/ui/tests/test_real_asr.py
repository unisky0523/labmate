"""Real-mode lifecycle/protocol checks with injected hardware, not ASR accuracy."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import Backend
from asr_adapter import BoardRecognizer


class QueueInput:
    def __init__(self):
        self.queue = queue.Queue()

    def readline(self, *args):
        return self.queue.get(timeout=4)


class QueueOutput:
    def __init__(self):
        self.queue = queue.Queue()

    def write(self, text):
        self.queue.put(json.loads(text))

    def flush(self):
        pass


class FakeRecognizer:
    def __init__(self, outcome='ok'):
        self.outcome = outcome
        self.calls = []

    def prepare(self, shutdown, progress):
        self.calls.append(('prepare', threading.get_ident()))
        progress('loading')
        if self.outcome == 'slow_prepare':
            shutdown.wait(2)
        if self.outcome == 'prepare_error':
            raise RuntimeError('missing model')

    def recognize(self, cancelled, progress):
        self.calls.append(('recognize', threading.get_ident()))
        progress('speak')
        # Deliberately finish after cancellation to test stale-result filtering.
        time.sleep(0.08)
        if self.outcome == 'error':
            raise RuntimeError('capture failed')
        return dict(text='记录电压三点三伏', summary='3.3 V', simulated=False,
                    command=None if self.outcome == 'reject' else {'intent': 'record_manual'},
                    reason='low confidence' if self.outcome == 'reject' else None,
                    _capture={'audio': object(), 'metadata': {}})

    def close(self):
        self.calls.append(('close', threading.get_ident()))


class RealProtocolTests(unittest.TestCase):
    def setUp(self):
        self.input = QueueInput()
        self.output = QueueOutput()
        self.thread = None

    def launch(self, outcome='ok'):
        self.engine = FakeRecognizer(outcome)
        self.backend = Backend(self.output, recognizer=self.engine)
        self.thread = threading.Thread(target=self.backend.run, args=(self.input,))
        self.thread.start()
        self.take('progress')
        self.take('progress')
        return self.take('fatal' if outcome == 'prepare_error' else 'ready')

    def take(self, event):
        message = self.output.queue.get(timeout=3)
        self.assertEqual(message['event'], event, message)
        self.assertEqual(message['mode'], 'asr')
        return message

    def send(self, action, request_id, target=None):
        self.input.queue.put(json.dumps(dict(protocol=1, id=request_id, action=action,
                                             target=target)) + '\n')

    def start(self, name):
        self.send('start', name)
        self.assertEqual(self.take('state')['operation_id'], name)
        self.take('progress')

    def tearDown(self):
        if self.thread is not None:
            self.input.queue.put('')
            self.thread.join(3)
            self.assertFalse(self.thread.is_alive())
            self.assertEqual([x[0] for x in self.engine.calls].count('close'), 1)
            self.assertEqual(len({x[1] for x in self.engine.calls}), 1)

    def test_model_and_microphone_owner_reused_and_unconfigured_save_keeps_result(self):
        self.launch()
        for index in range(2):
            name = 'round-%d' % index
            self.start(name)
            result = self.take('result')
            self.assertFalse(result['simulated'])
            self.assertNotIn('_capture', result)
            self.send('confirm', 'confirm-%d' % index, name)
            self.assertEqual(self.take('state')['state'], 'saving')
            failed = self.take('error')
            self.assertEqual((failed['code'], failed['state']), ('save_failed', 'pending'))
            self.send('cancel', 'cancel-%d' % index, name)
            self.take('cancelled')
        self.assertEqual([x[0] for x in self.engine.calls].count('prepare'), 1)

    def test_cancel_during_decode_drops_old_result_and_serializes_next_round(self):
        self.launch()
        self.start('old')
        self.send('cancel', 'cancel-old', 'old')
        self.take('cancelled')
        self.send('start', 'new')
        self.take('state')
        self.take('progress')
        self.assertEqual(self.take('result')['operation_id'], 'new')

    def test_invalid_recognition_keeps_text_but_disables_confirmation(self):
        self.launch('reject')
        self.start('invalid')
        rejected = self.take('rejected')
        self.assertEqual(rejected['text'], '记录电压三点三伏')
        self.assertEqual(rejected['state'], 'idle')
        self.assertNotIn('_capture', rejected)
        self.assertIsNone(self.backend.result)
        self.send('confirm', 'try-confirm', 'invalid')
        self.assertEqual(self.take('error')['code'], 'wrong_target')

    def test_initialization_failure_is_fatal_and_cleans_up(self):
        self.assertEqual(self.launch('prepare_error')['state'], 'failed')

    def test_capture_failure_does_not_leave_pending_result(self):
        self.launch('error')
        self.start('broken')
        self.assertEqual(self.take('error')['state'], 'idle')

    def test_quit_cancels_work_and_closes_owner(self):
        self.launch()
        self.start('closing')
        self.send('quit', 'quit')
        self.take('stopped')
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())

    def test_quit_during_initialization_does_not_publish_ready_or_leak_owner(self):
        self.engine = FakeRecognizer('slow_prepare')
        self.backend = Backend(self.output, recognizer=self.engine)
        self.thread = threading.Thread(target=self.backend.run, args=(self.input,))
        self.thread.start()
        self.take('progress')
        self.take('progress')
        self.send('quit', 'quit-loading')
        self.take('stopped')
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())
        self.assertTrue(self.output.queue.empty())


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        model = Path(self.temp.name) / 'models/vosk-model-small-cn-0.22/am'
        model.mkdir(parents=True)
        (model / 'final.mdl').write_bytes(b'test fixture, not a model')
        self.env = patch.dict(os.environ, {'LABMATE_MODEL_PATH': str(model.parent)})
        self.env.start()
        self.analyses = []
        self.models = []
        self.progress = []
        self.ready_to_speak = threading.Event()
        class Microphone:
            def __init__(self, args):
                self.args = args
                self.error = None
                self.utterances = queue.Queue()
                self.splitter = SimpleNamespace(rejected=0)
                self.closed = False
            def __enter__(self):
                return self
            def close(self):
                self.closed = True
        def load_model(path):
            self.models.append(path)
            return object()
        def analyze(*args, **kwargs):
            self.analyses.append((args, kwargs))
            kwargs['on_partial']('partial')
            return dict(text='记录电压三点三伏', command={'intent': 'record_manual'},
                        reason=None, recognition_ms=10)
        modules = SimpleNamespace(
            backend=SimpleNamespace(Model=load_model, SetLogLevel=lambda level: None),
            cli=SimpleNamespace(analyze=analyze, command_description=lambda command: '人工报数 3.3 V'),
            grammar=SimpleNamespace(GRAMMAR_JSON='["记录 电压"]',
                                    SAVE_CONFIRM_GRAMMAR_JSON='["确认", "确认 保存", "[unk]"]'),
            listen=SimpleNamespace(ContinuousMicrophone=Microphone))
        self.adapter = BoardRecognizer(self.temp.name, modules=modules)
        self.shutdown = threading.Event()
        self.adapter.prepare(self.shutdown, self.notify)

    def notify(self, text):
        self.progress.append(text)
        if text.startswith(('现在请说话', '可点击')):
            self.ready_to_speak.set()

    def feed_after_start(self, stale=False):
        def feed():
            self.ready_to_speak.wait(2)
            mic = self.adapter.microphone
            if stale:
                mic.utterances.put(([0], {'duration_seconds': 2}, time.monotonic() - 5))
            # 100 ms fixture audio stands in for the adapter's queue boundary.
            mic.utterances.put(([0], {'duration_seconds': 0.1}, time.monotonic()))
        thread = threading.Thread(target=feed)
        thread.start()
        return thread

    def tearDown(self):
        self.adapter.close()
        self.env.stop()
        self.temp.cleanup()

    def test_reuses_model_filters_idle_audio_and_uses_baseline_analyze(self):
        mic = self.adapter.microphone
        # A queued pre-click utterance must not be recognized.
        mic.utterances.put(([99], {'duration_seconds': 1}, time.monotonic()))
        for iteration in range(2):
            self.ready_to_speak.clear()
            producer = self.feed_after_start(stale=True)
            result = self.adapter.recognize(threading.Event(), self.notify)
            producer.join(2)
            self.assertFalse(result['simulated'])
            self.assertEqual(self.analyses[-1][0][0], [0])
            self.assertTrue(self.analyses[-1][1]['command_grammar'])
            self.assertEqual(self.analyses[-1][1]['grammar'], '["记录 电压"]')
        self.assertEqual(len(self.models), 1)
        self.assertEqual(mic.args.audio_device, 'hw:0,1')
        self.assertFalse(mic.args.no_es8388_init)

    def test_cancel_waiting_for_speech_returns_without_decode(self):
        cancelled = threading.Event()
        timer = threading.Timer(0.03, cancelled.set)
        timer.start()
        self.assertIsNone(self.adapter.recognize(cancelled, self.notify))
        timer.join(1)
        self.assertEqual(self.analyses, [])

    def test_confirmation_filters_stale_audio_wrong_words_and_low_confidence(self):
        replies = iter([
            dict(text='取消', command={'intent': 'cancel'}, reason=None),
            dict(text='确认', command={'intent': 'confirm'}, reason='low confidence'),
            dict(text='确认 保存', command={'intent': 'confirm'}, reason=None),
        ])
        def analyze(*args, **kwargs):
            self.analyses.append((args, kwargs))
            return next(replies)
        self.adapter.modules.cli.analyze = analyze
        def feed():
            self.ready_to_speak.wait(2)
            mic = self.adapter.microphone
            mic.utterances.put(([99], {'duration_seconds': 2}, time.monotonic()-5))
            for _ in range(3):
                mic.utterances.put(([0], {'duration_seconds': 0.1}, time.monotonic()))
        producer = threading.Thread(target=feed)
        producer.start()
        result = self.adapter.recognize_confirmation(threading.Event(), self.notify)
        producer.join(2)
        self.assertEqual(result, {'text': '确认保存'})
        self.assertEqual(len(self.analyses), 3)
        self.assertTrue(all(item[0][0] == [0] for item in self.analyses))
        self.assertTrue(all(item[1]['grammar'] == self.adapter.modules.grammar.SAVE_CONFIRM_GRAMMAR_JSON
                            for item in self.analyses))
        self.assertEqual(len(self.models), 1)

    def test_manual_action_can_stop_confirmation_without_decoding(self):
        cancelled = threading.Event()
        timer = threading.Timer(0.03, cancelled.set)
        timer.start()
        self.assertIsNone(self.adapter.recognize_confirmation(cancelled, self.notify))
        timer.join(1)
        self.assertEqual(self.analyses, [])

    def test_capture_error_is_reported_and_close_releases_microphone(self):
        mic = self.adapter.microphone
        mic.error = RuntimeError('XRUN')
        with self.assertRaisesRegex(RuntimeError, 'XRUN'):
            self.adapter.recognize(threading.Event(), self.notify)
        self.adapter.close()
        self.assertTrue(mic.closed)


class RealProcessChecks(unittest.TestCase):
    def test_missing_sources_do_not_silently_fall_back_to_demo(self):
        with tempfile.TemporaryDirectory() as empty:
            process = subprocess.Popen([sys.executable, '-u', str(ROOT / 'backend.py')],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       env=dict(os.environ, LABMATE_ASR_ROOT=empty, PYTHONIOENCODING='utf-8'),
                                       encoding='utf-8')
            try:
                process.wait(timeout=5)  # Keep stdin open like QProcess does.
                messages = [json.loads(line) for line in process.stdout]
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()
            self.assertTrue(messages)
            self.assertTrue(all(item['mode'] == 'asr' for item in messages))
            self.assertEqual(messages[-1]['event'], 'fatal')
            self.assertNotIn('ready', [item['event'] for item in messages])


if __name__ == '__main__':
    unittest.main()
