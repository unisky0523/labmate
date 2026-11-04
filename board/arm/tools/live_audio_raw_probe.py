"""Board-only observation of the original continuous microphone stream.

Keep the original decoder's return value. Retain bounded copies of its input,
then inspect them after the recorder closes; do not change production files.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4


def command(arguments):
    try:
        result = subprocess.run(arguments, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=4,
                                universal_newlines=True, errors='replace')
        return {'code': result.returncode, 'text': result.stdout.strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'error': str(error)}


def read(path):
    try:
        return Path(path).read_text(errors='replace').strip()
    except OSError as error:
        return str(error)


def snapshot():
    active = {'hw': {name: read('/proc/asound/card0/' + name + '/sub0/hw_params')
                     for name in ('pcm0p', 'pcm1c')},
              'mixer': command(['amixer', '-c', '0', 'scontents'])}
    active['registers'] = {}
    if shutil.which('i2cget'):
        for register in ('0x00', '0x01', '0x02', '0x03', '0x08', '0x09', '0x0a', '0x0b', '0x0c',
                         '0x0d', '0x0f', '0x10', '0x11', '0x12', '0x2b'):
            active['registers'][register] = command(
                ['i2cget', '-f', '-y', '0', '0x10', register, 'b'])
    for name, value in active['hw'].items():
        print('ALSA', name, value.replace('\n', ' / '), flush=True)
    print('ES8388', json.dumps(active['registers'], sort_keys=True), flush=True)
    if not active['registers']:
        print('NOTE i2cget unavailable; registers not read', flush=True)
    for section in active['mixer'].get('text', '').split('Simple mixer control '):
        if section.startswith(("'ALC Capture Function'", "'Left Channel'",
                               "'Right Channel'")):
            print('MIXER', ' / '.join(line.strip() for line in section.splitlines()),
                  flush=True)
    return active


def describe(raw, label, decoder, np):
    octets = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 2, 4)
    print('RAW', label, 'frames=%d bytes=%d head64=%s' % (
        len(raw) // (882 * 8), len(raw), raw[:64].hex()), flush=True)
    for channel in (0, 1):
        values = octets[:, channel, :]
        print('BYTES', label, 'CH%d' % channel,
              'zero=' + ','.join('%.3f' % x for x in np.mean(values == 0, axis=0)),
              'ff=' + ','.join('%.3f' % x for x in np.mean(values == 255, axis=0)),
              'unique=' + ','.join(str(np.unique(values[:, i]).size) for i in range(4)),
              flush=True)
        for layout in ('CURRENT_LE', 'CHECK_SWAP_LOW3', 'CHECK_HIGH24'):
            if layout == 'CHECK_HIGH24':
                audio = (np.frombuffer(raw, dtype='<i4').reshape(-1, 2)[:, channel]
                         >> 8).astype(np.float32) / 8388608.0
            else:
                audio = decoder(raw, 2, channel=channel,
                                byte_order='little' if layout == 'CURRENT_LE' else 'msb-first')
            frames = audio.reshape(-1, 882)
            centered = frames - frames.mean(axis=1, keepdims=True)
            rms = np.sqrt(np.mean(centered * centered, axis=1))
            print('METRIC', label, 'CH%d' % channel, layout,
                  'rms_min=%.5f median=%.5f max=%.5f gate=%d/%d clip=%.4f' % (
                      rms.min(), np.median(rms), rms.max(),
                      np.count_nonzero(rms >= 0.01), len(rms),
                      np.mean(np.abs(audio) >= 0.995)), flush=True)


def main():
    sys.path.insert(0, '/home/root/labmate_ui_test/asr_runtime')
    import numpy as np
    import board_listen
    import board_mic

    if subprocess.call(['pidof', 'arecord', 'aplay'], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL) == 0:
        raise SystemExit('STOP: another arecord/aplay is still running')
    folder = Path('/home/root/labmate_audio_debug') / ('live_raw_' + uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    print('OUTPUT', folder, flush=True)
    decoder = board_mic._decode_s24le
    phase = None
    parts = []
    active = {}
    failure = None

    def observe(data, *args, **kwargs):
        label = phase
        native = decoder(data, *args, **kwargs)
        if label is not None and len(parts) < 900:
            parts.append((label, bytes(data)))
        return native

    args = SimpleNamespace(speech_threshold=0.01, end_silence=0.8,
                           max_utterance=12.0, playback_device='default',
                           audio_device='hw:0,1', mic_channel=0,
                           no_es8388_init=False)
    labels = ('QUIET', 'SPEAK', 'QUIET_AGAIN')
    board_mic._decode_s24le = observe
    try:
        with board_listen.ContinuousMicrophone(args) as mic:
            active = snapshot()
            print('READY: follow each PHASE for four seconds.', flush=True)
            for phase in labels:
                print('PHASE', phase, '4_SECONDS', flush=True)
                deadline = time.monotonic() + 4.0
                while time.monotonic() < deadline:
                    if mic.error is not None:
                        raise RuntimeError(str(mic.error))
                    time.sleep(0.02)
                phase = None
            if mic.error is not None:
                raise RuntimeError(str(mic.error))
    except Exception as error:
        failure = str(error)
    finally:
        phase = None
        board_mic._decode_s24le = decoder

    (folder / 'active.json').write_text(json.dumps(
        {'active': active, 'error': failure, 'raw_chunks': len(parts)}, indent=2),
        encoding='utf-8')
    if failure:
        print('CAPTURE_ERROR', failure, flush=True)
    if len(parts) == 900:
        print('NOTE raw copy limit reached; later frames were not retained', flush=True)
    for label in labels:
        raw = b''.join(data for name, data in parts if name == label)
        if raw:
            (folder / (label + '.raw')).write_bytes(raw)
            describe(raw, label, decoder, np)
        else:
            print('RAW', label, 'EMPTY', flush=True)
    print('PROBE_DONE', folder, flush=True)
    return 1 if failure else 0


if __name__ == '__main__':
    raise SystemExit(main())
