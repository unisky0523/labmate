"""Instrument dispatch contracts, using CLI substitutes rather than USB devices."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import Backend
from command_executor import CommandExecutor
from instrument_adapter import InstrumentAdapter, validate_result
from record_store import RecordStore
from test_real_asr import FakeRecognizer, QueueInput, QueueOutput


def reading(action, request_id, partial=False):
    meter = action == 'meter.read'
    rows = [dict(measurement_id='dc_voltage' if meter else 'ch1_pkpk',
                 label='直流电压' if meter else '峰峰值', channel='' if meter else '1',
                 valid=True, value=0.0 if meter else 3.3, unit='V', unit_scale_verified=True)]
    if partial:
        rows.append(dict(measurement_id='ch1_freq', label='频率', channel='1',
                         valid=False, value=None, unit='Hz', error_code='NO_SIGNAL'))
    return dict(request_id=request_id, device_id='suin_sa5041' if meter else 'siglent_sds1202x',
                source='scpi', simulated=False, status='partial' if partial else 'complete',
                valid=not partial, measurements=rows, identity_verified=False,
                captured_at='2026-11-02T18:00:00+08:00')


def voice(intent='record_device', **extra):
    return dict(text='读取数据' if intent == 'read' else '记录数据', simulated=False,
                reason=None, command=dict(intent=intent, count=1, **extra))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.config = dict(meter=dict(root=str(self.base/'meter')),
                           scope=dict(root=str(self.base/'scope'), resource='USB::verified',
                                      channels=[1], parameters=['PKPK', 'FREQ', 'RMS']))
        for kind, script in (('meter', 'run_meter_board.sh'), ('scope', 'run_scope_board.sh')):
            path = self.base/kind/'c_instrument'/script
            path.parent.mkdir(parents=True)
            path.write_text('#!/bin/sh\n', encoding='utf-8')
        self.calls = []
        self.store = RecordStore(ROOT/'asr_runtime', self.base/'records')
        self.adapter = InstrumentAdapter(self.config, runner=self.runner)
        self.executor = CommandExecutor(self.adapter, self.store, self.base/'evidence')
        self.partial = False

    def tearDown(self):
        self.temp.cleanup()

    def runner(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        action = 'meter.read' if 'meter' in argv[1] else 'scope.read'
        request_id = argv[argv.index('--request-id')+1]
        result = reading(action, request_id, self.partial and action == 'scope.read')
        return SimpleNamespace(stdout=json.dumps(result), stderr='diagnostics on stderr',
                               returncode=2 if result['status'] == 'partial' else 0)


class AdapterTests(Fixture):
    def test_argv_configured_scope_and_action_deadline(self):
        result = self.adapter.call('scope.read', 'voice-1')
        self.assertEqual(result['result']['status'], 'complete')
        argv, kwargs = self.calls[0]
        self.assertEqual(argv[argv.index('--resource')+1], 'USB::verified')
        self.assertEqual(argv[-4:], ['--measure', 'PKPK', 'FREQ', 'RMS'])
        self.assertNotIn('shell', kwargs)
        self.assertGreater(kwargs['timeout'], 3)
        self.assertIn('diagnostics', result['stderr'])

    def test_partial_exit_two_preserves_valid_zero_and_invalid_items(self):
        self.partial = True
        result = self.adapter.call('scope.read', 'partial')
        self.assertEqual(result['result']['status'], 'partial')
        self.assertIsNone(result['result']['measurements'][1]['value'])
        meter = self.adapter.call('meter.read', 'zero')
        self.assertEqual(meter['result']['measurements'][0]['value'], 0)
        self.assertFalse(meter['result']['identity_verified'])

    def test_mismatched_request_and_non_json_start_failure_are_failures(self):
        for output in ('Traceback: missing pyusb', json.dumps(reading('meter.read', 'wrong'))):
            self.adapter.runner = lambda *a, **k: SimpleNamespace(stdout=output, stderr='bad', returncode=0)
            result = self.adapter.call('meter.read', 'expected')
            self.assertEqual(result['result']['status'], 'failed')

    def test_timeout_and_missing_script_give_structured_failures(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
        self.adapter.runner = timeout
        self.assertEqual(self.adapter.call('meter.read', 'timeout')['result']['error_code'], 'ACTION_TIMEOUT')
        (self.base/'meter/c_instrument/run_meter_board.sh').unlink()
        self.assertEqual(self.adapter.call('meter.read', 'missing')['result']['status'], 'failed')

    def test_rejects_unknown_resource_configuration_and_actions(self):
        for change in (dict(channels=[True]), dict(parameters=['*RST']), dict(resource='')):
            config = copy.deepcopy(self.config)
            config['scope'].update(change)
            with self.assertRaises(ValueError):
                InstrumentAdapter(config)
        with self.assertRaises(ValueError):
            self.adapter.call('shell', 'id')

    def test_rejects_nonfinite_and_unverified_meter_units(self):
        for change in (dict(value=float('nan')), dict(unit_scale_verified=False), dict(value=True)):
            result = reading('meter.read', 'id')
            result['measurements'][0].update(change)
            with self.assertRaises(ValueError):
                validate_result(result, 'meter.read')

    def test_screenshot_without_native_request_id_has_outer_correlation(self):
        path = self.base/'scope/c_instrument/runs/shot/screen.bmp'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'BM' + b'fixture' * 10)
        result = dict(device_id='siglent_sds1202x', source='scpi', simulated=False,
                      status='complete', valid=True, image_path=str(path), image_bytes=path.stat().st_size)
        self.adapter.runner = lambda *a, **k: SimpleNamespace(stdout=json.dumps(result), stderr='', returncode=0)
        entry = self.adapter.call('scope.capture_screen', 'shot-1')
        self.assertEqual(entry['request_id'], 'shot-1')
        self.assertNotIn('request_id', entry['result'])
        result['image_path'] = str(self.base/'missing.bmp')
        self.assertEqual(self.adapter.call('scope.capture_screen', 'shot-2')['result']['status'], 'failed')


class ExecutorStoreTests(Fixture):
    def test_preview_cancel_does_not_save_history_and_confirm_reuses_acquisition(self):
        value = self.executor.preview(voice('read'), 'read-1', threading.Event())
        self.assertIn('万用表', value['summary'])
        self.assertIn('示波器', value['summary'])
        self.assertEqual(self.store.list_page()['total'], 0)
        row = self.executor.save(value, 'read-1')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(row['source'], '仪器 USB')
        self.assertIn('0.0 V', row['content'])
        self.assertEqual(self.store.list_page()['total'], 1)

    def test_partial_result_history_and_restart_retain_each_item(self):
        self.partial = True
        row = self.executor.save(voice(), 'partial')
        self.assertEqual(row['status'], '部分成功')
        self.assertIn('NO_SIGNAL', row['content'])
        restarted = RecordStore(ROOT/'asr_runtime', self.base/'records')
        self.assertEqual(restarted.list_page()['total'], 1)
        document = json.loads(next((self.base/'records').glob('record_*.json')).read_text(encoding='utf-8'))
        self.assertEqual(document['devices'][1]['result']['measurements'][1]['value'], None)

    def test_archive_retry_after_restart_does_not_reacquire(self):
        original = self.store.core.write_json_atomically
        def fail_record(path, document):
            if path.name.startswith('record_'):
                raise OSError('disk full')
            return original(path, document)
        with patch.object(self.store.core, 'write_json_atomically', side_effect=fail_record):
            with self.assertRaises(OSError):
                self.executor.save(voice(), 'retry')
        restarted = CommandExecutor(self.adapter, self.store, self.base/'evidence')
        restarted.save(voice(), 'retry')
        restarted.save(voice(), 'retry')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.store.list_page()['total'], 1)

    def test_screenshot_is_copied_to_history_and_remains_after_source_removal(self):
        source = self.base/'scope/c_instrument/runs/screen.bmp'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'BM' + b'image' * 30)
        result = dict(device_id='siglent_sds1202x', source='scpi', simulated=False,
                      valid=True, status='complete', image_path=str(source), image_bytes=source.stat().st_size)
        self.adapter.runner = lambda *a, **k: SimpleNamespace(stdout=json.dumps(result), stderr='', returncode=0)
        row = self.executor.save(voice('capture_image'), 'shot')
        document = json.loads(next((self.base/'records').glob('record_*.json')).read_text(encoding='utf-8'))
        archived = Path(document['image_path'])
        self.assertEqual(source.read_bytes(), archived.read_bytes())
        self.assertEqual(row['image_path'], str(archived))
        source.unlink()
        self.assertTrue(archived.exists())
        self.assertEqual(self.store.list_page()['rows'][0]['image_path'], str(archived))
        self.assertIn(str(archived), row['detail'])

    def test_waveform_samples_and_camera_are_explicitly_rejected(self):
        values = [voice('save_waveform'), dict(voice('capture_image'), text='调用摄像头拍摄一下波形')]
        for value in values:
            with self.assertRaises(ValueError):
                self.executor.describe(value)
        self.assertEqual(self.calls, [])

    def batch(self, count=3, interval=1):
        result = voice()
        result['text'] = '连续记录三次数据，时间间隔一秒'
        result['command'].update(count=count, interval=interval)
        return result

    def test_batch_archives_three_real_pairs_as_separate_records(self):
        result = self.batch(interval=0)
        self.assertIn('连续记录 3 次', self.executor.describe(result))
        self.assertEqual(self.calls, [])
        row = self.executor.save(result, 'batch-three')
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(self.store.list_page()['total'], 3)
        self.assertEqual(row['batch_count'], 3)
        self.assertEqual(row['batch_complete_count'], 3)
        docs = [json.loads(p.read_text(encoding='utf-8')) for p in (self.base/'records').glob('record_*.json')]
        self.assertEqual(sorted(doc['batch']['index'] for doc in docs), [1, 2, 3])
        self.assertTrue(all(len(doc['devices']) == 2 for doc in docs))
        self.assertEqual(len({call[0][call[0].index('--request-id')+1] for call in self.calls}), 6)

    def test_batch_start_intervals_and_slow_reads_do_not_catch_up(self):
        for pair_duration, expected_starts in ((.3, [0, 1, 2]), (1.6, [0, 1.6, 3.2])):
            with self.subTest(pair_duration=pair_duration):
                clock = [0.0]
                starts = []
                original = self.adapter.runner
                def timed(argv, **kwargs):
                    if 'meter' in argv[1]:
                        starts.append(clock[0])
                    clock[0] += pair_duration / 2
                    return self.runner(argv, **kwargs)
                self.adapter.runner = timed
                executor = CommandExecutor(self.adapter, self.store, self.base/str(pair_duration),
                                           clock=lambda: clock[0], wait=lambda n: clock.__setitem__(0, clock[0]+n))
                executor.save(self.batch(), 'timed-' + str(pair_duration))
                for actual, expected in zip(starts, expected_starts):
                    self.assertAlmostEqual(actual, expected)
                self.assertEqual(len(starts), 3)
                self.adapter.runner = original

    def test_partial_batch_disk_failure_can_retry_without_reacquiring_any_round(self):
        result = self.batch(interval=0)
        original = self.store.core.write_json_atomically
        def fail_second(path, document):
            if path.name.startswith('record_') and document.get('batch', {}).get('index') == 2:
                raise OSError('disk full')
            return original(path, document)
        with patch.object(self.store.core, 'write_json_atomically', side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, '已保存 1/3 次'):
                self.executor.save(result, 'retry-batch')
        self.assertEqual(self.store.list_page()['total'], 1)
        self.assertEqual(len(self.calls), 4)
        restarted = CommandExecutor(self.adapter, self.store, self.base/'evidence')
        restarted.save(result, 'retry-batch')
        restarted.save(result, 'retry-batch')
        self.assertEqual(self.store.list_page()['total'], 3)
        self.assertEqual(len(self.calls), 6)

    def test_retry_of_complete_batch_does_not_wait_through_intervals_again(self):
        result = self.batch(interval=0)
        self.executor.save(result, 'cached-batch')
        result['command']['interval'] = 60
        executor = CommandExecutor(self.adapter, self.store, self.base/'evidence',
                                   wait=lambda n: self.fail('cached readings must not wait'))
        executor.save(result, 'cached-batch')
        self.assertEqual(len(self.calls), 6)

    def test_batch_failed_instrument_is_saved_honestly_for_each_round(self):
        self.partial = True
        row = self.executor.save(self.batch(interval=0), 'partial-batch')
        self.assertEqual(row['batch_complete_count'], 0)
        self.assertEqual(self.store.list_page()['total'], 3)
        self.assertTrue(all(r['status'] == '部分成功' for r in self.store.list_page()['rows']))

    def test_batch_rejects_invalid_numbers_before_querying_devices(self):
        for count, interval in ((0, 1), (101, 1), (True, 1), (1.5, 1), (3, -1),
                                (3, 61), (3, float('nan')), (3, True), (3, '1')):
            with self.subTest(count=count, interval=interval), self.assertRaises(ValueError):
                self.executor.describe(self.batch(count, interval))
        self.assertEqual(self.calls, [])


class BackendInstrumentTests(Fixture):
    def setUp(self):
        super().setUp()
        self.input, self.output = QueueInput(), QueueOutput()
        self.thread = None
        self.release = threading.Event()

    def tearDown(self):
        self.release.set()
        if self.thread is not None:
            self.input.queue.put('')
            self.thread.join(4)
            self.assertFalse(self.thread.is_alive())
        super().tearDown()

    def launch(self, intent, command=None):
        class Recognizer(FakeRecognizer):
            def recognize(engine, cancelled, progress):
                value = voice(intent)
                if command:
                    value['command'].update(command)
                return value
        self.backend = Backend(self.output, recognizer=Recognizer(), record_store=self.store,
                               command_executor=self.executor)
        self.thread = threading.Thread(target=self.backend.run, args=(self.input,))
        self.thread.start()
        self.take('progress')
        self.take('progress')
        self.take('ready')

    def send(self, action, request_id, target=None):
        self.input.queue.put(json.dumps(dict(protocol=1, action=action, id=request_id, target=target))+'\n')

    def take(self, event):
        value = self.output.queue.get(timeout=3)
        self.assertEqual(value['event'], event, value)
        return value

    def test_confirm_real_acquisition_returns_existing_gui_record_saved_protocol(self):
        self.launch('record_device')
        self.send('start', 'round')
        self.take('state')
        self.take('result')
        self.assertEqual(self.calls, [])
        self.send('confirm', 'confirm', 'round')
        self.take('state')
        saved = self.take('confirmed')
        self.assertEqual(saved['effect'], 'record_saved')
        self.assertIn('示波器', saved['record']['content'])
        self.assertEqual(len(self.calls), 2)

    def test_cancel_slow_read_is_responsive_and_does_not_start_second_instrument(self):
        entered = threading.Event()
        original = self.adapter.runner
        def slow(*args, **kwargs):
            entered.set()
            self.release.wait(2)
            return original(*args, **kwargs)
        self.adapter.runner = slow
        self.launch('read')
        self.send('start', 'round')
        self.take('state')
        self.take('progress')
        self.assertTrue(entered.wait(1))
        self.send('status', 'status')
        self.assertEqual(self.take('state')['state'], 'running')
        self.send('cancel', 'cancel', 'round')
        self.take('cancelled')
        self.release.set()
        self.send('history', 'history')
        self.assertEqual(self.take('history')['total'], 0)
        self.assertEqual(len(self.calls), 1)

    def test_read_previews_actual_values_then_saves_without_new_queries(self):
        self.launch('read')
        self.send('start', 'round')
        self.take('state')
        self.take('progress')
        self.assertIn('0.0 V', self.take('result')['summary'])
        self.send('confirm', 'confirm', 'round')
        self.take('state')
        self.take('confirmed')
        self.assertEqual(len(self.calls), 2)

    def test_batch_confirmation_executes_all_rounds_and_uses_existing_gui_protocol(self):
        self.launch('record_device', dict(count=3, interval=0))
        self.send('start', 'batch-round')
        self.take('state')
        self.assertIn('连续记录 3 次', self.take('result')['summary'])
        self.assertEqual(self.calls, [])
        self.send('confirm', 'batch-confirm', 'batch-round')
        state = self.take('state')
        self.assertEqual(state['state'], 'saving')
        self.assertIn('连续记录 3 次', state['message'])
        saved = self.take('confirmed')
        self.assertEqual(saved['state'], 'idle')
        self.assertEqual(saved['effect'], 'record_saved')
        self.assertEqual(saved['record']['batch_count'], 3)
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(self.store.list_page()['total'], 3)

    def test_cancel_pending_batch_does_not_query_either_instrument(self):
        self.launch('record_device', dict(count=3, interval=1))
        self.send('start', 'cancel-batch')
        self.take('state')
        self.take('result')
        self.send('cancel', 'cancel', 'cancel-batch')
        self.take('cancelled')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.list_page()['total'], 0)


if __name__ == '__main__':
    unittest.main()
