"""Capture once, invoke a configured PL bridge, and retain a spectrum for history."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import threading

from fft_protocol import make_request, read_json, write_json, decode_response, valid_n, validate_request


def validate_saved_fft(raw):
    if (not isinstance(raw, dict) or raw.get('status') not in ('complete', 'waiting_for_fpga')
            or raw.get('physical_port') != 'HOST4' or raw.get('channel') != 1
            or not valid_n(raw.get('fft_size')) or not isinstance(raw.get('request_id'), str)
            or raw.get('valid') is not (raw['status'] == 'complete')):
        raise ValueError('Invalid FFT result')
    if raw['valid'] and (raw.get('backend') != 'fpga' or not raw.get('image_path')
                         or not isinstance(raw.get('spectrum'), dict)):
        raise ValueError('Complete FFT result lacks FPGA spectrum/image')
    return raw


def summary(raw):
    if raw['status'] == 'waiting_for_fpga':
        return ('SDS1202X / HOST4 / CH1 已获取采样，FFT %d 点；等待 FPGA 接口。'
                '\n可保存本次采样任务；FPGA 接通后返回频谱。') % raw['fft_size']
    s = raw['spectrum']
    return ('FPGA 频谱：CH1，主峰频点 %g Hz，幅度 %g Vpeak；N=%d，频点间距 %g Hz。'
            '\n已生成频谱图，确认后保存到历史记录。') % (
                s['peak_frequency_hz'], s['peak_amplitude_vpeak'], raw['fft_size'], s['bin_spacing_hz'])


def render_spectrum(executable, spectrum_path, image_path, runner=subprocess.run):
    executable = Path(executable)
    if not executable.is_file() or b'LABMATE_UI_FFT_V1' not in executable.read_bytes():
        raise ValueError('频谱绘图程序尚未编译，请先安装带 FFT 窗口的新 Qt 程序。')
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    result = runner([str(executable), '--render-spectrum', str(spectrum_path), str(image_path)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, env=env)
    if result.returncode or not Path(image_path).is_file() or Path(image_path).read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('频谱图生成失败：'+result.stderr.decode('utf-8', 'replace')[-400:])


class FFTControl:
    def __init__(self, config, scope, store, evidence_dir, runner=subprocess.run, renderer=render_spectrum):
        self.config, self.scope, self.store = config, scope, store
        self.directory = Path(evidence_dir)/'fft'
        self.runner, self.renderer = runner, renderer
        self.lock = threading.Lock()
        self.n = config.get('fft_size', 4096)
        if not valid_n(self.n):
            raise ValueError('FFT 点数必须为 256—65536 之间的 2 的整数次幂。')
        self.worker = config.get('worker_argv', [])
        if (not isinstance(self.worker, list) or any(not isinstance(x, str) for x in self.worker)
                or (self.worker and not Path(self.worker[0]).is_absolute())):
            raise ValueError('FPGA worker_argv 必须为可信配置中的绝对路径参数数组。')

    def job_path(self, operation_id):
        return self.directory/hashlib.sha256(operation_id.encode()).hexdigest()

    def acquire(self, operation_id, cancelled):
        directory = self.job_path(operation_id)
        directory.mkdir(parents=True, exist_ok=True)
        request_path = directory/'request.json'
        if not request_path.exists():
            if cancelled.is_set():
                return None
            argv = [sys.executable, str(Path(__file__).with_name('scope_waveform.py')),
                    '--root', self.scope['root'], '--resource', self.scope['resource'],
                    '--channel', '1', '--out', str(directory)]
            # Per-query timeouts are in the child. Allow time to restore the scope
            # before an outer deadline; never cancel a child in its STOP window.
            result = self.runner(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
            if result.returncode:
                raise ValueError('HOST4 波形采集失败：'+result.stderr.decode('utf-8', 'replace')[-450:])
            capture = read_json(directory/'capture.json')
            make_request(directory, operation_id, capture, self.n)
        request = read_json(request_path)
        if request['request_id'] != operation_id:
            raise ValueError('FFT task id differs from cached capture')
        validate_request(request, directory)
        if cancelled.is_set():
            return None
        return directory, request

    def analyze(self, operation_id, cancelled):
        with self.lock:
            acquired = self.acquire(operation_id, cancelled)
            if acquired is None:
                return None
            directory, request = acquired
            response_path = directory/'response.json'
            if self.worker and not response_path.exists():
                if not Path(self.worker[0]).is_file():
                    raise ValueError('配置的 FPGA FFT 程序不存在。')
                result = self.runner(self.worker+['--request', str(directory/'request.json'),
                                      '--response', str(response_path)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
                if result.returncode:
                    raise ValueError('FPGA FFT 执行失败：'+result.stderr.decode('utf-8', 'replace')[-400:])
                if not response_path.exists():
                    raise ValueError('FPGA 程序未返回 response.json。')
            if cancelled.is_set():
                return None
            raw = dict(status='waiting_for_fpga', valid=False, backend='pending',
                       request_id=operation_id, physical_port='HOST4', channel=1,
                       fft_size=request['fft_size'], job_directory=str(directory.resolve()),
                       captured_at=request['capture']['captured_at'], image_path=None)
            if response_path.exists():
                spectrum = decode_response(request, read_json(response_path), directory)
                write_json(directory/'spectrum.json', spectrum)
                self.renderer(self.config.get('renderer', str(Path(__file__).with_name('labassistant'))),
                              directory/'spectrum.json', directory/'spectrum.png')
                # Large point arrays remain in spectrum.json, outside the UI protocol.
                small = {k:v for k,v in spectrum.items() if k != 'amplitudes_vpeak'}
                raw.update(status='complete', valid=True, backend='fpga', spectrum=small,
                           image_path=str((directory/'spectrum.png').resolve()))
            validate_saved_fft(raw)
            write_json(directory/'analysis.json', raw)
            return raw

    def preview(self, value, operation_id, cancelled):
        raw = self.analyze(operation_id, cancelled)
        if raw is None:
            return None
        return dict(value, summary=summary(raw), fft_result=raw,
                    spectrum_image_path=raw.get('image_path') or '')

    def save(self, value, operation_id):
        raw = read_json(self.job_path(operation_id)/'analysis.json')
        if raw['request_id'] != operation_id:
            raise ValueError('FFT 保存任务不匹配。')
        return self.store.save_fft_result(value, operation_id, raw)
