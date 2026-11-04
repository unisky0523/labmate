"""Board-only: listen to the successful and failed saved WAVs, same volume."""
from pathlib import Path
import subprocess
import time
import numpy as np
import board_audio

source = Path('/home/root/labmate_b_audio_test/data/audio/asr_tests')
output = Path('/home/root/labmate_audio_debug')
output.mkdir(parents=True, exist_ok=True)
pairs = [('GOOD', 'asr_20230420_052531_865995_c43b775b.wav'),
         ('BAD', 'asr_20230420_054354_819689_cd6f4d9d.wav')]
# Validate both inputs before starting playback; never overwrite source WAVs.
recordings = [(label, board_audio.read_wav_mono(source / name)) for label, name in pairs]
for label, (rate, audio) in recordings:
    print(label, 'RMS', round(float(np.sqrt(np.mean(audio ** 2))), 5),
          'CLIP_RATIO', round(float(np.mean(np.abs(audio) >= 0.995)), 6), flush=True)
    samples = board_audio.resample_linear(audio, rate, 44100)
    # Fixed attenuation, identical for both files. Padding allows the codec
    # output controls to be applied after playback starts without losing speech.
    samples = np.concatenate((np.zeros(88200), samples * 0.25, np.zeros(22050)))
    raw = output / ('asr_compare_' + label.lower() + '.raw')
    values = np.rint(np.clip(samples, -1, 1) * 8388607).astype('<i4')
    np.repeat(values, 2).tofile(str(raw))
    print('PLAY', label, flush=True)
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
    time.sleep(2)
print('COMPARE_DONE', flush=True)
