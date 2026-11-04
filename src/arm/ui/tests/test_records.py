"""Result-only record/history integration; no microphone, PCM or NumPy dependency."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import Backend
from record_store import RecordStore, display_time
from test_real_asr import FakeRecognizer, QueueInput, QueueOutput


def voice_result():
    return dict(text='记录电压三点三伏', summary='电压 3.30 V', simulated=False, reason=None,
                command=dict(intent='record_manual', measurements=[
                    dict(quantity='voltage', value='3.30', unit='V')]))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.directory = self.base / 'current/records'
        self.old = self.base / 'previous/records'
        self.store = RecordStore(ROOT / 'asr_runtime', self.directory, [self.old])

    def tearDown(self):
        self.temp.cleanup()

    def write_record(self, directory=None, **changes):
        record = dict(schema_version=2, record_id=uuid4().hex, value=3.3, unit='V',
                      source='mock', is_simulated=True, valid=True, status='active',
                      saved_at='2023-04-16T03:29:49.157+00:00')
        record.update(changes)
        destination = directory if directory is not None else self.directory
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / ('record_fixture_' + record['record_id'] + '.json')
        path.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        return path, record

    def test_actual_legacy_record_is_deduplicated_without_changing_time(self):
        source = ROOT / 'tests/fixtures/legacy_mock_record.json'
        name = 'record_legacy_fixture.json'
        for destination in (self.directory, self.old):
            destination.mkdir(parents=True)
            shutil.copy2(str(source), str(destination / name))
        page = self.store.list_page()
        self.assertEqual(page['total'], 1)
        row = page['rows'][0]
        self.assertEqual(row['content'], '电压 3.3 V')
        self.assertEqual(row['image_path'], '')
        self.assertEqual(row['source'], '模拟数据')
        self.assertEqual(row['time_text'], '2023-04-16 11:29:49')
        self.assertIn('2023-04-16T03:29:49.157+00:00', row['detail'])
        self.assertEqual((self.directory / name).read_bytes(), source.read_bytes())

    def test_zero_decimal_precision_and_two_measurements_remain_visible(self):
        self.write_record(record_kind='manual', source='manual_voice', is_simulated=False,
                          measurements=[dict(quantity='voltage', value='0.00', unit='mV'),
                                        dict(quantity='current', value='10.000', unit='mA')])
        row = self.store.list_page()['rows'][0]
        self.assertEqual(row['content'], '电压 0.00 mV；电流 10.000 mA')
        self.assertEqual(row['source'], '语音报数')

    def test_duplicate_annotations_merge_and_void_status_wins(self):
        path, record = self.write_record()
        self.old.mkdir(parents=True)
        shutil.copy2(str(path), str(self.old / path.name))
        self.store.core.RECORD_DIR = self.directory
        self.store.core.annotate_record(record['record_id'], 'abnormal', '数值异常')
        self.store.core.RECORD_DIR = self.old
        self.store.core.annotate_record(record['record_id'], 'void', '本条作废')
        row = self.store.list_page()['rows'][0]
        self.assertEqual(row['status'], '已撤销')
        self.assertIn('数值异常', row['detail'])
        self.assertIn('本条作废', row['detail'])
        self.assertEqual(self.store.list_page()['total'], 1)

    def test_conflicting_duplicate_never_hides_simulated_source(self):
        _, record = self.write_record(source='manual_voice', is_simulated=False)
        self.write_record(self.old, record_id=record['record_id'], source='mock', is_simulated=True)
        page = self.store.list_page()
        self.assertEqual(page['rows'][0]['source'], '模拟数据')
        self.assertTrue(page['warnings'])

    def test_malformed_files_and_fields_do_not_hide_good_records(self):
        self.write_record()
        for changes in (dict(saved_at={}), dict(source=[]), dict(measurements=[5]),
                        dict(value=float('nan')), dict(measurements=[dict(quantity=[], value='1', unit='V')])):
            self.write_record(**changes)
        (self.directory / 'record_broken.json').write_text('{', encoding='utf-8')
        (self.directory / 'record_list.json').write_text('[]', encoding='utf-8')
        page = self.store.list_page()
        self.assertEqual(page['total'], 1)
        self.assertIn('7', page['warnings'][0])

    def test_pagination_orders_by_time_and_clamps_after_deletion(self):
        for day in range(1, 10):
            self.write_record(saved_at='2026-10-%02dT10:00:00+08:00' % day)
        first = self.store.list_page(0, 4)
        last = self.store.list_page(99, 4)
        self.assertEqual((first['total'], first['total_pages'], len(first['rows'])), (9, 3, 4))
        self.assertEqual(first['rows'][0]['saved_at'], '2026-10-09T10:00:00+08:00')
        self.assertEqual((last['page'], len(last['rows'])), (2, 1))
        for size in (0, 7, True):
            with self.assertRaises(ValueError):
                self.store.list_page(0, size)

    def test_missing_and_timezone_less_times_are_not_given_a_false_timezone(self):
        self.assertEqual(display_time(None), '未记录')
        self.assertIn('原时区未知', display_time('2023-04-16T03:29:49'))
        self.assertEqual(display_time('2023-04-16T03:29:49Z'), '2023-04-16 11:29:49')

    def test_original_recognizer_result_saves_without_audio_and_survives_restart(self):
        row = self.store.save_result(voice_result(), 'round-1')
        document = self.store.core.read_record(next(self.directory.glob('record_*.json')))
        self.assertEqual((document['schema_version'], document['source'], document['is_simulated']),
                         (3, 'manual_voice_result', False))
        self.assertEqual(document['measurements'][0]['value'], '3.30')
        self.assertIsNone(document['audio_path'])
        self.assertTrue(document['confirmed_at'])
        self.assertEqual(list(self.base.rglob('*.wav')), [])
        restarted = RecordStore(ROOT / 'asr_runtime', self.directory)
        self.assertEqual(restarted.list_page()['rows'][0]['record_id'], row['record_id'])

    def test_save_with_all_audio_libraries_unavailable(self):
        code = """import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
