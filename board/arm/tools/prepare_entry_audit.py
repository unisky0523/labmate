"""Simulate entry-audit orchestration and package a pasteable board command."""
import ast
import base64
import builtins
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zlib

import numpy as np

WORK = Path(__file__).resolve().parents[1]
SOURCE = WORK / 'tools/labmate_entry_audit.py'
OUT = WORK / 'work/entry_audit_20261022'
OUT.mkdir(parents=True, exist_ok=True)
source = SOURCE.read_text(encoding='utf-8')
ast.parse(source, feature_version=(3, 7))
sys.path.insert(0, 'D:/labmate_b')
spec = importlib.util.spec_from_file_location('entry_audit_sim', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
originals = (module.board_mic._decode_s24le, module.board_mic.capture_16k_mono,
             module.asr_cli.process, module.board_app.TextApplication.handle_text,
             builtins.input, sys.argv, sys.stdout)
results = []

for case in ('normal', 'capture_failure', 'wrong_version'):
    with tempfile.TemporaryDirectory(prefix='sim_', dir=str(OUT)) as temporary:
        root = Path(temporary).resolve()
        assert root.parent == OUT.resolve()
        project = root / 'project'
        refs = root / 'reference'
        count = {'capture': 0, 'playback': 0, 'asr': 0, 'partial': 0}
        wave = np.rint(np.sin(np.arange(44100 * 5) * .04) * 300000).astype(np.int32)
        pair = np.stack([wave, wave // 2], axis=1)
        raw = (pair.astype('<u4') & 0xffffff).tobytes()
        for trial in ('R2', 'R3'):
            (refs / trial).mkdir(parents=True)
            (refs / trial / 'native_stereo.raw').write_bytes(raw)
        for stem in ('asr_20230420_064625_a', 'asr_20230420_064658_b'):
            module.board_audio.write_wav_16k(project / 'data/audio/asr_tests' / (stem + '.wav'),
                                          np.sin(np.arange(80000) * .05).astype(np.float32) * .1)

        def capture(seconds, channel=0, **kwargs):
            count['capture'] += 1
            if case == 'capture_failure' and count['capture'] == 3:
                raise module.board_audio.AudioError('SIMULATED_CAPTURE_FAILURE')
            module.board_mic.configure_es8388_mic()
            data = bytes(len(raw)) if count['capture'] == 1 else raw
            audio = module.board_mic._decode_s24le(data, 2, channel, byte_order='little')
            return module.board_audio.resample_linear(audio, 44100, 16000), {
                'capture_errors': [], 'pcm_layout': 's24-le-low24-in-4', 'selected_channel': channel}

        def transcribe(audio, model, on_partial=None, grammar=None):
            count['asr'] += 1
            if on_partial:
                count['partial'] += 1
                on_partial('记录 电压')
            return {'text': '记录 电压 三 点 三 伏',
                    'words': [{'word': '记录', 'conf': .9}], 'segments': []}

        def preview(*args):
            count['playback'] += 1
            return .2

        def answer(prompt):
            return '0' if '0清楚' in prompt else ''

        def fake_command(args):
            return {'code': 0, 'text': 'SIMULATED: ' + ' '.join(args)}

        with contextlib.ExitStack() as stack:
            def use(obj, name, value):
                stack.enter_context(patch.object(obj, name, value))
            use(module, 'PROJECT', project)
            use(module, 'ROOT', root / 'outputs')
            use(module, 'REFERENCE', refs)
            use(module, 'command', fake_command)
            use(module, 'preview', preview)
            use(module.shutil, 'which', lambda name: None if name.startswith('espeak') else '/usr/bin/' + name)
            use(module.board_app, 'load_vosk_model', lambda p: (object(), None))
            use(module.board_mic, 'capture_16k_mono', capture)
            use(module.board_audio, 'run_command', lambda args: subprocess.CompletedProcess(args, 0, '', ''))
            use(module.asr_cli, 'transcribe', transcribe)
            use(module.asr_cli, 'AUDIO_DIR', root / 'app_audio')
            use(module.asr_cli, 'LOG_DIR', root / 'app_logs')
            real_status = module.board_app.board_ui.StatusBus
            use(module.board_app.board_ui, 'StatusBus', lambda: real_status(root / 'status.json'))
            use(module.board_app.core, 'set_reading_source', lambda *a: None)
            use(module.board_app.core, 'set_record_observer', lambda *a: None)
            use(builtins, 'input', answer)
            if case == 'wrong_version':
                use(module, 'EXPECTED_MIC_SHA', 'wrong')
            with contextlib.redirect_stdout(io.StringIO()) as output:
                module.main()
        reports = list((root / 'outputs').glob('entry_audit_*/summary.txt'))
        assert len(reports) == 1
        report = reports[0].read_text(encoding='utf-8')
        assert 'FINAL_RESULT_END' in output.getvalue(), output.getvalue()
        if case == 'wrong_version':
            assert 'MIC_VERSION_MISMATCH' in report and count['capture'] == 0
        else:
            assert 'ENTRY_AUDIT_DONE' in report, report
            assert 'ENTRY_AUDIT_INCOMPLETE' not in report, report
            assert count['capture'] == 5 and count['partial'] >= 3, count
            expected_raw = 4 if case == 'capture_failure' else 5
            assert len(list(reports[0].parent.glob('*/native_stereo.raw'))) == expected_raw
            assert count['playback'] == (2 if case == 'capture_failure' else 7), count
            if case == 'normal':
                assert count['asr'] == 27, count
                assert report.count('ENTRY_VS_LE max_abs_diff=0.0') == 5, report
            else:
                assert 'SIMULATED_CAPTURE_FAILURE' in report
        results.append({'case': case, 'result': 'PASS', 'counts': count})
    assert originals == (module.board_mic._decode_s24le, module.board_mic.capture_16k_mono,
                         module.asr_cli.process, module.board_app.TextApplication.handle_text,
                         builtins.input, sys.argv, sys.stdout)

digest = hashlib.sha256(source.encode()).hexdigest()
target = '/home/root/labmate_audio_debug/entry_audit_' + digest[:10] + '.py'
encoded = base64.b64encode(zlib.compress(source.encode(), 9)).decode()
lines = ["python3 - <<'PY'", 'import base64,zlib,hashlib', 'from pathlib import Path', 'parts=[']
lines += [repr(encoded[i:i + 1000]) + ',' for i in range(0, len(encoded), 1000)]
lines += [']', "source=zlib.decompress(base64.b64decode(''.join(parts)))",
          'assert hashlib.sha256(source).hexdigest()==' + repr(digest) + ", 'TOOL_CHECK_FAILED'",
          'p=Path(' + repr(target) + ')', 'p.parent.mkdir(parents=True,exist_ok=True)',
          "if p.exists(): assert p.read_bytes()==source, 'TOOL_VERSION_MISMATCH'",
          'else: p.write_bytes(source)', "print('ENTRY_AUDIT_READY')", 'PY',
          'cd /home/root/labmate_b_audio_test',
          'LD_LIBRARY_PATH="$PWD/lib:$PWD${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" PYTHONIOENCODING=utf-8 python3 ' + target]
installer = '\n'.join(lines) + '\n'
ast.parse('\n'.join(lines[1:lines.index('PY')]), feature_version=(3, 7))
assert max(map(len, lines)) < 1500
(OUT / '一次性调试命令.txt').write_text(installer, encoding='ascii')
(OUT / 'pc_simulation_results.txt').write_text(str(results), encoding='utf-8')
print(results)
print('COMMAND_FILE', OUT / '一次性调试命令.txt')
print('INSTALLER_LINES', len(lines))
