"""DG voice/USB boundary, output sequencing and crash-safe retry tests."""
import copy
from contextlib import nullcontext
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
sys.path[:0] = [str(ROOT), str(ROOT/'asr_runtime')]
from text_cli import parse_command
from asr_cli import command_description
from generator_control import GeneratorControl, validate_control
from generator_runner import execute_job
from record_store import RecordStore

PHRASE = '配置扫频起始频率一百赫兹终止频率十千赫兹时间五秒幅度一伏峰峰值'
STATE = dict(output='OFF', load='INFINITY', waveform='SIN', frequency_hz=1000.,
             amplitude_unit='VPP', amplitude=1., offset_v=0., sweep='ON', start_hz=100.,
             stop_hz=10000., time_s=5., spacing='LIN', trigger='INT')


def success(request):
    return dict(device_id='rigol_dg4102', source='scpi', simulated=False, status='complete', valid=True,
                identity_verified=True, identity='RIGOL TECHNOLOGIES,DG4102,DG4E184950519,00.01.13',
                request=request, state=copy.deepcopy(STATE), electrical_output_verified=False)


class LanguageTests(unittest.TestCase):
    def test_units_and_optional_channel(self):
        c = parse_command(PHRASE)
        self.assertEqual(c['request']['channel'], 2)
        self.assertEqual([c['request'][k] for k in ('start_hz','stop_hz','time_s','amplitude_vpp')], [100,10000,5,1])
        self.assertFalse(c['enable'])
        self.assertIn('输出关闭', command_description(c))
        self.assertEqual(parse_command('通道二'+PHRASE), c)
        self.assertEqual(parse_command(PHRASE.replace('配置扫频', '开始对数扫频'))['request']['spacing'], 'log')
        self.assertTrue(parse_command(PHRASE.replace('配置扫频', '开始扫频'))['enable'])
        self.assertEqual(parse_command('设置正弦波频率一兆赫兹幅度五百毫伏峰峰值')['request']['amplitude_vpp'], .5)
        for number, value in (('一万',10000),('十万',100000),('一百万',1000000),('一万零二',10002)):
            self.assertEqual(parse_command(PHRASE.replace('十千',number))['request']['stop_hz'],value)

    def test_all_actions(self):
        for phrase in ('查询信号发生器状态','开始扫频','暂停扫频','继续扫频','停止扫频','触发扫频','开启信号输出','关闭信号输出'):
            self.assertEqual(parse_command(phrase)['intent'], 'generator_control')

    def test_individual_frequency_and_peak_to_peak(self):
        for text in ('设置信号发生器频率为5KHZ','设置信号发生器频率五千赫兹'):
            self.assertEqual(parse_command(text)['request']['frequency_hz'],5000)
        for text, value in (('设置信号发生器峰峰值1V',1),('修改信号发生器峰峰值为五百毫伏',.5)):
            self.assertEqual(parse_command(text)['request']['amplitude_vpp'],value)
        for text in ('设置信号发生器频率五伏','设置信号发生器峰峰值一赫兹','设置信号发生器峰峰值1',
                     '设置信号发生器频率5mHz'):
            with self.subTest(text=text),self.assertRaises(ValueError):
                parse_command(text)

    def test_reject_missing_units_bounds_or_extra_words(self):
        for text in (PHRASE.replace('一伏峰峰值','一伏'), PHRASE.replace('一百赫兹','一百'),
                     PHRASE.replace('五秒','零秒'), PHRASE.replace('一伏峰峰值','十一伏峰峰值'),
                     PHRASE+'然后开启输出', PHRASE.replace('十千赫兹','一百赫兹'),
                     PHRASE.replace('十千赫兹','二十兆赫兹').replace('一伏峰峰值','两伏峰峰值')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_command(text)


class Driver:
    config_path = '/fake/binding.json'
    usb_resources = staticmethod(lambda backend: ['resource'])
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail
    def execute(self, request):
        self.calls.append(copy.deepcopy(request))
        raw = success(request)
        if request['action'] == 'output':
            raw['state']['output'] = request['state'].upper()
        if self.fail == request['action']:
            raw.update(status='failed', valid=False, error_code='USB_TIMEOUT', detail='no reply')
        return raw


BOARD = SimpleNamespace(EXPECTED_SERIAL='DG4E184950519', device_lock=lambda path: nullcontext(),
                        load_binding=lambda path: dict(serial='DG4E184950519', usb_route='1-1.2'),
                        devices=lambda: [], select_device=lambda *args: {}, visa_resource=lambda *args: 'resource')


class SequenceTests(unittest.TestCase):
    def test_config_off_then_on_in_one_lock(self):
        d = Driver()
        result = execute_job(dict(request=parse_command(PHRASE)['request'], enable=True), BOARD, d)
        self.assertTrue(result['valid'])
        self.assertEqual([r['action'] for r in d.calls], ['sweep','output'])
        self.assertEqual(result['state']['output'], 'ON')
        self.assertFalse(result['electrical_output_verified'])

    def test_failed_configuration_never_enables(self):
        d = Driver('sweep')
        raw = execute_job(dict(request=parse_command(PHRASE)['request'], enable=True), BOARD, d)
        self.assertFalse(raw['valid'])
        self.assertEqual(len(d.calls), 1)

    def test_resume_rechecks_reviewed_state(self):
        request = dict(action='resume', channel=2)
        d = Driver()
        raw = execute_job(dict(request=request, expected_state=copy.deepcopy(STATE)), BOARD, d)
        self.assertTrue(raw['valid'])
        expected = dict(STATE, amplitude=2.)
        d = Driver()
        raw = execute_job(dict(request=request, expected_state=expected), BOARD, d)
        self.assertFalse(raw['valid'])
        self.assertEqual([r['action'] for r in d.calls], ['status'])

    def test_no_resume_after_stop_or_without_preview(self):
        for state in (dict(STATE, sweep='OFF'), STATE):
            d = Driver()
            with patch(__name__+'.success', side_effect=lambda r: dict(success_original(r), state=state)):
                raw = execute_job(dict(request=dict(action='resume',channel=2)), BOARD, d)
            self.assertFalse(raw['valid'])
            self.assertEqual(len(d.calls), 1)

    def test_partial_change_rechecks_snapshot_before_any_write(self):
        d=Driver()
        job=dict(request=parse_command(PHRASE)['request'],enable=False,expected_state=dict(STATE,amplitude=2))
        raw=execute_job(job,BOARD,d)
        self.assertFalse(raw['valid'])
        self.assertEqual([r['action'] for r in d.calls],['status'])


success_original = success


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.store = RecordStore(ROOT/'asr_runtime', self.root/'records')
        self.calls = []
        self.control = GeneratorControl(dict(root=str(self.root), channels=[2]), self.store, self.root, self.run_cli)
    def tearDown(self):
        self.tmp.cleanup()
    def run_cli(self, argv, **kwargs):
        self.calls.append(argv)
        self.assertNotIn('shell', kwargs)
        request = json.loads(argv[argv.index('--job')+1])['request']
        return subprocess.CompletedProcess(argv, 0, json.dumps(success(request)), '')
    def value(self, phrase=PHRASE):
        return dict(text=phrase, simulated=False, command=parse_command(phrase))

    def test_save_retry_does_not_reexecute_and_history_is_real_result(self):
        value = self.control.prepare(self.value())
        with patch.object(self.store, 'save_generator_result', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.control.save(value, 'one')
        row = self.control.save(value, 'one')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.control.save(value,'one')['record_id'], row['record_id'])
        self.assertEqual(len(self.store.list_page(0,6)['rows']), 1)
        document = json.loads(next((self.root/'records').glob('record_*.json')).read_text(encoding='utf-8'))
        self.assertEqual(document['record_kind'], 'generator_control')
        self.assertFalse(document['control_result']['electrical_output_verified'])
        start = self.control.prepare(self.value('开始扫频'))
        self.assertTrue(start['command']['enable'])
        self.assertEqual(start['command']['request'], value['command']['request'])

    def test_start_requires_template_and_non_ch2_is_blocked(self):
        for phrase in ('开始扫频','通道一查询扫频状态'):
            with self.assertRaises(ValueError):
                self.control.prepare(self.value(phrase))
        self.assertEqual(self.calls, [])

    def test_started_but_missing_receipt_is_never_replayed(self):
        import hashlib
        self.control.directory.mkdir(parents=True)
        value = self.value()
        path = self.control.directory/(hashlib.sha256(b'ambiguous').hexdigest()+'.json')
        job = dict(request=value['command']['request'], enable=False)
        path.write_text(json.dumps(dict(job=job)), encoding='utf-8')
        row = self.control.save(value,'ambiguous')
        self.assertEqual(row['status'], '执行失败')
        self.assertEqual(self.calls, [])

    def test_status_preview_is_reused_on_archive(self):
        value = self.control.prepare(self.value('查询信号发生器状态'))
        self.control.preview(value,'query',threading.Event())
        self.control.save(value,'query')
        self.assertEqual(len(self.calls), 1)

    def test_cli_plan_is_not_success_and_no_automatic_retry(self):
        self.control.runner = lambda *args,**kwargs: subprocess.CompletedProcess([],0,json.dumps(dict(
            success(dict(action='stop',channel=2)),status='planned')), '')
        value = self.value('停止扫频')
        row = self.control.save(value,'failed')
        self.assertEqual(row['status'],'执行失败')
        self.assertEqual(self.control.save(value,'failed')['record_id'],row['record_id'])

    def test_frequency_changes_to_fixed_sine_preserves_readback_voltage(self):
        v=self.control.prepare(self.value('设置信号发生器频率为5KHZ'))
        self.assertTrue(self.control.needs_preview(v))
        self.control.preview(v,'freq',threading.Event())
        r=v['command']['request']
        self.assertEqual(r,dict(action='sine',channel=2,frequency_hz=5000.,amplitude_vpp=1.,offset_v=0.,load='highz'))
        self.assertFalse(v['command']['enable'])
        self.assertEqual(v['command']['expected_state'],STATE)
        self.assertIn('固定正弦波',v['summary'])

    def test_peak_to_peak_preserves_sweep_or_fixed_mode(self):
        v=self.control.prepare(self.value('设置信号发生器峰峰值500mV'))
        self.control.preview(v,'amp-sweep',threading.Event())
        r=v['command']['request']
        self.assertEqual(r['action'],'sweep')
        self.assertEqual(r['start_hz'],STATE['start_hz'])
        self.assertEqual(r['stop_hz'],STATE['stop_hz'])
        self.assertEqual(r['amplitude_vpp'],.5)
        original=self.control.runner
        def fixed(argv,**kwargs):
            p=original(argv,**kwargs);raw=json.loads(p.stdout);raw['state']['sweep']='OFF'
            return subprocess.CompletedProcess(argv,0,json.dumps(raw),'')
        self.control.runner=fixed
        v=self.control.prepare(self.value('设置信号发生器峰峰值1V'))
        self.control.preview(v,'amp-sine',threading.Event())
        self.assertEqual(v['command']['request']['action'],'sine')
        self.assertEqual(v['command']['request']['frequency_hz'],STATE['frequency_hz'])

    def test_non_vpp_or_wrong_waveform_rejects_without_conversion(self):
        for field,value in (('amplitude_unit','VRMS'),('waveform','SQU')):
            def changed(argv,**kwargs):
                request=json.loads(argv[-1])['request'];raw=success(request);raw['state'][field]=value
                return subprocess.CompletedProcess(argv,0,json.dumps(raw),'')
            self.control.runner=changed
            v=self.control.prepare(self.value('设置信号发生器峰峰值1V'))
            with self.assertRaises(ValueError):
                self.control.preview(v,field,threading.Event())


class ProtocolTests(unittest.TestCase):
    setUp = ReceiptTests.setUp
    run_cli = ReceiptTests.run_cli
    value = ReceiptTests.value

    def tearDown(self):
        if hasattr(self, 'thread'):
            self.input.queue.put('')
            self.thread.join(4)
            self.assertFalse(self.thread.is_alive())
        ReceiptTests.tearDown(self)

    def launch(self, phrase):
        from backend import Backend
        from command_executor import CommandExecutor
        from test_real_asr import QueueInput, QueueOutput, FakeRecognizer
        value = self.value(phrase)
        class Recognizer(FakeRecognizer):
            def recognize(engine, cancelled, progress):
                return value
        self.input, self.output = QueueInput(), QueueOutput()
        executor = CommandExecutor(SimpleNamespace(config={}), self.store, self.root)
        executor.generator = self.control
        self.backend = Backend(self.output, recognizer=Recognizer(), record_store=self.store, command_executor=executor)
        self.thread = threading.Thread(target=self.backend.run, args=(self.input,))
        self.thread.start()
        self.take('progress'); self.take('progress'); self.take('ready')

    def take(self, event):
        value = self.output.queue.get(timeout=3)
        self.assertEqual(value['event'], event, value)
        return value

    def send(self, action, name, target=None):
        self.input.queue.put(json.dumps(dict(protocol=1,id=name,action=action,target=target))+'\n')

    def test_configure_waits_for_confirmation_and_returns_existing_qt_protocol(self):
        self.launch(PHRASE)
        self.send('start','round'); self.take('state')
        self.assertIn('输出关闭', self.take('result')['summary'])
        self.assertEqual(self.calls, [])
        self.send('confirm','confirm','round'); self.take('state')
        done = self.take('confirmed')
        self.assertIn('DG4102',done['message'])
        self.assertEqual(done['effect'],'record_saved')
        self.assertEqual(len(self.calls),1)

    def test_status_preview_then_cancel_writes_no_history(self):
        self.launch('查询信号发生器状态')
        self.send('start','round'); self.take('state'); self.take('progress')
        self.assertIn('当前回读',self.take('result')['summary'])
        self.assertEqual(len(self.calls),1)
        self.send('cancel','cancel','round'); self.take('cancelled')
        self.assertEqual(self.store.list_page()['total'],0)


if __name__ == '__main__':
    unittest.main()
