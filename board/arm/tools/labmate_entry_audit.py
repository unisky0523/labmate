"""One serial session: audit the real board entry without editing project sources."""
import builtins
from contextlib import ExitStack, contextmanager
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
from uuid import uuid4

import numpy as np

PROJECT = Path('/home/root/labmate_b_audio_test')
ROOT = Path('/home/root/labmate_audio_debug')
REFERENCE = ROOT / 'batch_20230420_062226_bdd17b'
EXPECTED_MIC_SHA = '9e94ca5cffcf0c3ee061a6e0a44e756c1ba6b90a3a57cc8e5c0bc6fceeea7c15'
sys.path.insert(0, str(PROJECT))
import board_app
import board_audio
import board_mic
import asr_cli

TRIALS = [('S0', '保持安静，不说话'), ('R1', '读取数据'),
          ('R2', '记录电压三点三伏'), ('R3', '记录电压三点六伏'),
          ('R4', '记录电压三点三伏')]
NOTES = {'0': '人声清楚', '1': '主要是杂音', '2': '鸭子音',
         '3': '无声', '4': '杂音和鸭子音', '5': '没听清，跳过'}


@contextmanager
def patched(obj, name, value):
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def read(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace')[:20000]
    except OSError as error:
        return str(error)


def command(args):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=5, universal_newlines=True, errors='replace')
        return {'code': p.returncode, 'text': p.stdout[-12000:]}
    except Exception as error:
        return {'error': str(error)}


def decode(data, channel, order):
    if not data or len(data) % 8:
        raise ValueError('RAW_FRAME_LENGTH_ERROR')
    words = np.frombuffer(data, dtype='<u4').reshape(-1, 2)[:, channel]
    if order == 'LE':
        values = (words & 0xffffff).astype(np.int32)
    elif order == 'MSB':
        values = (((words & 0xff) << 16) | (words & 0xff00)
                  | ((words >> 16) & 0xff)).astype(np.int32)
    else:
        raise ValueError(order)
    return ((values ^ 0x800000) - 0x800000).astype(np.float32) / 8388608.0


