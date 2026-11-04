"""Small UART receiver; sent by the Windows helper, runs on board Python 3.7."""
import base64
import hashlib
import io
import os
import pathlib
import shutil
import sys
import termios
import time
import zipfile

count, expected = int(sys.argv[1]), sys.argv[2]
previous = termios.tcgetattr(0)
try:
    settings = termios.tcgetattr(0)
    settings[3] &= ~(termios.ECHO | termios.ECHONL)
    termios.tcsetattr(0, termios.TCSANOW, settings)
    print('__LM_RX_READY__', flush=True)
    parts = []
    for index in range(count):
        line = sys.stdin.readline()
        if not line or line.strip() == '__LM_ABORT__':
            raise RuntimeError('transfer aborted')
        parts.append(line.strip())
        print('__LM_ACK_%d__' % index, flush=True)
    data = base64.b64decode(''.join(parts), validate=True)
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError('archive SHA256 mismatch')
    allowed = {'labassistant', 'run_ui_test.sh', 'run_ui_voice.sh', 'run_ui_instruments.sh',
               'backend.py', 'asr_adapter.py', 'record_store.py', 'instrument_adapter.py',
               'command_executor.py', 'audio_frontend.py', 'instruments.json', 'restore_ui_voice_baseline.py',
               'QMainApp', 'run_ui_desktop.sh', 'install_desktop_entry.py',
               'generator_control.py', 'generator_runner.py', 'asr_runtime/generator_commands.py',
               'fft_control.py', 'fft_protocol.py', 'scope_waveform.py', 'sweep_response.py'}
    runtime = ('asr_cli asr_grammar asr_backend vosk_lite board_audio board_mic '
               'board_listen text_cli main wave chunk').split()
    allowed.update('asr_runtime/' + name + '.py' for name in runtime)
    allowed.update({'asr_runtime/PYTHON_STDLIB_LICENSE.txt',
                    'asr_runtime/PYTHON_STDLIB_SOURCE.md', 'asr_runtime/baseline.json'})
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        for name in names:
            parts = pathlib.PurePosixPath(name).parts
            if (name.startswith('dg4102_driver/c_instrument/') and '..' not in parts
                    and '\\' not in name and not name.endswith('/')):
                allowed.add(name)
        if len(names) != len(set(names)) or not set(names) <= allowed:
            raise RuntimeError('unexpected archive paths')
        files = {name: archive.read(name) for name in archive.namelist()}
    target = pathlib.Path('/home/root/labmate_ui_test')
    elf = files.get('labassistant') or (target / 'labassistant').read_bytes()
    if elf[:5] != b'\x7fELF\x01' or int.from_bytes(elf[18:20], 'little') != 40:
        raise RuntimeError('expected ARM ELF32 executable')
    if 'labassistant' not in files and (b'LABMATE_UI_RECORDS_V2' not in elf or not {'backend.py', 'record_store.py', 'run_ui_voice.sh'} <= set(names)):
        raise RuntimeError('records-only update requires the already installed records V2 GUI')
    restore = None
    if 'restore_ui_voice_baseline.py' in files:
        restore = {}
        exec(compile(files['restore_ui_voice_baseline.py'], 'restore_ui_voice_baseline.py', 'exec'), restore)
        plan = restore['plan_restore'](target)
    if 'backend.py' in files:
        required = ['asr_adapter.py'] + ['asr_runtime/' + name + '.py' for name in runtime]
        restored = {p.resolve().relative_to(target.resolve()).as_posix() for _, p, _ in plan['files']} if restore is not None else set()
        if any(name not in files and name not in restored and not (target / name).is_file() for name in required):
            raise RuntimeError('existing ASR runtime missing; use explicit -InstallAsrRuntime for initial deployment')
    if 'asr_adapter.py' in files and b'from audio_frontend import' in files['asr_adapter.py']:
        if 'audio_frontend.py' not in files and not (target/'audio_frontend.py').is_file():
            raise RuntimeError('audio frontend module missing')
    target.mkdir(parents=True, exist_ok=True)
    stamp = '%d_%d' % (int(time.time()), os.getpid())
    for name, content in files.items():
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.copy2(str(destination), str(destination) + '.bak.' + stamp)
        temporary = destination.parent / ('.' + destination.name + '.incoming.' + stamp)
        with temporary.open('xb') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o755)
        os.replace(str(temporary), str(destination))
    if restore is not None:
        restore['apply_restore'](plan, stamp)
    print('__LM_UPLOAD_OK__ ' + hashlib.sha256(elf).hexdigest(), flush=True)
except Exception as error:
    print('__LM_UPLOAD_ERROR__ ' + str(error), flush=True)
finally:
    termios.tcsetattr(0, termios.TCSANOW, previous)
