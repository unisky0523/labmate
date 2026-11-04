"""Board backup restoration and records-only receiver, entirely in temp dirs."""
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

TOOLS = next((parent/'tools' for parent in Path(__file__).resolve().parents
              if (parent/'tools/restore_ui_voice_baseline.py').is_file()), None)
if TOOLS is None:
    raise unittest.SkipTest('Deployment tools are outside this standalone Qt source folder')
spec = importlib.util.spec_from_file_location('voice_restore', str(TOOLS/'restore_ui_voice_baseline.py'))
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


def elf(marker):
    data = bytearray(32)
    data[:5] = b'\x7fELF\x01'
    data[18:20] = (40).to_bytes(2, 'little')
    return bytes(data) + marker


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'labassistant').write_bytes(elf(b'LABMATE_UI_RECORDS_V2'))
        for name in restore.VOICE_FILES:
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('current:' + name).encode())
        self.record = self.root/'data/records/record_existing.json'
        self.record.parent.mkdir(parents=True)
        self.record.write_bytes(b'keep existing records')

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self, stamp='100_1', marker=b'LABMATE_UI_ASR_V1'):
        (self.root/('labassistant.bak.'+stamp)).write_bytes(elf(marker))
        for name in restore.VOICE_FILES:
            (self.root/(name+'.bak.'+stamp)).write_bytes(('old:' + stamp + ':' + name).encode())

    def receive(self, with_restore=False):
        files = {'backend.py': b'new records backend', 'record_store.py': b'new store',
                 'run_ui_voice.sh': b'new records launcher'}
        if with_restore:
            files['restore_ui_voice_baseline.py'] = (TOOLS/'restore_ui_voice_baseline.py').read_bytes()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        data = stream.getvalue()
        incoming = io.StringIO(base64.b64encode(data).decode()+'\n')
        output = io.StringIO()
        terminal = types.ModuleType('termios')
        terminal.ECHO, terminal.ECHONL, terminal.TCSANOW = 1, 2, 0
        terminal.tcgetattr = lambda fd: [0, 0, 0, 3, 0, 0, []]
        terminal.tcsetattr = lambda *args: None
        source = (TOOLS/'ui_serial_receiver.py').read_text(encoding='utf-8')
        needle = "pathlib.Path('/home/root/labmate_ui_test')"
        self.assertEqual(source.count(needle), 1)
        source = source.replace(needle, 'pathlib.Path(sys.argv[3])')
        with patch.dict(sys.modules, termios=terminal), patch.object(sys, 'stdin', incoming), \
             patch.object(sys, 'stdout', output), patch.object(sys, 'argv', [
                 'receiver', '1', hashlib.sha256(data).hexdigest(), str(self.root)]):
            exec(compile(source, 'receiver-test', 'exec'), {})
        return output.getvalue()

    def test_restores_latest_complete_asr_v1_cohort_and_keeps_backups(self):
        self.snapshot('100_1')
        self.snapshot('200_2')
        self.snapshot('300_3', b'LABMATE_UI_RECORDS_V2')
        plan = restore.plan_restore(self.root)
        self.assertEqual(plan['stamp'], '200_2')
        restore.apply_restore(plan, '400_4')
        for name in restore.VOICE_FILES:
            self.assertEqual((self.root/name).read_bytes(), ('old:200_2:'+name).encode())
            self.assertEqual((self.root/(name+'.before_voice_restore.400_4')).read_bytes(), ('current:'+name).encode())
        self.assertEqual(self.record.read_bytes(), b'keep existing records')
        self.assertIn(b'LABMATE_UI_RECORDS_V2', (self.root/'labassistant').read_bytes())

    def test_incomplete_backup_is_rejected_before_any_update(self):
        self.snapshot()
        (self.root/(restore.VOICE_FILES[-1]+'.bak.100_1')).unlink()
        output = self.receive(with_restore=True)
        self.assertIn('__LM_UPLOAD_ERROR__', output)
        self.assertFalse((self.root/'backend.py').exists())
        self.assertEqual((self.root/restore.VOICE_FILES[0]).read_bytes(), ('current:'+restore.VOICE_FILES[0]).encode())

    def test_failed_restore_rolls_voice_files_back(self):
        self.snapshot()
        original = restore.os.replace
        calls = []
        def fail_second(*args):
            calls.append(args)
            if len(calls) == 2:
                raise OSError('injected write failure')
            return original(*args)
        with patch.object(restore.os, 'replace', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'injected'):
                restore.apply_restore(restore.plan_restore(self.root), '400_4')
        for name in restore.VOICE_FILES:
            self.assertEqual((self.root/name).read_bytes(), ('current:'+name).encode())

    def test_records_only_receiver_preserves_voice_gui_and_existing_data(self):
        voice = {name: (self.root/name).read_bytes() for name in restore.VOICE_FILES}
        self.assertIn('__LM_UPLOAD_OK__', self.receive())
        self.assertEqual((self.root/'backend.py').read_bytes(), b'new records backend')
        for name in voice:
            self.assertEqual((self.root/name).read_bytes(), voice[name])
        self.assertEqual(self.record.read_bytes(), b'keep existing records')
        self.assertEqual((self.root/'labassistant').read_bytes(), elf(b'LABMATE_UI_RECORDS_V2'))

    def test_receiver_restores_board_voice_backup_without_replacing_gui(self):
        self.snapshot()
        self.assertIn('__LM_UPLOAD_OK__', self.receive(with_restore=True))
        for name in restore.VOICE_FILES:
            self.assertEqual((self.root/name).read_bytes(), ('old:100_1:'+name).encode())
        self.assertEqual((self.root/'labassistant').read_bytes(), elf(b'LABMATE_UI_RECORDS_V2'))

    def test_records_only_receiver_rejects_old_gui_before_replacing_files(self):
        (self.root/'labassistant').write_bytes(elf(b'LABMATE_UI_ASR_V1'))
        self.assertIn('__LM_UPLOAD_ERROR__', self.receive())
        self.assertFalse((self.root/'backend.py').exists())

    def test_adapter_and_runtime_match_verified_board_reference(self):
        root = Path(__file__).resolve().parents[1]
        hashes = json.loads((root/'tests/fixtures/voice_hashes_20261103_fft.json').read_text())
        for name, expected in hashes.items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(), expected, name)

    def test_fft_voice_changes_are_limited_to_command_and_vocabulary(self):
        root = Path(__file__).resolve().parents[1]
        previous = json.loads((root/'tests/fixtures/voice_hashes_20261103_dg4102.json').read_text())
        current = json.loads((root/'tests/fixtures/voice_hashes_20261103_fft.json').read_text())
        self.assertEqual(set(previous), set(current))
        self.assertEqual({name for name in previous if previous[name] != current[name]},
                         {'asr_runtime/asr_cli.py', 'asr_runtime/asr_grammar.py',
                          'asr_runtime/text_cli.py'})

    def test_voice_confirmation_only_changes_adapter_and_vocabulary_since_little_fix(self):
        root = Path(__file__).resolve().parents[1]
        baseline = json.loads((root/'tests/fixtures/voice_hashes_20261102_little.json').read_text())
        current = json.loads((root/'tests/fixtures/voice_hashes_20261102_confirm.json').read_text())
        self.assertEqual(set(baseline), set(current))
        self.assertEqual({name for name in baseline if baseline[name] != current[name]},
                         {'asr_adapter.py', 'asr_runtime/asr_grammar.py'})

    def test_only_explicit_pcm_argument_differs_from_original_voice(self):
        root = Path(__file__).resolve().parents[1]
        original = json.loads((root/'tests/fixtures/original_voice_hashes.json').read_text())
        verified = json.loads((root/'tests/fixtures/voice_hashes_20261102_little.json').read_text())
        self.assertEqual(set(original), set(verified))
        self.assertEqual([name for name in original if original[name] != verified[name]],
                         ['asr_runtime/board_listen.py'])
        restored = (root/'asr_runtime/board_listen.py').read_bytes()
        for old, new in (
            (b'board_mic._decode_s24le(raw, 2, channel=self.args.mic_channel)',
             b'board_mic._decode_s24le(raw, 2, channel=self.args.mic_channel, byte_order="little")'),
        ):
            self.assertEqual(restored.count(new), 1)
            restored = restored.replace(new, old)
        self.assertEqual(hashlib.sha256(restored).hexdigest(), original['asr_runtime/board_listen.py'])