class NoAudio:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('numpy', 'wave', 'chunk', 'audioop'):
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, NoAudio())
from record_store import RecordStore
store = RecordStore(sys.argv[2], sys.argv[3])
row = store.save_result(dict(simulated=False, text='fixture', command=dict(
    intent='record_manual', measurements=[dict(quantity='voltage', value='3.30', unit='V')])), 'no-audio')
assert row['content'] == '电压 3.30 V'
print('RESULT_ONLY_OK')
"""
        checked = subprocess.run([sys.executable, '-c', code, str(ROOT), str(ROOT/'asr_runtime'),
                                  str(self.directory)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 encoding='utf-8', timeout=10, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn('RESULT_ONLY_OK', checked.stdout)

    def test_save_failure_leaves_no_record_and_allows_retry(self):
        with patch.object(self.store.core, 'write_json_atomically', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.store.save_result(voice_result(), 'retry')
        self.assertEqual(list(self.directory.glob('record_*.json')), [])
        self.store.save_result(voice_result(), 'retry')
        self.assertEqual(self.store.list_page()['total'], 1)

    def test_failure_after_json_commit_is_idempotent_after_restart(self):
        original = self.store.core.write_json_atomically
        def lost_ack(path, document):
            original(path, document)
            raise OSError('ack lost')
        with patch.object(self.store.core, 'write_json_atomically', side_effect=lost_ack):
            with self.assertRaisesRegex(OSError, 'ack lost'):
                self.store.save_result(voice_result(), 'once-only')
        restarted = RecordStore(ROOT/'asr_runtime', self.directory)
        self.assertEqual(restarted.save_result(voice_result(), 'once-only')['content'], '电压 3.30 V')
        self.assertEqual(len(list(self.directory.glob('record_*.json'))), 1)

    def test_old_clock_does_not_block_original_voice_flow(self):
        with patch('record_store.datetime', wraps=datetime) as clock:
            clock.now.return_value = datetime(2023, 4, 27)
            self.store.save_result(voice_result(), 'old-clock')
        self.assertIn('尚未校准', self.store.list_page()['rows'][0]['detail'])

    def test_simulation_and_invalid_values_do_not_write(self):
        for change in (dict(simulated=True), dict(command=None), dict(reason='rejected'),
                       dict(command=dict(intent='record_manual', measurements=[
                           dict(quantity='voltage', value='NaN', unit='V')]))):
            result = voice_result()
            result.update(change)
            with self.assertRaises(ValueError):
                self.store.save_result(result, uuid4().hex)
        self.assertEqual(list(self.directory.glob('record_*.json')), [])

    def test_other_recognized_commands_are_saved_as_text_without_instrument_values(self):
        result = voice_result()
        result.update(text='记录数据', command=dict(intent='record_device'))
        with patch.object(self.store.core, 'get_reading', side_effect=AssertionError('must not acquire')):
            self.store.save_result(result, 'old-command')
        row = self.store.list_page()['rows'][0]
        self.assertEqual((row['content'], row['source']), ('记录数据', '语音指令'))
        document = self.store.core.read_record(next(self.directory.glob('record_*.json')))
        self.assertNotIn('measurements', document)
        self.assertNotIn('value', document)


class SyntheticRecognizer(FakeRecognizer):
    def recognize(self, cancelled, progress):
        super().recognize(cancelled, progress)
        return voice_result()


class BackendRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name) / 'data/records'
        self.store = RecordStore(ROOT / 'asr_runtime', self.directory)
        self.input, self.output = QueueInput(), QueueOutput()
        self.backend = None
        self.thread = None
        self.release = threading.Event()

    def tearDown(self):
        self.release.set()
        if self.thread is not None:
            self.input.queue.put('')
            self.thread.join(4)
            self.assertFalse(self.thread.is_alive())
        self.temp.cleanup()

    def launch(self, engine=None, ready=True):
        self.backend = Backend(self.output, recognizer=engine or SyntheticRecognizer(), record_store=self.store)
        self.thread = threading.Thread(target=self.backend.run, args=(self.input,))
        self.thread.start()
        self.take('progress')
        self.take('progress')
        if ready:
            self.take('ready')

    def take(self, event):
        message = self.output.queue.get(timeout=3)
        self.assertEqual(message['event'], event, message)
        self.assertNotIn('_capture', message)
        return message

    def send(self, action, request_id, target=None, **fields):
        self.input.queue.put(json.dumps(dict(protocol=1, action=action, id=request_id,
                                             target=target, **fields)) + '\n')

    def start(self):
        self.send('start', 'round')
        self.take('state')
        self.take('progress')
        return self.take('result')

    def confirm(self, request_id='confirm'):
        self.send('confirm', request_id, 'round')
        self.assertEqual(self.take('state')['state'], 'saving')

    def test_original_result_and_cancel_never_write_before_confirmation(self):
        self.launch()
        self.start()
        self.assertIsNotNone(self.backend.result)
        self.send('status', 'status')
        self.assertNotIn('_capture', self.take('state')['result'])
        self.send('cancel', 'cancel', 'round')
        self.take('cancelled')
        self.assertIsNone(self.backend.result)
        self.assertFalse(self.directory.exists())

    def test_confirm_then_history_returns_the_actual_saved_row(self):
        self.launch()
        self.start()
        self.confirm()
        saved = self.take('confirmed')
        self.assertEqual(saved['effect'], 'record_saved')
        self.assertEqual(saved['state'], 'idle')
        self.assertIsNone(self.backend.result)
        self.send('history', 'history-1')
        page = self.take('history')
        self.assertEqual(page['request_id'], 'history-1')
        self.assertEqual(page['total'], 1)
        self.assertEqual(page['rows'][0]['record_id'], saved['record']['record_id'])

    def test_save_failure_keeps_pending_result_and_retry_saves_exactly_once(self):
        self.launch()
        self.start()
        with patch.object(self.store.core, 'write_json_atomically', side_effect=OSError('read only')):
            self.confirm('first-confirm')
            failed = self.take('error')
            self.assertEqual((failed['code'], failed['state']), ('save_failed', 'pending'))
            self.assertIsNotNone(self.backend.result)
        self.confirm('retry-confirm')
        self.take('confirmed')
        self.assertEqual(self.store.list_page()['total'], 1)

    def test_slow_history_does_not_block_cancellation_or_mix_round_ids(self):
        entered = threading.Event()
        original = self.store.list_page
        def blocked(*args):
            entered.set()
            self.release.wait(2)
            return original(*args)
        with patch.object(self.store, 'list_page', side_effect=blocked):
            self.launch()
            self.start()
            self.send('history', 'history-slow')
            self.assertTrue(entered.wait(1))
            self.send('cancel', 'cancel-round', 'round')
            self.assertEqual(self.take('cancelled')['request_id'], 'cancel-round')
            self.release.set()
            page = self.take('history')
            self.assertEqual(page['request_id'], 'history-slow')
            self.assertEqual((page['state'], page['total']), ('idle', 0))

    def test_history_is_available_while_model_is_initializing(self):
        release = self.release
        class Loading(SyntheticRecognizer):
            def prepare(self, shutdown, progress):
                progress('loading')
                release.wait(2)
        self.launch(Loading(), ready=False)
        self.send('history', 'while-loading')
        page = self.take('history')
        self.assertEqual((page['request_id'], page['state']), ('while-loading', 'initializing'))
        self.release.set()
        self.take('ready')

    def test_duplicate_confirm_and_cancel_during_save_cannot_repeat_or_undo_commit(self):
        entered = threading.Event()
        original = self.store.save_result
        def blocked(*args):
            entered.set()
            self.release.wait(2)
            return original(*args)
        with patch.object(self.store, 'save_result', side_effect=blocked):
            self.launch()
            self.start()
            self.confirm()
            self.assertTrue(entered.wait(1))
            for action in ('confirm', 'cancel'):
                self.send(action, 'duplicate-' + action, 'round')
                self.assertEqual(self.take('error')['code'], 'save_in_progress')
            self.release.set()
            self.take('confirmed')
        self.assertEqual(self.store.list_page()['total'], 1)

    def test_quit_finishes_submitted_save_before_stopping(self):
        entered = threading.Event()
        original = self.store.save_result
        def blocked(*args):
            entered.set()
            self.release.wait(2)
            return original(*args)
        with patch.object(self.store, 'save_result', side_effect=blocked):
            self.launch()
            self.start()
            self.confirm()
            self.assertTrue(entered.wait(1))
            self.send('quit', 'closing')
            # Status is ordered after quit on the owner queue; confirms it was
            # processed while the disk worker was still blocked.
            self.send('status', 'after-quit')
            self.assertEqual(self.take('state')['state'], 'saving')
            self.release.set()
            self.take('confirmed')
            self.assertEqual(self.take('stopped')['request_id'], 'closing')
            self.thread.join(3)
            self.assertFalse(self.thread.is_alive())
        self.assertEqual(self.store.list_page()['total'], 1)

    def test_history_failure_does_not_discard_the_pending_recognition(self):
        self.launch()
        self.start()
        with patch.object(self.store, 'list_page', side_effect=OSError('unreadable')):
            self.send('history', 'failed-history')
            failed = self.take('error')
            self.assertEqual((failed['request_id'], failed['state']), ('failed-history', 'pending'))
        self.assertIsNotNone(self.backend.result)
        self.send('cancel', 'cancel', 'round')
        self.take('cancelled')

    def test_previously_accepted_intent_still_reaches_result_and_confirmation(self):
        class Instrument(SyntheticRecognizer):
            def recognize(self, cancelled, progress):
                result = super().recognize(cancelled, progress)
                result.update(text='记录数据', command=dict(intent='record_device'), _capture=object())
                return result
        self.launch(Instrument())
        result = self.start()
        self.assertEqual(result['command']['intent'], 'record_device')
        self.confirm()
        self.assertEqual(self.take('confirmed')['record']['content'], '记录数据')


if __name__ == '__main__':
    unittest.main()
