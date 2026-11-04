"""Validate and package the serial batch runner; simulate without board access."""
import ast
import base64
import builtins
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import zlib

import numpy as np

WORK = Path(__file__).resolve().parents[1]
SOURCE = WORK / 'tools/labmate_audio_batch.py'
OUT = WORK / 'work/audio_batch_20261022'
OUT.mkdir(parents=True, exist_ok=True)
source = SOURCE.read_text(encoding='utf-8')
ast.parse(source, feature_version=(3, 7))
sys.path.insert(0, 'D:/labmate_b')
spec = importlib.util.spec_from_file_location('labmate_audio_batch_check', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
real_decoder = module.board_mic._decode_s24le

with tempfile.TemporaryDirectory(prefix='simulation_', dir=str(OUT.resolve())) as directory:
    root = Path(directory).resolve()
    assert root.parent == OUT.resolve()
    counts = {'captures': 0, 'playbacks': 0, 'decodes': 0}

    def snapshot(path, active=False):
        module.write_json(path, {'registers': {'0x0d': {'text': '0x03'}},
                                 'capture_hw': 'format: S24_LE\nrate: 44100'})

    def capture(seconds, channel=0):
        counts['captures'] += 1
        silent = seconds == 3
        values = np.zeros((seconds * 44100, 2), dtype=np.int32)
        if not silent:
            tone = np.rint(np.sin(np.arange(seconds * 44100) * 0.03) * 80000).astype(np.int32)
            values[:, 0], values[:, 1] = tone, tone // 2
        unsigned = values.astype(np.uint32) & 0xffffff
        slots = np.zeros((len(values), 2, 4), dtype=np.uint8)
        slots[:, :, 0] = unsigned
        slots[:, :, 1] = unsigned >> 8
        slots[:, :, 2] = unsigned >> 16
        module.board_mic.configure_es8388_mic()
        data = slots.tobytes()
        audio = module.board_mic._decode_s24le(data, 2, channel, byte_order='little')
        return module.board_audio.resample_linear(audio, 44100, 16000), {'capture_errors': []}

    def play(*args):
        counts['playbacks'] += 1

    def transcribe(*args, **kwargs):
        counts['decodes'] += 1
        return {'text': '读取 数据', 'words': [{'word': '读取', 'conf': 0.9}], 'segments': []}

    def answer(prompt):
        return '0' if '听感编号' in prompt else ''

    # Source hashing is done against the real PC source paths for this simulation.
    simulated_source = source.replace("PROJECT = Path('/home/root/labmate_b_audio_test')", "PROJECT = Path('D:/labmate_b')")
    scope = {'__name__': 'labmate_audio_batch_sim'}
    exec(compile(simulated_source, str(SOURCE), 'exec'), scope)
    scope['ROOT'] = root
    scope['snapshot'] = snapshot
    scope['play'] = play
    scope['command'] = lambda args: {'code': 0, 'text': 'simulation'}
    scope['read'] = lambda path: 'simulation'
    scope['load_vosk_model'] = lambda path: (object(), None)
    with patch.object(module.board_mic, 'capture_16k_mono', side_effect=capture), \
         patch.object(module.board_mic, 'configure_es8388_mic', return_value={'available': True, 'errors': []}), \
         patch.object(module.asr_cli, 'transcribe', side_effect=transcribe), \
         patch.object(builtins, 'input', side_effect=answer), \
         contextlib.redirect_stdout(io.StringIO()) as output:
        scope['main']()
    assert counts == {'captures': 5, 'playbacks': 16, 'decodes': 18}, counts
    result = next(root.glob('batch_*/summary.txt'))
    assert 'BATCH_DONE' in result.read_text(encoding='utf-8'), output.getvalue()
    assert 'BATCH_INTERRUPTED' not in result.read_text(encoding='utf-8')
    assert len(list(result.parent.glob('*/native_stereo.raw'))) == 5
    assert len(json.loads((result.parent / 'asr_results.json').read_text(encoding='utf-8'))) == 18
    assert module.board_mic._decode_s24le is real_decoder

digest = hashlib.sha256(source.encode()).hexdigest()[:10]
target = '/home/root/labmate_audio_debug/labmate_audio_batch_' + digest + '.py'
encoded = base64.b64encode(zlib.compress(source.encode(), 9)).decode()
lines = ["python3 - <<'PY'", 'import base64,zlib', 'from pathlib import Path', 'parts = [']
lines += [repr(encoded[index:index + 1500]) + ',' for index in range(0, len(encoded), 1500)]
lines += [']', "source=zlib.decompress(base64.b64decode(''.join(parts)))", 'p=Path(' + repr(target) + ')',
          'p.parent.mkdir(parents=True,exist_ok=True)',
          "if p.exists(): assert p.read_bytes()==source, 'DIAGNOSTIC_VERSION_MISMATCH'",
          "else: p.write_bytes(source)", "print('BATCH_TOOL_READY')", 'PY',
          'cd /home/root/labmate_b_audio_test',
          'LD_LIBRARY_PATH="$PWD/lib:$PWD${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" PYTHONIOENCODING=utf-8 python3 ' + target]
command = '\n'.join(lines) + '\n'
assert max(len(line) for line in lines) < 2000
ast.parse('\n'.join(lines[1:lines.index('PY')]), feature_version=(3, 7))
(OUT / 'run_board_batch_command.txt').write_text(command, encoding='ascii')
print(json.dumps({'simulation': 'PASS', 'counts': counts, 'file': str(OUT / 'run_board_batch_command.txt'),
                  'installer_lines': len(lines), 'max_line_length': max(map(len, lines))}))
