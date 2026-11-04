"""Voice/manual confirmation share one save and reject replies from old turns."""
import json
from pathlib import Path
import queue
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import Backend
from test_real_asr import FakeRecognizer, QueueInput, QueueOutput


class ConfirmationRecognizer(FakeRecognizer):
    def __init__(self):
        super().__init__()
        self.decisions = queue.Queue()
        self.decoded = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def recognize_confirmation(self, cancelled, progress):
        self.calls.append(('confirmation', threading.get_ident()))
        progress('waiting for confirmation')
        while not cancelled.is_set():
            try:
                value = self.decisions.get(timeout=0.01)
            except queue.Empty:
                continue
            self.decoded.set()
            self.release.wait(2)
            if isinstance(value, Exception):
                raise value
            return {'text': value}
        return None


class Store:
    def __init__(self):
        self.saved = []
        self.fail = False

    def save_result(self, result, operation_id):
        if self.fail:
            raise OSError('test disk error')
        self.saved.append(operation_id)
        return {'content': result['summary']}


class ConfirmationProtocolTests(unittest.TestCase):
    def setUp(self):
        self.input, self.output = QueueInput(), QueueOutput()
        self.engine, self.store = ConfirmationRecognizer(), Store()
        self.backend = Backend(self.output, recognizer=self.engine, record_store=self.store)
        self.thread = threading.Thread(target=self.backend.run, args=(self.input,))
        self.thread.start()
        self.take('progress')
        self.take('progress')
        self.take('ready')

    def send(self, action, name, target=None):
        self.input.queue.put(json.dumps(dict(protocol=1, id=name, action=action, target=target))+'\n')

    def take(self, event):
        value = self.output.queue.get(timeout=3)
        self.assertEqual(value['event'], event, value)
        return value

    def start(self, name):
        self.send('start', name)
        self.take('state')
        self.take('progress')
        self.take('result')
        self.take('confirmation_progress')

    def tearDown(self):
        self.engine.release.set()
        self.input.queue.put('')
        self.thread.join(3)
        self.assertFalse(self.thread.is_alive())
        self.assertEqual(len({call[1] for call in self.engine.calls}), 1)
        self.assertEqual([call[0] for call in self.engine.calls].count('prepare'), 1)
        self.assertEqual([call[0] for call in self.engine.calls].count('close'), 1)

    def test_voice_uses_normal_confirm_request_and_saves_only_once(self):
        self.start('read')
        self.engine.decisions.put('确认')
        voice = self.take('voice_confirm')
        self.assertEqual((voice['operation_id'], voice['state']), ('read', 'pending'))
        self.assertEqual(self.store.saved, [])
        # Qt routes this event through the same request as its manual button.
        self.send('confirm', 'voice-request', voice['operation_id'])
        self.assertEqual(self.take('state')['state'], 'saving')
        self.take('confirmed')
        self.send('confirm', 'manual-double-click', 'read')
        self.assertEqual(self.take('error')['code'], 'wrong_target')
        self.assertEqual(self.store.saved, ['read'])

    def test_manual_save_wins_over_late_voice_and_next_turn_stays_pending(self):
        self.start('old')
        self.engine.release.clear()
        self.engine.decisions.put('确认')
        self.assertTrue(self.engine.decoded.wait(1))
        self.send('confirm', 'manual', 'old')
        self.take('state')
        self.take('confirmed')
        self.send('start', 'new')
        self.take('state')
        self.engine.release.set()
        self.take('progress')
        self.assertEqual(self.take('result')['operation_id'], 'new')
        self.take('confirmation_progress')
        self.assertEqual(self.store.saved, ['old'])
        self.assertEqual(self.backend.state, 'pending')

    def test_cancel_discards_voice_from_previous_operation(self):
        self.start('cancelled-round')
        self.engine.release.clear()
        self.engine.decisions.put('确认')
        self.assertTrue(self.engine.decoded.wait(1))
        self.send('cancel', 'cancel', 'cancelled-round')
        self.take('cancelled')
        self.engine.release.set()
        self.start('fresh')
        self.assertEqual(self.store.saved, [])
        self.engine.decisions.put('确认保存')
        self.assertEqual(self.take('voice_confirm')['operation_id'], 'fresh')

    def test_save_failure_rearms_voice_and_keeps_manual_retry_available(self):
        self.start('retry')
        self.store.fail = True
        self.send('confirm', 'first-save', 'retry')
        self.take('state')
        self.assertEqual(self.take('error')['state'], 'pending')
        self.take('confirmation_progress')
        self.store.fail = False
        self.send('confirm', 'retry-save', 'retry')
        self.take('state')
        self.take('confirmed')
        self.assertEqual(self.store.saved, ['retry'])

    def test_voice_failure_leaves_result_for_manual_save(self):
        self.start('fallback')
        self.engine.decisions.put(RuntimeError('microphone error'))
        self.assertEqual(self.take('confirmation_progress')['state'], 'pending')
        self.send('confirm', 'manual-fallback', 'fallback')
        self.take('state')
        self.take('confirmed')
        self.assertEqual(self.store.saved, ['fallback'])


if __name__ == '__main__':
    unittest.main()
