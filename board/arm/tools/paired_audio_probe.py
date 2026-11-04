"""Board diagnostic only: preserve one raw stereo capture and compare stages.

Uses the deployed capture routine and settings without modifying its source.
The decode wrapper exists only in this Python process and saves the exact
post-warmup bytes passed to the application's decoder.
"""
from datetime import datetime
import json
from pathlib import Path
import subprocess
import time
from uuid import uuid4

import numpy as np

import board_audio
import board_mic


def play(audio, rate, raw):
    samples = board_audio.resample_linear(audio, rate, 44100)
    samples = np.concatenate((np.zeros(88200), samples * 0.25, np.zeros(22050)))
    values = np.rint(np.clip(samples, -1, 1) * 8388607).astype('<i4')
    np.repeat(values, 2).tofile(str(raw))
    process = subprocess.Popen(['aplay', '-q', '-D', 'default', '-t', 'raw',
                                '-f', 'S24_LE', '-r', '44100', '-c', '2', str(raw)])
    try:
        time.sleep(1)
        board_audio.run_command(['amixer', '-q', '-c', '0', 'sset', 'Output 2', '32'])
        board_audio.run_command(['amixer', '-q', '-c', '0', 'sset', 'Playback', '192,192'])
        code = process.wait(timeout=20)
        if code:
            raise RuntimeError('aplay failed: %s' % code)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    folder = Path('/home/root/labmate_audio_debug') / (
        'paired_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    decoder = board_mic._decode_s24le
    raw_path = folder / 'native_stereo.raw'

    def save_then_decode(data, *args, **kwargs):
        raw_path.write_bytes(data)
        return decoder(data, *args, **kwargs)

    print('OUTPUT', folder, flush=True)
    print('等待“现在开始说话”后，只说一次：记录电压三点三伏。', flush=True)
    board_mic._decode_s24le = save_then_decode
    try:
        left16, metadata = board_mic.capture_16k_mono(5, channel=0)
    finally:
        board_mic._decode_s24le = decoder
    (folder / 'capture.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2),
                                       encoding='utf-8')
    raw = raw_path.read_bytes()
    assert len(raw) == 5 * 44100 * 8, 'RAW_LENGTH_MISMATCH'
    left = decoder(raw, 2, 0, byte_order='little')
    right = decoder(raw, 2, 1, byte_order='little')
    right16 = board_audio.resample_linear(right, 44100, 16000)
    cases = [('1_LEFT_44K', left, 44100), ('2_LEFT_16K', left16, 16000),
             ('3_RIGHT_44K', right, 44100), ('4_RIGHT_16K', right16, 16000)]
    report = {}
    for name, audio, rate in cases:
        stats = {'rms': float(np.sqrt(np.mean(audio ** 2))),
                 'peak': float(np.max(np.abs(audio))),
                 'clip_ratio': float(np.mean(np.abs(audio) >= 0.995)),
                 'dc': float(np.mean(audio))}
        report[name] = stats
        board_audio.write_wav_16k(folder / (name + '.wav'), audio, rate)
        print('METRICS', name, json.dumps(stats), flush=True)
    (folder / 'metrics.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    for name, audio, rate in cases:
        print('PLAY', name, flush=True)
        play(audio, rate, folder / (name + '_play.raw'))
        time.sleep(2)
    print('PROBE_DONE', folder, flush=True)


if __name__ == '__main__':
    main()
