"""Continuous sweep observation. Frequencies are measured, never inferred from time."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from fft_protocol import read_json, write_json


@contextmanager
def scope_guard():
    # Shared by the collector, scalar adapter and waveform reader on the board.
    if os.name != 'posix':
        yield
        return
    import fcntl
    with open('/tmp/labmate_host4.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('HOST4 正在采集扫频曲线或波形，请稍后再读取示波器。')
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def start_observer(config):
    out = Path(config['directory'])
    out.mkdir(parents=True, exist_ok=True)
    write_json(out/'config.json', config)
    with (out/'worker.log').open('ab') as log:
        p = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--config', str(out/'config.json')],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    deadline = time.monotonic()+8
    while time.monotonic() < deadline:
        if (out/'ready.json').exists():
            return dict(directory=str(out), status='armed', pid=p.pid)
        if (out/'result.json').exists() or p.poll() is not None:
            return dict(directory=str(out), status='failed', detail='示波器响应采集未就绪，查看 worker.log')
        time.sleep(.02)
    # The child also has a bounded wait, so it cannot leave an orphan capture.
    return dict(directory=str(out), status='failed', detail='示波器响应采集准备超时')


def mark_start(observer):
    if observer and observer['status'] == 'armed':
        write_json(Path(observer['directory'])/'start.json', dict(monotonic=time.monotonic(),
                   requested_at=datetime.now(timezone.utc).isoformat()))
        observer['status'] = 'collecting'


def measure_pairs(io, duration, started, clock=time.monotonic, wait=time.sleep, cancelled=lambda:False, on_point=lambda p:None):
    from scope_waveform import quantity
    points = []
    while clock()-started < duration and len(points) < 2000:
        if cancelled():
            break
        row = dict(index=len(points), valid=False)
        fatal = False
        try:
            row['frequency_query_start_s'] = clock()-started
            fraw = io.query('C1:PAVA? FREQ')
            row['frequency_query_end_s'] = clock()-started
            row['vpp_query_start_s'] = clock()-started
            vraw = io.query('C1:PAVA? PKPK')
            row['vpp_query_end_s'] = clock()-started
            hz, vpp = quantity(fraw, 'Hz'), quantity(vraw, 'V')
            row.update(frequency_reply=fraw, vpp_reply=vraw)
            if not 0 < hz <= 1e9 or not 0 <= vpp <= 1e6 or cancelled():
                raise ValueError('Invalid measured frequency/peak-to-peak')
            row.update(valid=True, frequency_hz=hz, vpp_v=vpp,
                       pair_span_s=row['vpp_query_end_s']-row['frequency_query_start_s'])
        except ValueError as error:
            row['error'] = str(error)
        except Exception as error:
            row['error'] = str(error)
            # A timed-out late USB reply must never be paired with another query.
            fatal = True
        points.append(row)
        on_point(row)
        if fatal:
            break
        wait(.01)
    return points


def make_plot_data(points, config):
    good = [p for p in points if p.get('valid') and
            min(config['start_hz'], config['stop_hz'])*.9 <= p['frequency_hz'] <= max(config['start_hz'], config['stop_hz'])*1.1]
    good.sort(key=lambda p:p['frequency_hz'])
    if len({p['frequency_hz'] for p in good}) < 2:
        raise ValueError('有效频率点不足，不能绘制响应曲线；原始测量记录已保留。')
    peak = max(good, key=lambda p:p['vpp_v'])
    return dict(kind='sweep_response', backend='scope_scpi', channel=1,
                frequencies_hz=[p['frequency_hz'] for p in good],
                amplitudes_vpeak=[p['vpp_v'] for p in good],
                peak_frequency_hz=peak['frequency_hz'], peak_amplitude_vpeak=peak['vpp_v'],
                captured_at=config['started_at'], point_count=len(good),
                requested_start_hz=config['start_hz'], requested_stop_hz=config['stop_hz'],
                warning='Continuous sweep: sequential measurements, approximate response; not transfer gain')


def run(config):
    directory = Path(config['directory'])
    result = dict(status='failed', mode='continuous', simultaneous=False, points=[],
                  source='SDS1202X / HOST4 / CH1', directory=str(directory))
    try:
        root = Path(config['scope']['root'])
        sys.path[:0] = [str(root/'c_instrument/vendor'), str(root)]
        sys.path.append(str(root/'c_instrument/compat_py37'))
        from c_instrument.transport import VisaTransport
        import usb.core
        d = usb.core.find(idVendor=0xf4ec, idProduct=0xee3a)
        if d is None or d.serial_number != 'SDS1XDC4163410' or d.bus != 1 or d.port_numbers != (1,4):
            raise ValueError('HOST4 scope identity/route mismatch')
        with scope_guard():
            io = VisaTransport(config['scope']['resource'], '@py', 1000)
            try:
                identity = io.query('*IDN?')
                if 'SDS1202X,SDS1XDC4163410' not in identity.replace(' ', ''):
                    raise ValueError('Scope identity mismatch')
                mode = io.query('TRMD?').upper().split()[-1]
                if mode not in ('AUTO', 'NORM'):
                    raise ValueError('请先将示波器设为自动或普通运行状态，再记录连续扫频。')
                write_json(directory/'ready.json', dict(identity=identity))
                deadline = time.monotonic()+15
                while not (directory/'start.json').exists():
                    if time.monotonic() > deadline:
                        raise ValueError('未收到本次扫频启动标记')
                    time.sleep(.01)
                start = read_json(directory/'start.json')
                config['started_at'] = start['requested_at']
                with (directory/'points.jsonl').open('a') as evidence:
                    def checkpoint(point):
                        evidence.write(json.dumps(point, allow_nan=False)+'\n')
                        evidence.flush()
                        if point['index'] % 10 == 0:
                            os.fsync(evidence.fileno())
                    result['points'] = measure_pairs(io, config['duration_s'], start['monotonic'],
                            cancelled=lambda:(directory/'cancel.json').exists(), on_point=checkpoint)
                    os.fsync(evidence.fileno())
            finally:
                io.close()
        # Checkpoint actual evidence before plotting or loading Qt.
        result.update(status='measured', started_at=config['started_at'], duration_s=config['duration_s'])
        write_json(directory/'result.json', result)
        if not (directory/'control.json').exists() or read_json(directory/'control.json').get('valid') is not True:
            raise ValueError('扫频输出开启未确认，不生成成功响应曲线。')
        with (directory/'points.csv').open('w') as f:
            f.write('index,frequency_hz,vpp_v,frequency_query_start_s,vpp_query_end_s,valid\n')
            for p in result['points']:
                f.write(','.join(str(p.get(k,'')) for k in ('index','frequency_hz','vpp_v','frequency_query_start_s','vpp_query_end_s','valid'))+'\n')
        plot = make_plot_data(result['points'], config)
        result.update(observed_min_hz=min(plot['frequencies_hz']), observed_max_hz=max(plot['frequencies_hz']))
        write_json(directory/'plot.json', plot)
        binary = Path(config['renderer'])
        if b'LABMATE_UI_RESPONSE_V1' not in binary.read_bytes():
            raise ValueError('请安装支持扫频响应绘图的新 Qt 程序；测量数据已保留。')
        p = subprocess.run([str(binary), '--render-spectrum', str(directory/'plot.json'), str(directory/'response.png')],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
                           env=dict(os.environ, QT_QPA_PLATFORM='offscreen'))
        if p.returncode or not (directory/'response.png').is_file():
            raise ValueError('响应曲线绘图失败：'+p.stderr.decode('utf-8','replace')[-300:])
        partial = ((directory/'cancel.json').exists() or
                   any(not p.get('valid') for p in result['points']) or len(result['points']) == 2000 or
                   result['observed_max_hz']-result['observed_min_hz'] < .8*abs(config['stop_hz']-config['start_hz']))
        result.update(status='partial' if partial else 'complete', image_path=str(directory/'response.png'), point_count=plot['point_count'])
    except Exception as error:
        result.update(status='failed', detail=str(error))
    write_json(directory/'result.json', result)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    run(read_json(p.parse_args().config))
