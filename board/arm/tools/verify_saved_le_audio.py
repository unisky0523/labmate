"""Read-only LE ASR checks on the user's already-saved R2/R3 stereo RAWs."""
import json
from pathlib import Path
import sys
import time

import numpy as np

PROJECT = Path('/home/root/labmate_b_audio_test')
sys.path.insert(0, str(PROJECT))
import asr_cli
import board_audio
import board_mic
from board_app import load_vosk_model, DEFAULT_MODEL

BATCH = Path('/home/root/labmate_audio_debug/batch_20230420_062226_bdd17b')


def main():
    output = []
    try:
        print('已恢复 LE。现在检查已有录音，无需说话；约需 2～5 分钟。', flush=True)
        environment = BATCH / 'environment.json'
        if environment.exists():
            env = json.loads(environment.read_text(encoding='utf-8'))
            for key in ('uname', 'cpu_frequency', 'cpu_governor', 'asound_conf'):
                output.append('ENV %s %s' % (key, str(env.get(key, '')).replace('\n', ' / ')))
        model, error = load_vosk_model(DEFAULT_MODEL)
        if model is None:
            raise RuntimeError(error)
        for trial, expected in (('R2', '记录电压三点三伏'), ('R3', '记录电压三点六伏')):
            folder = BATCH / trial
            data = (folder / 'native_stereo.raw').read_bytes()
            active_path = folder / 'active.json'
            if active_path.exists():
                active = json.loads(active_path.read_text(encoding='utf-8'))
                for key in ('capture_hw', 'playback_hw', 'registers'):
                    output.append('%s %s %s' % (trial, key, str(active.get(key, '')).replace('\n', ' / ')))
                selected = False
                for line in active.get('mixer', {}).get('text', '').splitlines():
                    if line.startswith('Simple mixer control'):
                        selected = any("'%s'" % control in line for control in (
                            'ALC Capture Function', 'Left Channel', 'Right Channel', 'Capture Digital Volume'))
                    if selected:
                        output.append('%s MIXER %s' % (trial, line.strip()))
            for channel, label in ((0, 'L'), (1, 'R')):
                native = board_mic._decode_s24le(data, 2, channel, byte_order='little')
                audio = board_audio.resample_linear(native, 44100, 16000)
                wav = folder / ('verified_LE_' + label + '_16k.wav')
                board_audio.write_wav_16k(wav, audio)
                quality = asr_cli.audio_problem(audio)
                output.append('%s %s QUALITY %s RMS %.5f' % (
                    trial, label, quality, float(np.sqrt(np.mean(audio ** 2)))))
                for mode, grammar in (('NORMAL', None), ('WORDS', asr_cli.GRAMMAR_JSON)):
                    print('CHECK', trial, label, mode, flush=True)
                    started = time.perf_counter()
                    result = asr_cli.transcribe(audio, model, grammar=grammar)
                    seconds = time.perf_counter() - started
                    command, confidence, reason = asr_cli._evaluate_transcript(result['text'], result['words'], 0.45)
                    correct = asr_cli.semantic_key(command) == asr_cli.semantic_key(asr_cli.parse_command(expected))
                    output.append('%s %s %s %.2fs text=%s correct=%s confidence=%s reason=%s' % (
                        trial, label, mode, seconds, result['text'], correct, confidence, reason))
                    print(output[-1], flush=True)
                    (folder / ('verified_LE_' + label + '_' + mode + '.json')).write_text(
                        json.dumps({'result': result, 'expected': expected, 'correct': correct,
                                    'seconds': seconds, 'quality': quality}, ensure_ascii=False, indent=2), encoding='utf-8')
        output.append('LE_VERIFY_DONE')
    finally:
        report = '\n'.join(output) + '\n'
        (BATCH / 'verified_LE_summary.txt').write_text(report, encoding='utf-8')
        print('\n===== LE_RESULT_BEGIN =====\n' + report + '===== LE_RESULT_END =====', flush=True)


if __name__ == '__main__':
    main()
