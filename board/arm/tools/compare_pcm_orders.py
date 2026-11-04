"""Compare byte orders using existing native stereo files; no new capture."""
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import numpy as np

PROJECT = Path('/home/root/labmate_b_audio_test')
sys.path.insert(0, str(PROJECT))
import board_audio

ROOT = Path('/home/root/labmate_audio_debug')


def decode(data, channel, order):
    if not data or len(data) % 8:
        raise ValueError('RAW_FRAME_LENGTH_ERROR')
    words = np.frombuffer(data, dtype='<u4').reshape(-1, 2)[:, channel]
    if order == 'LE':
        value = (words & 0xffffff).astype(np.int32)
    elif order == 'MSB':
        value = (((words & 0xff) << 16) | (words & 0xff00) |
                 ((words >> 16) & 0xff)).astype(np.int32)
    else:
        raise ValueError(order)
    value = (value ^ 0x800000) - 0x800000
    return value.astype(np.float32) / 8388608.0


def preview(audio, folder):
    peak = float(np.max(np.abs(audio)))
    # Listening gain only: same bounded peak target, at most 12x amplification.
    # The preserved raw and WAV data are never normalized or modified.
    gain = min(12.0, 0.20 / max(peak, 1e-12))
    padded = np.concatenate((np.zeros(88200), audio * gain, np.zeros(22050)))
    path = folder / 'preview.raw'
    np.repeat(np.rint(np.clip(padded, -1, 1) * 8388607).astype('<i4'), 2).tofile(str(path))
    with (folder / 'playback.log').open('ab') as log:
        process = subprocess.Popen(['aplay', '-q', '-D', 'default', '-t', 'raw',
                                    '-f', 'S24_LE', '-r', '44100', '-c', '2', str(path)],
                                   stdout=log, stderr=log)
        try:
            time.sleep(1)
            board_audio.run_command(['amixer', '-q', '-c', '0', 'sset', 'Output 2', '24'])
            board_audio.run_command(['amixer', '-q', '-c', '0', 'sset', 'Playback', '192,192'])
            if process.wait(timeout=20):
                raise RuntimeError('APLAY_FAILED')
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if path.exists():
                path.unlink()
    return gain


def main():
    batches = [path for path in ROOT.glob('batch_*') if path.is_dir()
               and list(path.glob('R*/native_stereo.raw'))]
    if not batches:
        raise RuntimeError('没有找到整轮测试保存的原始录音；请把这一条错误发回，不要重录。')
    batch = max(batches, key=lambda path: path.stat().st_mtime)
    sources = [batch / name / 'native_stereo.raw' for name in ('R2', 'R3')]
    sources = [path for path in sources if path.exists()]
    if not sources:
        sources = sorted(batch.glob('R*/native_stereo.raw'))[:2]
    output = ROOT / ('orders_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:6])
    output.mkdir()
    summary = ['SOURCE_BATCH ' + str(batch), 'OUTPUT ' + str(output),
               'LE=standard low-24 little-endian; MSB=previous byte-reordered decode']
    results = []
    try:
        for source in sources:
            data = source.read_bytes()
            frames = np.frombuffer(data, dtype=np.uint8).reshape(-1, 2, 4)
            summary.append('%s bytes=%d first64=%s padding_zero=%s' % (
                source.parent.name, len(data), data[:64].hex(),
                np.mean(frames[:, :, 3] == 0, axis=0).tolist()))
            for channel, channel_name in ((0, 'L'), (1, 'R')):
                for order in ('LE', 'MSB'):
                    label = source.parent.name + '_' + channel_name + '_' + order
                    audio = decode(data, channel, order)
                    stats = {'label': label, 'rms': float(np.sqrt(np.mean(audio ** 2))),
                             'peak': float(np.max(np.abs(audio))),
                             'clip_ratio': float(np.mean(np.abs(audio) >= 0.995))}
                    board_audio.write_wav_16k(output / (label + '.wav'), audio, 44100)
                    print('\nPLAY', label, '标准小端' if order == 'LE' else '之前的高位在前读法', flush=True)
                    try:
                        stats['listening_gain'] = preview(audio, output)
                        answer = input('听感：0人声清楚 / 1主要是杂音 / 2人声有鸭子音 / 3无声：').strip()
                        while answer not in ('0', '1', '2', '3'):
                            answer = input('请输入 0、1、2 或 3：').strip()
                        stats['heard'] = {'0': '清楚', '1': '杂音', '2': '鸭子音', '3': '无声'}[answer]
                    except Exception as error:
                        stats['error'] = str(error)
                    results.append(stats)
                    summary.append(json.dumps(stats, ensure_ascii=False))
                    (output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        summary.append('ORDER_COMPARE_DONE')
    finally:
        text = '\n'.join(summary) + '\n'
        (output / 'summary.txt').write_text(text, encoding='utf-8')
        print('\n===== ORDER_RESULT_BEGIN =====\n' + text + '===== ORDER_RESULT_END =====', flush=True)


if __name__ == '__main__':
    main()
