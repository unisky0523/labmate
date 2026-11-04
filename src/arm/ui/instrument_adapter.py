"""Call the existing instrument CLIs without importing USB/audio dependencies.

Python 3.7 compatible. One lock covers both scope reads and screen captures.
Only trusted configuration and whitelisted arguments enter subprocess argv.
"""
from datetime import datetime
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import threading


DEVICES = {'meter.read': 'suin_sa5041', 'scope.read': 'siglent_sds1202x',
           'scope.capture_screen': 'siglent_sds1202x'}
PARAMETERS = {'PKPK', 'AMPL', 'MAX', 'MIN', 'MEAN', 'RMS', 'TOP', 'BASE',
              'CMEAN', 'CRMS', 'FREQ', 'PER', 'RISE', 'FALL', 'PWID', 'NWID'}


def now():
    return datetime.now().astimezone().isoformat(timespec='milliseconds')


def reject_constant(value):
    raise ValueError('Non-finite JSON value: ' + value)


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)


def run_cli(argv, timeout, **options):
    """Reap the shell and its Python child together before releasing USB lock."""
    process = subprocess.Popen(argv, start_new_session=os.name == 'posix', **options)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        if os.name == 'posix':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.communicate()
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def validate_result(result, action):
    """Do not convert a failed measurement to zero or trust only top-level valid."""
    if not isinstance(result, dict) or result.get('device_id') != DEVICES[action]:
        raise ValueError('仪器回执的设备标识不匹配。')
    if result.get('simulated') is not False or result.get('source') != 'scpi':
        raise ValueError('仪器回执没有明确标记真实 SCPI 来源。')
    if result.get('status') not in ('complete', 'partial', 'failed'):
        raise ValueError('仪器回执状态无效。')
    if type(result.get('valid')) is not bool:
        raise ValueError('仪器回执缺少有效性标记。')
    if action == 'scope.capture_screen':
        if result['status'] == 'complete':
            if (result['valid'] is not True or not isinstance(result.get('image_path'), str)
                    or not result['image_path'] or type(result.get('image_bytes')) is not int
                    or result['image_bytes'] <= 0):
                raise ValueError('截图回执缺少有效文件。')
        return
    rows = result.get('measurements')
    if not isinstance(rows, list) or len(rows) > 32:
        raise ValueError('仪器测量项格式无效。')
    for item in rows:
        if not isinstance(item, dict) or type(item.get('valid')) is not bool:
            raise ValueError('测量项缺少有效性标记。')
        if item['valid']:
            if not numeric(item.get('value')) or not isinstance(item.get('unit'), str) or not item['unit']:
                raise ValueError('有效测量项缺少有限数值或单位。')
            if action == 'meter.read' and item.get('unit_scale_verified') is not True:
                raise ValueError('万用表单位倍率尚未确认。')
    valid_count = sum(item['valid'] for item in rows)
    expected = 'complete' if rows and valid_count == len(rows) else 'partial' if valid_count else 'failed'
    if result['status'] != expected or result['valid'] != (expected == 'complete'):
        raise ValueError('仪器顶层状态与逐项状态不一致。')


def measurement_text(item):
    channel = str(item.get('channel') or '')
    label = ('通道' + channel + ' ' if channel else '') + str(item.get('label') or item.get('measurement_id') or '数据')
    if item.get('valid') is not True:
        return label + '读取失败（' + str(item.get('error_code') or 'INVALID') + '）'
    return '%s %s %s' % (label, item['value'], item['unit'])


def result_text(entry):
    result = entry['result']
    name = '万用表' if entry['action'] == 'meter.read' else '示波器'
    if entry['action'] == 'scope.capture_screen' and result['status'] == 'complete':
        return name + '屏幕截图已保存（%d 字节）' % result['image_bytes']
    items = result.get('measurements', [])
    if items:
        return name + '：' + '；'.join(measurement_text(item) for item in items)
    return name + '：读取失败（' + str(result.get('error_code') or 'FAILED') + '）'


