"""Confirmed DG4102 jobs, durable receipts and real control-history entries."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from asr_runtime.generator_commands import describe_request, validate_request


def validate_control(raw):
    if (not isinstance(raw, dict) or raw.get('device_id') != 'rigol_dg4102'
            or raw.get('source') != 'scpi' or raw.get('simulated') is not False
            or raw.get('status') not in ('complete', 'failed')
            or raw.get('valid') is not (raw.get('status') == 'complete')):
        raise ValueError('信号发生器回执格式无效。')
    if raw['valid']:
        if (raw.get('identity_verified') is not True or not isinstance(raw.get('state'), dict)
                or raw['state'].get('output') not in ('ON', 'OFF')
                or not all(k in raw['state'] for k in ('sweep', 'start_hz', 'stop_hz', 'time_s',
                           'spacing', 'amplitude', 'amplitude_unit', 'offset_v', 'load'))):
            raise ValueError('信号发生器回执缺少真实身份或输出回读。')
    return raw


def state_text(raw):
    if not raw['valid']:
        return 'DG4102 执行失败，输出状态需重新查询：%s；%s' % (raw.get('error_code'), raw.get('detail', ''))
    s = raw['state']
    return ('DG4102 CH%d，输出 %s，%s，固定频率 %g Hz；扫频 %s，%g → %g Hz，%g 秒，%s，幅度 %g %s，'
            '偏置 %g V，负载设置 %s；仅为设备回读，未验证实际电信号。') % (
        raw['request']['channel'], s['output'], s['waveform'], s['frequency_hz'], s['sweep'], s['start_hz'], s['stop_hz'], s['time_s'],
        s['spacing'], s['amplitude'], s['amplitude_unit'], s['offset_v'], s['load'])


class GeneratorControl:
    def __init__(self, config, store, directory, runner=subprocess.run):
        self.config, self.store = config, store
        self.directory = Path(directory)/'generator'
        self.runner = runner

    def check(self, request):
        validate_request(request)
        if request['channel'] not in self.config.get('channels', [2]):
            raise ValueError('当前只接入了信号发生器 CH2，请说通道二或省略通道。')
        root = Path(self.config['root'])
        if not root.is_absolute():
            raise ValueError('信号发生器部署路径必须是绝对路径。')
        return root

    def prepare(self, value):
        command = value['command']
        if type(command.get('enable', False)) is not bool:
            raise ValueError('信号发生器开启标记须为布尔值。')
        request = command['request']
        self.check(request)
        if request['action'] == 'start_sweep':
            path = self.directory/('template_ch%d.json' % request['channel'])
            if not path.exists():
                raise ValueError('尚无成功配置的扫频参数，请先说完整的“配置扫频……”指令。')
            request = json.loads(path.read_text(encoding='utf-8'))
            if request.get('action') != 'sweep' or request.get('channel') != command['request']['channel']:
                raise ValueError('已保存的扫频模板无效，请重新配置。')
            self.check(request)
            command.update(request=request, enable=True)
        value['summary'] = describe_request(request, command.get('enable', False))
        if request['action'] == 'sweep' and command.get('enable') and self.config.get('scope'):
            value['summary'] += '\n连续扫频期间记录 HOST4 CH1 实测频率和峰峰值；曲线完成后可从本条历史打开。'
        return value

    def needs_preview(self, value):
        r = value['command']['request']
        return r['action'] in ('status', 'resume', 'adjust_frequency', 'adjust_amplitude') or (r['action'] == 'output' and r['state'] == 'on')

    def invoke(self, job):
        root = self.check(job['request'])
        argv = [sys.executable, str(Path(__file__).with_name('generator_runner.py')),
                '--root', str(root), '--job', json.dumps(job, allow_nan=False)]
        try:
            # Driver bounds every query. Do not kill a control halfway then replay it.
            p = self.runner(argv, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True)
            raw = json.loads(p.stdout)
            validate_control(raw)
            if (p.returncode == 0) != raw['valid']:
                raise ValueError('CLI exit status disagrees with DG result')
            return raw
        except Exception as error:
            return dict(device_id='rigol_dg4102', source='scpi', simulated=False,
                        status='failed', valid=False, request=job['request'], state_unknown=True,
                        error_code='DG_BRIDGE_FAILED', detail=str(error))

    def preview(self, value, operation_id, cancelled):
        request = value['command']['request']
        if cancelled.is_set():
            return None
        raw = self.receipt(dict(request=dict(action='status', channel=request['channel']), enable=False),
                           operation_id+'-preview')
        if not raw['valid']:
            raise ValueError(state_text(raw))
        if request['action'] == 'resume' and raw['state']['sweep'] != 'ON':
            raise ValueError('扫频模式已关闭；请用“开始扫频”重新配置，不能直接继续。')
        if request['action'] in ('adjust_frequency', 'adjust_amplitude'):
            s = raw['state']
            if s['waveform'] != 'SIN' or s['amplitude_unit'] != 'VPP':
                raise ValueError('当前不是 Vpp 单位的正弦波，不能自动换算；请先完整设置正弦波。')
            if s['load'] in ('INFINITY', 'INF'):
                load = 'highz'
            else:
                try:
                    if float(s['load']) != 50:
                        raise ValueError()
                    load = '50'
                except (TypeError,ValueError):
                    raise ValueError('当前负载设置不支持，请先完整设置正弦波。')
            resolved = dict(action='sine', channel=request['channel'], offset_v=s['offset_v'],load=load,
                            frequency_hz=s['frequency_hz'], amplitude_vpp=s['amplitude'])
            if request['action'] == 'adjust_frequency':
                resolved['frequency_hz'] = request['frequency_hz']
                note = '单改频率，切换为固定正弦波。'
            else:
                resolved['amplitude_vpp'] = request['amplitude_vpp']
                note = '单改峰峰值，保留当前模式及已回读参数。'
                if s['sweep'] == 'ON':
                    resolved.pop('frequency_hz')
                    resolved.update(action='sweep', start_hz=s['start_hz'],stop_hz=s['stop_hz'],time_s=s['time_s'],
                                    spacing=s['spacing'].lower(),trigger=s['trigger'].lower())
            self.check(resolved)
            value['command'].update(adjustment=request,request=resolved,enable=False,expected_state=s)
            value['summary'] = note + '\n' + describe_request(resolved,False)
        if request['action'] != 'status':
            value['command']['expected_state'] = raw['state']
        value['summary'] += '\n当前回读：' + state_text(raw)
        return value

    def receipt(self, job, operation_id):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory/(hashlib.sha256(operation_id.encode('utf-8')).hexdigest()+'.json')
        if path.exists():
            old = json.loads(path.read_text(encoding='utf-8'))
            if old['job'] != job:
                raise ValueError('已有信号发生器回执与本轮操作不一致。')
            if 'result' in old:
                return validate_control(old['result'])
            # A crash may have occurred after USB writes. Never replay an ambiguous job.
            return dict(device_id='rigol_dg4102', source='scpi', simulated=False, status='failed', valid=False,
                        request=job['request'], state_unknown=True, error_code='CONTROL_OUTCOME_UNKNOWN',
                        detail='上次操作已提交但未收到持久化回执。先重新查询状态；本轮不会重复执行。')
        document = dict(operation_id=operation_id, job=job)
        self.store.core.write_json_atomically(path, document)
        with path.open('r+b') as f:
            os.fsync(f.fileno())
        submitted = dict(job)
        active = self.directory/'active_response.json'
        if job['request']['action'] != 'status' and active.exists():
            from fft_protocol import read_json, write_json
            previous = read_json(active)
            if Path(previous['directory']).is_dir():
                write_json(Path(previous['directory'])/'cancel.json', dict(reason='发生器收到新的控制指令，停止本轮观测'))
        if (job['request']['action'] == 'sweep' and job.get('enable') and self.config.get('scope')
                and job['request'].get('trigger', 'int') == 'int'):
            r = job['request']
            submitted['response_capture'] = dict(scope=self.config['scope'],
                directory=str(self.store.directory/'sweep_responses'/hashlib.sha256(operation_id.encode()).hexdigest()),
                start_hz=r['start_hz'], stop_hz=r['stop_hz'], duration_s=r['time_s'],
                renderer=str(Path(__file__).with_name('labassistant')))
        raw = self.invoke(submitted)
        if raw.get('response_capture'):
            self.store.core.write_json_atomically(active, raw['response_capture'])
        document['result'] = raw
        self.store.core.write_json_atomically(path, document)
        with path.open('r+b') as f:
            os.fsync(f.fileno())
        if raw['valid'] and job['request']['action'] == 'sweep':
            self.store.core.write_json_atomically(
                self.directory/('template_ch%d.json' % job['request']['channel']), job['request'])
        return raw

    def save(self, value, operation_id):
        command = value['command']
        if command['request']['action'] == 'status':
            job = dict(request=command['request'], enable=False)
            raw = self.receipt(job, operation_id+'-preview')
        else:
            job = {key: command[key] for key in ('request', 'enable', 'expected_state') if key in command}
            raw = self.receipt(job, operation_id)
        return self.store.save_generator_result(value, operation_id, raw)
