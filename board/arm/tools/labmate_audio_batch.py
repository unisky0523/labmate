"""One-session board audio audit. No application dispatch or source edits."""
import contextlib
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import traceback
from uuid import uuid4

import numpy as np

PROJECT = Path('/home/root/labmate_b_audio_test')
sys.path.insert(0, str(PROJECT))

import asr_cli
import board_audio
import board_mic
from board_app import load_vosk_model, DEFAULT_MODEL

ROOT = Path('/home/root/labmate_audio_debug')
TRIALS = [('S0', '', 3), ('R1', '读取数据', 5),
          ('R2', '记录电压三点三伏', 5), ('R3', '记录电压三点六伏', 5),
          ('R4', '记录电压三点三伏', 5)]
PLAY_NOTES = {'0': '清楚', '1': '杂音', '2': '鸭子音', '3': '无声', '4': '杂音和鸭子音'}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def command(args):
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=5, universal_newlines=True, errors='replace')
        return {'code': result.returncode, 'text': result.stdout[-20000:]}
    except Exception as error:
        return {'error': str(error)}


def read(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace')[:20000]
    except OSError as error:
        return str(error)


def snapshot(path, active=False):
    result = {'time': datetime.now().isoformat(), 'load': read('/proc/loadavg'),
              'ps': command(['ps']), 'mixer': command(['amixer', '-c', '0', 'scontents']),
              'capture_hw': read('/proc/asound/card0/pcm1c/sub0/hw_params'),
              'playback_hw': read('/proc/asound/card0/pcm0p/sub0/hw_params')}
    if active:
        result['registers'] = {reg: command(['i2cget', '-f', '-y', '0', '0x10', reg, 'b'])
                               for reg in ('0x0a', '0x03', '0x0d', '0x18')}
    write_json(path, result)


def metrics(audio, rate):
    blocks = audio[:len(audio) // (rate // 10) * (rate // 10)].reshape(-1, rate // 10)
    rms = np.sqrt(np.mean(blocks ** 2, axis=1))
    return {'rms': float(np.sqrt(np.mean(audio ** 2))),
            'peak': float(np.max(np.abs(audio))),
            'clip_ratio': float(np.mean(np.abs(audio) >= 0.995)),
            'dc': float(np.mean(audio)), 'block_rms_100ms': rms.tolist()}


def capture(folder, seconds, silent):
    decoder = board_mic._decode_s24le
    configure = board_mic.configure_es8388_mic
    workers = []
    worker_errors = []

    def active_snapshot():
        try:
            snapshot(folder / 'active.json', active=True)
        except Exception as error:
            worker_errors.append(str(error))

    def configure_and_observe():
        result = configure()
        worker = threading.Thread(target=active_snapshot)
        worker.daemon = True
        workers.append(worker)
        worker.start()
        return result

    def preserve(data, *args, **kwargs):
        (folder / 'native_stereo.raw').write_bytes(data)
        return decoder(data, *args, **kwargs)

    class Output:
        def write(self, text):
            if silent:
                text = text.replace('现在开始说话', '现在保持安静，不要说话')
            return sys.__stdout__.write(text)

        def flush(self):
            sys.__stdout__.flush()

    board_mic._decode_s24le = preserve
    board_mic.configure_es8388_mic = configure_and_observe
    try:
        with contextlib.redirect_stdout(Output()):
            left16, metadata = board_mic.capture_16k_mono(seconds, channel=0)
    finally:
        board_mic._decode_s24le = decoder
        board_mic.configure_es8388_mic = configure
        for worker in workers:
            worker.join(timeout=30)
    metadata['snapshot_errors'] = worker_errors
    write_json(folder / 'capture.json', metadata)
    raw = (folder / 'native_stereo.raw').read_bytes()
    if len(raw) != seconds * 44100 * 8:
        raise RuntimeError('RAW_LENGTH_MISMATCH')
    left = decoder(raw, 2, 0, byte_order='little')
    right = decoder(raw, 2, 1, byte_order='little')
    right16 = board_audio.resample_linear(right, 44100, 16000)
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 2, 4)
    layout = {'padding_zero_ratio': np.mean(frames[:, :, 3] == 0, axis=0).tolist(),
              'unique_bytes': [[int(np.unique(frames[:, ch, byte]).size)
                                for byte in range(4)] for ch in range(2)]}
    write_json(folder / 'layout.json', layout)
    return [('L44', left, 44100), ('L16', left16, 16000),
            ('R44', right, 44100), ('R16', right16, 16000)], metadata, layout


def play(audio, rate, folder):
    audio = board_audio.resample_linear(audio, rate, 44100)
    padded = np.concatenate((np.zeros(88200), audio * 0.25, np.zeros(22050)))
    raw = folder / 'preview.raw'
    np.repeat(np.rint(np.clip(padded, -1, 1) * 8388607).astype('<i4'), 2).tofile(str(raw))
    log = folder / 'playback.log'
    with log.open('ab') as stream:
        process = subprocess.Popen(['aplay', '-q', '-D', 'default', '-t', 'raw',
                                    '-f', 'S24_LE', '-r', '44100', '-c', '2', str(raw)],
                                   stdout=stream, stderr=stream)
        try:
            time.sleep(1)
            board_audio.run_command(['amixer', '-q', '-c', '0', 'sset', 'Output 2', '32'])
            board_audio.run_command(['amixer', '-q', '-c', '0', 'sset', 'Playback', '192,192'])
            if process.wait(timeout=20):
                raise RuntimeError('APLAY_FAILED; see playback.log')
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if raw.exists():
                raw.unlink()


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(str(ROOT)).free < 40 * 1024 * 1024:
        raise RuntimeError('需要至少 40 MB 可用空间；未开始录音。')
    folder = ROOT / ('batch_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:6])
    folder.mkdir()
    summary = ['OUTPUT ' + str(folder), 'NO_APPLICATION_DISPATCH']
    rows, captures = [], []
    try:
        environment = {'uname': command(['uname', '-a']), 'python': sys.version,
                       'numpy': np.__version__, 'meminfo': read('/proc/meminfo'),
                       'asound': read('/proc/asound/pcm'), 'asound_conf': read('/etc/asound.conf'),
                       'cpuinfo': read('/proc/cpuinfo'),
                       'cpu_frequency': read('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq'),
                       'cpu_governor': read('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'),
                       'dmesg': command(['dmesg'])}
        environment['source_sha256'] = {name: hashlib.sha256((PROJECT / name).read_bytes()).hexdigest()
                                       for name in ('board_mic.py', 'board_audio.py', 'asr_cli.py',
                                                    'board_app.py', 'models/vosk-model-small-cn-0.22/conf/model.conf')}
        write_json(folder / 'environment.json', environment)
        summary.extend(['KERNEL ' + environment['uname'].get('text', '').strip(),
                        'CPU_FREQ ' + environment['cpu_frequency'].strip(),
                        'CPU_GOVERNOR ' + environment['cpu_governor'].strip()])
        snapshot(folder / 'before.json')
        print('结果目录：', folder, flush=True)
        print('正在加载模型。此测试不会保存实验记录，也不会执行识别出的命令。', flush=True)
        model, error = load_vosk_model(DEFAULT_MODEL)
        if model is None:
            raise RuntimeError(error)
        for label, expected, seconds in TRIALS:
            trial = folder / label
            trial.mkdir()
            print('\n本轮', label, '：', expected or '保持安静，不要说话', flush=True)
            input('准备好后按回车；等开始提示再说，只说一次：')
            started = time.monotonic()
            try:
                cases, metadata, layout = capture(trial, seconds, not expected)
            except Exception:
                error = traceback.format_exc()
                write_json(trial / 'capture_error.json', {'error': error})
                summary.append('CAPTURE_ERROR %s %s' % (label, error))
                print('本轮录音失败，已保存错误，继续下一轮。', flush=True)
                continue
            elapsed = time.monotonic() - started
            report = {name: metrics(audio, rate) for name, audio, rate in cases}
            write_json(trial / 'metrics.json', report)
            for name, audio, rate in cases:
                board_audio.write_wav_16k(trial / (name + '.wav'), audio, rate)
            summary.append('%s expected=%s capture=%.2fs padding=%s' % (
                label, expected or 'SILENCE', elapsed, layout['padding_zero_ratio']))
            for name in ('L44', 'L16', 'R44', 'R16'):
                value = report[name]
                summary.append('%s %s RMS=%.5f PEAK=%.5f CLIP=%.6f DC=%.5f' % (
                    label, name, value['rms'], value['peak'], value['clip_ratio'], value['dc']))
            active = json.loads((trial / 'active.json').read_text(encoding='utf-8')) if (trial / 'active.json').exists() else {}
            registers = {key: value.get('text', value.get('error', '')).strip()
                         for key, value in active.get('registers', {}).items()}
            summary.append('%s ACTIVE_REGISTERS %s' % (label, json.dumps(registers)))
            summary.append('%s CAPTURE_HW %s' % (label, active.get('capture_hw', '').replace('\n', ' / ')))
            summary.append('%s PLAYBACK_HW %s' % (label, active.get('playback_hw', '').replace('\n', ' / ')))
            section = []
            selected = False
            for line in active.get('mixer', {}).get('text', '').splitlines():
                if line.startswith('Simple mixer control'):
                    selected = any("'%s'" % control in line for control in (
                        'ALC Capture Function', 'Left Channel', 'Right Channel', 'Capture Digital Volume'))
                if selected:
                    section.append(line.strip())
            summary.append('%s ACTIVE_MIXER %s' % (label, ' / '.join(section)))
            captures.append((label, expected, trial, cases))
            write_json(folder / 'progress.json', {'last_capture': label})

        print('\n录音完成，开始回听。0清楚，1杂音，2鸭子音，3无声，4杂音加鸭子音。', flush=True)
        print('L=左路，R=右路；44=转换前，16=转换后。每段后输入听感编号。', flush=True)
        for label, expected, trial, cases in captures:
            if not expected:
                continue
            for name, audio, rate in cases:
                print('\nPLAY', label, expected, name, flush=True)
                try:
                    play(audio, rate, trial)
                    note = input('听感编号 0/1/2/3/4：').strip()
                    while note not in PLAY_NOTES:
                        note = input('请输入 0、1、2、3 或 4：').strip()
                    summary.append('HEARD %s %s %s' % (label, name, PLAY_NOTES[note]))
                except Exception as error:
                    summary.append('PLAY_ERROR %s %s %s' % (label, name, error))

        print('\n开始自动识别对比，约需数分钟，不需要再说话。', flush=True)
        for label, expected, trial, cases in captures:
            for name, audio, rate in cases:
                if rate != 16000:
                    continue
                modes = [('NORMAL', None), ('WORDS', asr_cli.GRAMMAR_JSON)] if expected else [('WORDS', asr_cli.GRAMMAR_JSON)]
                for mode, grammar in modes:
                    print('ASR', label, name, mode, flush=True)
                    started = time.perf_counter()
                    try:
                        result = asr_cli.transcribe(audio, model, grammar=grammar)
                        seconds = time.perf_counter() - started
                        cmd, score, reason = asr_cli._evaluate_transcript(result['text'], result['words'], 0.45)
                        quality = asr_cli.audio_problem(audio)
                        reference = asr_cli.parse_command(expected) if expected else None
                        correct = (asr_cli.semantic_key(cmd) == asr_cli.semantic_key(reference)) if expected else cmd is None
                        row = {'trial': label, 'expected': expected, 'channel': name, 'mode': mode,
                               'seconds': seconds, 'text': result['text'], 'correct_semantics': correct,
                               'quality_warning': quality, 'min_confidence': score, 'parse_reason': reason,
                               'would_pass_checks': cmd is not None and quality is None}
                        write_json(trial / (name + '_' + mode + '.json'), dict(row, transcript=result))
                        rows.append(row)
                        summary.append('ASR %s %s %s %.2fs text=%s correct=%s quality=%s' % (
                            label, name, mode, seconds, result['text'], correct, quality))
                    except Exception as error:
                        summary.append('ASR_ERROR %s %s %s %s' % (label, name, mode, error))
                    write_json(folder / 'asr_results.json', rows)
        snapshot(folder / 'after.json')
        write_json(folder / 'dmesg_after.json', command(['dmesg']))
        summary.append('BATCH_DONE')
    except BaseException:
        summary.append('BATCH_INTERRUPTED\n' + traceback.format_exc())
    finally:
        text = '\n'.join(summary) + '\n'
        (folder / 'summary.txt').write_text(text, encoding='utf-8')
        print('\n===== RESULT_BEGIN =====\n' + text + '===== RESULT_END =====', flush=True)
        print('请把 RESULT_BEGIN 到 RESULT_END 的全部内容发回。', flush=True)
        print('所有原始录音、转换录音和配置快照已保存在：', folder, flush=True)


if __name__ == '__main__':
    main()
