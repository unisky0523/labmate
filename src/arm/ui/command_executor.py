"""Business dispatch for accepted ASR results; never changes the ASR runtime."""
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time

from instrument_adapter import InstrumentAdapter, now, result_text, validate_result


class CommandExecutor:
    def __init__(self, adapter, store, evidence_dir, clock=time.monotonic, wait=time.sleep):
        self.adapter, self.store = adapter, store
        self.directory = Path(evidence_dir)
        self.lock = threading.Lock()
        self.clock, self.wait = clock, wait
        self.generator = None
        self.fft = None
        if adapter.config.get('fft'):
            from fft_control import FFTControl
            self.fft = FFTControl(adapter.config['fft'], adapter.config['scope'], store, self.directory)
        if adapter.config.get('generator'):
            from generator_control import GeneratorControl
            generator_config = dict(adapter.config['generator'], scope=adapter.config['scope'])
            self.generator = GeneratorControl(generator_config, store, self.directory)

    @staticmethod
    def batch_parameters(result):
        command = result['command']
        count, interval = command.get('count', 1), command.get('interval', 1)
        if type(count) is not int or not 1 <= count <= 100:
            raise ValueError('记录次数须为 1—100 的整数。')
        if type(interval) not in (int, float) or not math.isfinite(interval) or not 0 <= interval <= 60:
            raise ValueError('时间间隔须为 0—60 秒。')
        return count, float(interval)

    @classmethod
    def from_file(cls, path, store):
        if store is None:
            raise ValueError('仪器对接需要可用的记录存储。')
        adapter = InstrumentAdapter.from_file(path)
        directory = adapter.config.get('evidence_dir') or str(store.directory.parent / 'instrument_jobs')
        if not Path(directory).is_absolute():
            raise ValueError('仪器证据目录必须是绝对路径。')
        return cls(adapter, store, directory)

    def handles(self, result):
        command = result.get('command') or {}
        return command.get('intent') in ('read', 'record_device', 'capture_image', 'save_waveform', 'generator_control', 'fft_analyze')

    def fft_for(self):
        if self.fft is None:
            raise ValueError('FFT 采样与分析接口尚未配置。')
        return self.fft

    def generator_for(self):
        if self.generator is None:
            raise ValueError('尚未部署信号发生器配置与驱动，未执行任何设置。')
        return self.generator

    def needs_preview(self, result):
        if result['command']['intent'] == 'generator_control':
            return self.generator_for().needs_preview(result)
        return result['command']['intent'] in ('read', 'fft_analyze')

    def actions(self, result):
        command = result['command']
        intent = command['intent']
        if intent == 'save_waveform':
            raise ValueError('当前接口尚未提供原始波形采样点。需要屏幕截图请说“拍一下波形”，核对“示波器屏幕截图”提示后确认。')
        if intent == 'capture_image':
            if '摄像头' in result.get('text', '').replace(' ', ''):
                raise ValueError('当前对接使用示波器 USB 截图；摄像头采集尚未接入。')
            return ['scope.capture_screen']
        if intent == 'record_device':
            self.batch_parameters(result)
        if intent in ('read', 'record_device'):
            return ['meter.read', 'scope.read']
        raise ValueError('没有可执行的仪器动作。')

    def describe(self, result):
        if result['command']['intent'] == 'fft_analyze':
            self.fft_for()
            return '通过 HOST4 获取 SDS1202X CH1 原始采样，提交 FPGA FFT，绘制频谱。'
        if result['command']['intent'] == 'generator_control':
            return self.generator_for().prepare(result)['summary']
        actions = self.actions(result)
        if actions == ['scope.capture_screen']:
            return '确认后通过 USB 保存示波器屏幕截图并归档；不包含原始波形采样点。'
        description = '万用表当前值；示波器通道 %s 的 %s。确认后采集并保存。' % (
            '、'.join(str(ch) for ch in self.adapter.config['scope'].get('channels', [1])),
            '、'.join(self.adapter.config['scope'].get('parameters', ['PKPK', 'FREQ', 'RMS'])))
        if result['command']['intent'] == 'record_device':
            count, interval = self.batch_parameters(result)
            if count > 1:
                description += '\n连续记录 %d 次，时间间隔 %g 秒；每次单独保存。间隔按采集启动计算，读取超时顺延，不补赶。' % (count, interval)
        return description

    def path_for(self, operation_id):
        return self.directory / (hashlib.sha256(operation_id.encode('utf-8')).hexdigest() + '.json')

    def acquire(self, result, operation_id, cancelled=None):
        """Persist each completed action; retrying archive never re-queries USB."""
        actions = self.actions(result)
        path = self.path_for(operation_id)
        with self.lock:
            receipt = dict(request_id=operation_id, actions=actions, devices=[], created_at=now())
            if path.exists():
                receipt = json.loads(path.read_text(encoding='utf-8'))
                if receipt.get('request_id') != operation_id or receipt.get('actions') != actions:
                    raise ValueError('已有仪器回执与本轮请求不一致。')
                for entry in receipt['devices']:
                    validate_result(entry['result'], entry['action'])
            for index, action in enumerate(actions):
                if index < len(receipt['devices']):
                    continue
                if cancelled is not None and cancelled.is_set():
                    return None
                entry = self.adapter.call(action, operation_id + '-' + str(index + 1))
                receipt['devices'].append(entry)
                receipt['completed_at'] = now()
                self.directory.mkdir(parents=True, exist_ok=True)
                self.store.core.write_json_atomically(path, receipt)
                with path.open('r+b') as stream:
                    os.fsync(stream.fileno())
            statuses = [entry['result']['status'] for entry in receipt['devices']]
            receipt['acquisition_status'] = ('complete' if all(s == 'complete' for s in statuses)
                                             else 'failed' if all(s == 'failed' for s in statuses) else 'partial')
            receipt['receipt_path'] = str(path.resolve())
            return receipt

    def preview(self, result, operation_id, cancelled):
        if result['command']['intent'] == 'fft_analyze':
            with self.lock:
                return self.fft_for().preview(result, operation_id, cancelled)
        if result['command']['intent'] == 'generator_control':
            return self.generator_for().preview(result, operation_id, cancelled)
        receipt = self.acquire(result, operation_id, cancelled)
        if receipt is None:
            return None
        value = dict(result)
        value['summary'] = '\n'.join(result_text(entry) for entry in receipt['devices'])
        value['summary'] += '\n核对后确认保存本次读数，取消不写入实验历史。'
        return value

    def save(self, result, operation_id):
        if result['command']['intent'] == 'fft_analyze':
            return self.fft_for().save(result, operation_id)
        if result['command']['intent'] == 'generator_control':
            return self.generator_for().save(result, operation_id)
        if result['command']['intent'] == 'record_device' and self.batch_parameters(result)[0] > 1:
            return self.save_batch(result, operation_id)
        receipt = self.acquire(result, operation_id)
        return self.store.save_instrument_result(result, operation_id, receipt)

    def save_batch(self, result, operation_id):
        """Archive each real pair separately; retry uses durable per-round receipts.

        The user confirms the whole batch once. A committed save runs to completion,
        like existing single saves, so Qt requires no new protocol or recompilation.
        """
        count, interval = self.batch_parameters(result)
        rows = []
        next_start = None
        for index in range(count):
            round_id = '%s-batch-%d' % (operation_id, index + 1)
            value = dict(result, batch=dict(operation_id=operation_id, index=index + 1,
                                           count=count, interval_seconds=interval))
            try:
                path = self.path_for(round_id)
                cached = path.is_file() and len(json.loads(path.read_text(encoding='utf-8'))['devices']) == 2
                if not cached and next_start is not None:
                    remaining = next_start - self.clock()
                    if remaining > 0:
                        self.wait(remaining)
                started = self.clock()
                receipt = self.acquire(value, round_id)
                row = self.store.save_instrument_result(value, round_id, receipt)
            except Exception as failure:
                raise RuntimeError('连续记录已保存 %d/%d 次；再次确认可继续本批，不会重复采集已完成读数：%s' % (
                    len(rows), count, failure)) from failure
            rows.append(row)
            if not cached:
                next_start = started + interval
        complete = sum(row['status'] == '完成' for row in rows)
        summary = dict(rows[-1])
        summary['content'] = '连续记录已保存 %d/%d 次（两台均成功 %d 次）；最后一条：%s' % (
            len(rows), count, complete, rows[-1]['content'])
        summary['batch_count'] = count
        summary['batch_complete_count'] = complete
        return summary
