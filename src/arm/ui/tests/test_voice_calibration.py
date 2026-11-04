"""Calibration selects evidence and cannot enter instrument/record dispatch."""
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audio_frontend import select_calibration
from backend import Backend
import test_real_asr as fixtures


def candidate(layout='msb-first', channel=1, hits=3, confidence=.9, floor=.004):
    return dict(layout=layout, channel=channel, hits=hits, confidence=confidence, noise_floor=floor)


class CalibrationChoiceTests(unittest.TestCase):
    def test_matching_speech_and_quiet_win_over_high_level_noise(self):
        report = select_calibration([candidate('little', 0, confidence=.99, floor=.3), candidate()])
        self.assertTrue(report['success'])
        self.assertEqual(report['selected']['layout'], 'msb-first')
        self.assertEqual(report['selected']['channel'], 1)

    def test_fewer_than_two_successes_do_not_apply(self):
        self.assertFalse(select_calibration([candidate(hits=1)])['success'])

    def test_close_layout_tie_is_rejected(self):
        report = select_calibration([candidate(), candidate('little', confidence=.89)])
        self.assertFalse(report['success'])


class CalibrationRecognizer(fixtures.FakeRecognizer):
    def __init__(self):
        super().__init__()
        self.applied = []

    def calibrate(self, cancelled, progress):
        progress('calibration capture')
        time.sleep(.1)  # Deliberately return late after cancellation.
        return select_calibration([candidate()])

    def apply_calibration(self, report):
        self.applied.append(report)


class CalibrationProtocolTests(unittest.TestCase):
    def setUp(self):
        self.input, self.output = fixtures.QueueInput(), fixtures.QueueOutput()
        self.recognizer = CalibrationRecognizer()
        self.store, self.instruments = Mock(), Mock()
        self.backend = Backend(self.output, recognizer=self.recognizer,
                               record_store=self.store, command_executor=self.instruments)
        self.thread = threading.Thread(target=self.backend.run, args=(self.input,))
        self.thread.start()
        self.take('ready')

    def send(self, action, request, target=None):
        import json
        value = dict(protocol=1, action=action, id=request)
        if target: value['target'] = target
        self.input.queue.put(json.dumps(value)+'\n')

    def take(self, event):
        for _ in range(12):
            value = self.output.queue.get(timeout=3)
            if value['event']==event: return value
        self.fail('Missing event: '+event)

    def tearDown(self):
        if self.thread.is_alive():
            self.send('quit', 'end')
            self.thread.join(3)
        self.assertFalse(self.thread.is_alive())

    def test_calibration_result_never_reads_or_saves_experiment_data(self):
        self.send('calibrate', 'detect')
        self.take('state')
        result = self.take('calibration_result')
        self.assertEqual(result['state'], 'idle')
        self.assertTrue(result['success'])
        self.assertEqual(len(self.recognizer.applied), 1)
        self.store.save_result.assert_not_called()
        self.instruments.handles.assert_not_called()
        self.instruments.preview.assert_not_called()
        self.instruments.save.assert_not_called()

    def test_cancelled_detection_cannot_apply_a_late_result(self):
        self.send('calibrate', 'detect')
        self.take('progress')
        self.send('cancel', 'cancel', 'detect')
        self.take('cancelled')
        time.sleep(.15)
        self.assertEqual(self.recognizer.applied, [])
        self.assertEqual(self.backend.state, 'idle')