def stats(audio):
    audio = np.asarray(audio, dtype=np.float32)
    if not len(audio):
        return {'samples': 0}
    blocks = audio[:len(audio) // 1600 * 1600].reshape(-1, 1600)
    return {'samples': len(audio), 'rms': float(np.sqrt(np.mean(audio ** 2))),
            'peak': float(np.max(np.abs(audio))), 'dc': float(np.mean(audio)),
            'clip_ratio': float(np.mean(np.abs(audio) >= .995)),
            'block_rms_100ms': np.sqrt(np.mean(blocks ** 2, axis=1)).tolist(),
            'quality_gate': asr_cli.audio_problem(audio)}


def recognize(audio, model, expected, grammar):
    start = time.perf_counter()
    result = asr_cli.transcribe(audio, model, grammar=grammar)
    cmd, confidence, reason = asr_cli._evaluate_transcript(result['text'], result['words'], .45)
    correct = None if expected is None else (
        asr_cli.semantic_key(cmd) == asr_cli.semantic_key(asr_cli.parse_command(expected)))
    return {'text': result['text'], 'seconds': round(time.perf_counter() - start, 2),
            'correct': correct, 'confidence': confidence, 'reason': reason,
            'transcript': result, 'stats': stats(audio)}


def real_entry(folder, model, report):
    """Keep board_app's capture, status callbacks and ASR path; block actions only."""
    original_input = builtins.input
    original_capture = board_mic.capture_16k_mono
    original_decoder = board_mic._decode_s24le
    original_process = asr_cli.process
    original_run = board_audio.run_command
    state = {'index': 0, 'folder': None, 'label': None, 'commands': []}

    def next_input(prompt=''):
        if not prompt.startswith('LabMate[board]>'):
            raise RuntimeError('UNEXPECTED_INTERACTIVE_PROMPT: ' + prompt)
        if state['index'] >= len(TRIALS):
            return 'q'
        label, phrase = TRIALS[state['index']]
        state['index'] += 1
        state['label'] = label
        state['folder'] = folder / label
        state['folder'].mkdir()
        print('\n[%d/%d] %s：%s' % (state['index'], len(TRIALS), label, phrase), flush=True)
        answer = original_input('准备好按回车；看到“现在开始说话”再说。输入 q 结束整轮：').strip()
        if answer.lower() == 'q':
            report.append('USER_STOPPED_CAPTURE')
            return 'q'
        return ''

    def traced_run(args, *a, **kw):
        row = {'args': list(args), 'time': time.monotonic()}
        state['commands'].append(row)
        try:
            result = original_run(args, *a, **kw)
            row['result'] = result
            return result
        except Exception as error:
            row['error'] = str(error)
            raise

    def preserve(data, *a, **kw):
        (state['folder'] / 'native_stereo.raw').write_bytes(data)
        return original_decoder(data, *a, **kw)

    def capture(*a, **kw):
        target = state['folder']
        state['commands'] = []
        started = time.monotonic()
        try:
            audio, metadata = original_capture(*a, **kw)
            np.save(str(target / 'entry_audio.npy'), audio)
            board_audio.write_wav_16k(target / 'entry_audio.wav', audio)
            write_json(target / 'capture.json', metadata)
            write_json(target / 'entry_stats.json', stats(audio))
            report.append('%s CAPTURE %.2fs layout=%s channel=%s errors=%s' % (
                state['label'], time.monotonic() - started, metadata.get('pcm_layout'),
                metadata.get('selected_channel'), metadata.get('capture_errors')))
            return audio, metadata
        except Exception as error:
            report.append('%s CAPTURE_ERROR %s' % (state['label'], error))
            write_json(target / 'capture_error.json', {'error': str(error)})
            raise
        finally:
            write_json(target / 'commands.json', state['commands'])

    def process(*a, **kw):
        result, exit_requested = original_process(*a, **kw)
        write_json(state['folder'] / 'live_asr.json', result)
        report.append('%s LIVE text=%s reason=%s' % (
            state['label'], result.get('text'), result.get('reason')))
        return result, False

    def no_dispatch(self, text, input_context=None):
        print('[本轮诊断] 已完成识别与解析；不写入实验记录。')
        return False

    args = ['board_app.py', '--source', 'mock', '--seconds', '5',
            '--mic-channel', '0', '--command-grammar']
    with ExitStack() as stack:
        stack.enter_context(patched(sys, 'argv', args))
        stack.enter_context(patched(builtins, 'input', next_input))
        stack.enter_context(patched(board_app, 'load_vosk_model', lambda path: (model, None)))
        stack.enter_context(patched(board_mic, 'capture_16k_mono', capture))
        stack.enter_context(patched(board_mic, '_decode_s24le', preserve))
        stack.enter_context(patched(board_audio, 'run_command', traced_run))
        stack.enter_context(patched(asr_cli, 'process', process))
        stack.enter_context(patched(board_app.TextApplication, 'handle_text', no_dispatch))
        board_app.main()


def preview(audio, rate, folder):
    audio = board_audio.resample_linear(audio, rate, 44100)
    gain = min(12.0, .20 / max(float(np.max(np.abs(audio))), 1e-12))
    padded = np.concatenate((np.zeros(88200), audio * gain, np.zeros(22050)))
    path = folder / 'preview.raw'
    np.repeat(np.rint(np.clip(padded, -1, 1) * 8388607).astype('<i4'), 2).tofile(str(path))
    with (folder / 'playback.log').open('ab') as log:
        p = subprocess.Popen(['aplay', '-q', '-D', 'default', '-t', 'raw',
                              '-f', 'S24_LE', '-r', '44100', '-c', '2', str(path)],
                             stdout=log, stderr=log)
        try:
            time.sleep(1)
            board_audio.run_command(['amixer', '-q', '-c', '0', 'sset', 'Output 2', '24'])
            board_audio.run_command(['amixer', '-q', '-c', '0', 'sset', 'Playback', '192,192'])
            if p.wait(timeout=20):
                raise RuntimeError('APLAY_FAILED: see playback.log')
        finally:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
            path.unlink()
    return gain


def audit_versions(folder, report):
    env = {'python': sys.version, 'numpy': np.__version__, 'uname': command(['uname', '-a']),
           'load': read('/proc/loadavg'), 'memory': read('/proc/meminfo'),
           'asound_conf': read('/etc/asound.conf'), 'alsa': read('/proc/asound/pcm'),
           'processes': command(['ps']), 'dmesg': command(['dmesg']),
           'tools': {name: shutil.which(name) for name in
                     ('arecord', 'aplay', 'amixer', 'i2cset', 'i2cget', 'espeak', 'espeak-ng')}}
    env['sources'] = {}
    for module in (board_app, board_mic, board_audio, asr_cli):
        path = Path(module.__file__)
        content = path.read_text(encoding='utf-8').replace('\r\n', '\n')
        env['sources'][module.__name__] = {'path': str(path),
            'normalized_sha256': hashlib.sha256(content.encode()).hexdigest()}
    write_json(folder / 'environment.json', env)
    for name, row in env['sources'].items():
        report.append('MODULE %s %s %s' % (name, row['path'], row['normalized_sha256']))
    report.append('TTS ' + str({k: env['tools'][k] for k in ('espeak', 'espeak-ng')}))
    for log in sorted((PROJECT / 'data/asr_logs').glob('asr_20230420_064*.json'))[-6:]:
        try:
            data = json.loads(log.read_text(encoding='utf-8'))
            write_json(folder / ('old_' + log.name), data)
            report.append('OLD_LOG %s text=%s metadata=%s' % (
                log.name, data.get('text'), json.dumps(data.get('metadata', {}), ensure_ascii=False)))
        except Exception as error:
            report.append('OLD_LOG_ERROR %s %s' % (log.name, error))
    if env['sources']['board_mic']['normalized_sha256'] != EXPECTED_MIC_SHA:
        raise RuntimeError('MIC_VERSION_MISMATCH: 未更改源码；请发回汇总，先核对版本。')
    missing = [k for k in ('arecord', 'aplay', 'amixer', 'i2cset') if not env['tools'][k]]
    if missing:
        raise RuntimeError('MISSING_TOOLS ' + ','.join(missing))


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(str(ROOT)).free < 80 * 1024 * 1024:
        print('可用空间不足 80 MB，未开始测试。')
        return
    folder = ROOT / ('entry_audit_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:6])
    folder.mkdir()
    report = ['OUTPUT ' + str(folder), 'ACTUAL_BOARD_APP_ENTRY; NO_EXPERIMENT_RECORD_DISPATCH']
    rows, clips = [], []

    def check(label, audio, expected, mode='WORDS'):
        print('正在检查', label, mode, flush=True)
        try:
            row = recognize(audio, model, expected, asr_cli.GRAMMAR_JSON if mode == 'WORDS' else None)
            row.update(label=label, mode=mode)
            report.append('%s %s %.2fs text=%s correct=%s reason=%s' % (
                label, mode, row['seconds'], row['text'], row['correct'], row['reason']))
            rows.append(row)
            write_json(folder / 'offline_results.json', rows)
        except Exception as error:
            report.append('%s %s ERROR %s' % (label, mode, error))

    try:
        audit_versions(folder, report)
        print('正在加载模型，随后录五段音。S0 要保持安静，其他按提示说。', flush=True)
        model, error = board_app.load_vosk_model(board_app.DEFAULT_MODEL)
        if model is None:
            raise RuntimeError(error)
        # Saved controls are read from the exact previously successful batch.
        for label, expected in (('R2', TRIALS[2][1]), ('R3', TRIALS[3][1])):
            path = REFERENCE / label / 'native_stereo.raw'
            if path.exists():
                native = decode(path.read_bytes(), 0, 'LE')
                check('OLD_' + label + '_L_LE', board_audio.resample_linear(native, 44100, 16000), expected)
                if label == 'R2':
                    clips.append(('以前的3.3伏录音，LE左声道', native, 44100))
            else:
                report.append('REFERENCE_MISSING ' + str(path))
        old_bad = sorted((PROJECT / 'data/audio/asr_tests').glob('asr_20230420_064*.wav'))[-2:]
        for path in old_bad:
            try:
                rate, audio = board_audio.read_wav_mono(path)
                check('FAILED_' + path.stem, board_audio.resample_linear(audio, rate, 16000), None)
                if path == old_bad[-1]:
                    clips.append(('此前只识别成负或伏的录音', audio, rate))
            except Exception as error:
                report.append('OLD_WAV_ERROR %s %s' % (path.name, error))
        real_entry(folder, model, report)
        print('\n录音结束。下面自动比较，无需说话；请等回放提示。', flush=True)
        for label, phrase in TRIALS:
            target = folder / label
            raw_path = target / 'native_stereo.raw'
            if not raw_path.exists():
                report.append(label + ' NO_RAW')
                continue
            if not (target / 'entry_audio.npy').exists():
                report.append(label + ' RAW_SAVED_BUT_CAPTURE_FAILED')
                continue
            data = raw_path.read_bytes()
            frames = np.frombuffer(data, dtype=np.uint8).reshape(-1, 2, 4)
            layout = {'bytes': len(data), 'first64': data[:64].hex(),
                      'padding_zero': np.mean(frames[:, :, 3] == 0, axis=0).tolist()}
            write_json(target / 'layout.json', layout)
            report.append('%s RAW %s' % (label, json.dumps(layout)))
            entry = np.load(str(target / 'entry_audio.npy'))
            expected = None if label == 'S0' else phrase
            check(label + '_ENTRY_REPLAY', entry, expected)
            left = board_audio.resample_linear(decode(data, 0, 'LE'), 44100, 16000)
            delta = float(np.max(np.abs(entry - left))) if entry.shape == left.shape else None
            report.append('%s ENTRY_VS_LE max_abs_diff=%s stats=%s' % (
                label, delta, json.dumps(stats(entry), ensure_ascii=False)))
            if label == 'S0':
                continue
            for channel, cname in ((0, 'L'), (1, 'R')):
                for order in ('LE', 'MSB'):
                    native = decode(data, channel, order)
                    converted = board_audio.resample_linear(native, 44100, 16000)
                    board_audio.write_wav_16k(target / (cname + '_' + order + '_16k.wav'), converted)
                    # The entry replay already checks identical standard-left audio.
                    if channel or order != 'LE' or delta != 0:
                        check(label + '_' + cname + '_' + order, converted, expected)
                    if label == 'R2':
                        clips.append(('本轮3.3伏 %s %s' % (cname, order), native, 44100))
            if label in ('R2', 'R3'):
                check(label + '_ENTRY_REPLAY', entry, expected, 'NORMAL')
            if label == 'R2':
                clips.append(('本轮3.3伏 正式入口16k录音', entry, 16000))
        after = {
            'mixer': command(['amixer', '-c', '0', 'scontents']),
            'registers_after_streams_closed': {reg: command(['i2cget', '-f', '-y', '0', '0x10', reg, 'b'])
                for reg in ('0x0a', '0x03', '0x0d', '0x18')},
            'dmesg': command(['dmesg'])}
        write_json(folder / 'after_capture.json', after)
        report.append('REGISTERS_AFTER_STREAMS_CLOSED ' + json.dumps(
            after['registers_after_streams_closed'], ensure_ascii=False))
        selected = False
        for line in after['mixer'].get('text', '').splitlines():
            if line.startswith('Simple mixer control'):
                selected = any("'%s'" % control in line for control in (
                    'ALC Capture Function', 'Left Channel', 'Right Channel'))
            if selected:
                report.append('MIXER_AFTER_STREAMS_CLOSED ' + line.strip())
        print('\n现在回放并填写听感。只是播放已有录音，不用说话。', flush=True)
        for label, audio, rate in clips:
            print('\nPLAY', label, flush=True)
            try:
                gain = preview(audio, rate, folder)
                answer = input('0清楚 / 1杂音 / 2鸭子音 / 3无声 / 4杂音和鸭子音 / 5跳过：').strip()
                while answer not in NOTES:
                    answer = input('请输入 0～5：').strip()
                report.append('HEARD %s %s gain=%.4f' % (label, NOTES[answer], gain))
            except Exception as error:
                report.append('PLAYBACK_ERROR %s %s' % (label, error))
        report.append('ENTRY_AUDIT_DONE')
    except (Exception, KeyboardInterrupt) as error:
        report.append('ENTRY_AUDIT_INCOMPLETE %s: %s' % (type(error).__name__, error))
        (folder / 'exception.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        text = '\n'.join(report) + '\n'
        (folder / 'summary.txt').write_text(text, encoding='utf-8')
        print('\n===== FINAL_RESULT_BEGIN =====\n' + text + '===== FINAL_RESULT_END =====', flush=True)


if __name__ == '__main__':
    main()