class InstrumentAdapter:
    def __init__(self, configuration, runner=run_cli):
        self.config = configuration
        self.runner = runner
        self.lock = threading.Lock()
        self.validate_config()

    @classmethod
    def from_file(cls, path):
        return cls(json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=reject_constant))

    def validate_config(self):
        if not isinstance(self.config, dict):
            raise ValueError('仪器配置必须是对象。')
        for key in ('meter', 'scope'):
            device = self.config.get(key)
            if not isinstance(device, dict) or not isinstance(device.get('root'), str):
                raise ValueError('仪器配置缺少部署目录：' + key)
            if not Path(device['root']).is_absolute():
                raise ValueError('仪器部署目录必须是绝对路径。')
        scope = self.config['scope']
        if not isinstance(scope.get('resource'), str) or not scope['resource']:
            raise ValueError('请先枚举并明确配置示波器 resource。')
        channels, parameters = scope.get('channels', [1]), scope.get('parameters', ['PKPK', 'FREQ', 'RMS'])
        if (not isinstance(channels, list) or not channels or len(channels) > 2
                or any(type(ch) is not int or ch not in (1, 2) for ch in channels)):
            raise ValueError('示波器通道仅支持 1、2。')
        if (not isinstance(parameters, list) or not parameters or len(parameters) > 16
                or any(not isinstance(p, str) or p not in PARAMETERS for p in parameters)):
            raise ValueError('示波器测量参数不在白名单内。')
        for key, default in (('query_timeout_ms', 3000), ('screen_timeout_ms', 15000)):
            value = self.config.get(key, default)
            if type(value) is not int or not 100 <= value <= 60000:
                raise ValueError('仪器查询超时无效：' + key)

    def call(self, action, request_id):
        if action not in DEVICES:
            raise ValueError('不支持的仪器动作。')
        device = self.config['meter' if action == 'meter.read' else 'scope']
        root = Path(device['root'])
        screenshot = action == 'scope.capture_screen'
        query_ms = self.config.get('screen_timeout_ms', 15000) if screenshot else self.config.get('query_timeout_ms', 3000)
        script = 'c_instrument/run_meter_board.sh' if action == 'meter.read' else 'c_instrument/run_scope_board.sh'
        output = root / 'c_instrument/runs'
        argv = ['sh', script, '--request-id', request_id, '--timeout-ms', str(query_ms), '--out', str(output)]
        if action != 'meter.read':
            argv += ['--resource', device['resource']]
            if screenshot:
                argv += ['--screenshot']
            else:
                argv += ['--channels'] + [str(ch) for ch in device.get('channels', [1])]
                argv += ['--measure'] + device.get('parameters', ['PKPK', 'FREQ', 'RMS'])
        # The meter may perform eight queries; the scope has IDN plus every
        # requested measurement. This is an action deadline, not one query.
        queries = 2 if screenshot else 8 if action == 'meter.read' else 1 + len(device.get('channels', [1])) * len(device.get('parameters', ['PKPK', 'FREQ', 'RMS']))
        timeout = 10 + queries * query_ms / 1000.0
        with self.lock:
            try:
                if not (root / script).is_file():
                    raise FileNotFoundError('找不到仪器启动脚本：' + str(root / script))
                from contextlib import nullcontext
                from sweep_response import scope_guard
                with (scope_guard() if action != 'meter.read' else nullcontext()):
                    completed = self.runner(argv, cwd=str(root), stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, universal_newlines=True,
                                            encoding='utf-8', errors='replace', timeout=timeout)
                if len(completed.stdout) > 1024 * 1024:
                    raise ValueError('仪器 JSON 超过大小限制。')
                result = json.loads(completed.stdout, parse_constant=reject_constant)
                validate_result(result, action)
                if completed.returncode not in (0, 2) or (completed.returncode == 0) != (result['status'] == 'complete'):
                    raise ValueError('仪器退出码与 JSON 状态不一致。')
                if action != 'scope.capture_screen' and result.get('request_id') != request_id:
                    raise ValueError('仪器请求编号不匹配。')
                if screenshot and result['status'] == 'complete':
                    path = Path(result['image_path']).resolve()
                    path.relative_to(output.resolve())
                    if not path.is_file() or path.stat().st_size != result['image_bytes']:
                        raise ValueError('截图文件不存在或大小不匹配。')
                return dict(request_id=request_id, action=action, result=result,
                            stderr=completed.stderr[-2048:], returncode=completed.returncode)
            except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as error:
                code = 'ACTION_TIMEOUT' if isinstance(error, subprocess.TimeoutExpired) else 'ADAPTER_FAILED'
                result = dict(request_id=request_id, device_id=DEVICES[action], source='scpi',
                              simulated=False, valid=False, status='failed', measurements=[],
                              captured_at=now(), error_code=code, detail=str(error)[:2048])
                return dict(request_id=request_id, action=action, result=result, stderr='', returncode=None)
