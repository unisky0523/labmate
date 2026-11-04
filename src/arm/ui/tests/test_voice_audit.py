"""The version check reads deployment evidence without changing board files."""
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest


tool = next((p/'tools/audit_ui_voice.py' for p in Path(__file__).resolve().parents
             if (p/'tools/audit_ui_voice.py').is_file()), None)
if tool is None:
    raise unittest.SkipTest('Board audit tool is outside this standalone Qt folder')
spec = importlib.util.spec_from_file_location('voice_audit', str(tool))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VoiceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.voice = b'raise RuntimeError("ASR must not be imported")\n'
        self.expected = dict(voice={'asr_adapter.py': hashlib.sha256(self.voice).hexdigest()},
                             records={'backend.py': hashlib.sha256(b'new store backend').hexdigest()},
                             gui=hashlib.sha256(b'LABMATE_UI_RECORDS_V2').hexdigest())
        (self.root/'asr_adapter.py').write_bytes(self.voice)
        (self.root/'backend.py').write_bytes(b'new store backend')
        (self.root/'labassistant').write_bytes(b'LABMATE_UI_RECORDS_V2')

    def tearDown(self):
        self.temp.cleanup()

    def run_audit(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.audit(self.root, self.expected)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        return output.getvalue()

    def test_matching_install_is_only_read_and_asr_is_not_imported(self):
        output = self.run_audit()
        self.assertIn('VOICE_MATCH 1/1', output)
        self.assertIn('RECORDS_MATCH 1/1', output)
        self.assertIn('GUI RECORDS_V2 same_as_windows=True', output)

    def test_reports_wrong_and_missing_files(self):
        (self.root/'asr_adapter.py').write_bytes(b'other voice version')
        (self.root/'backend.py').unlink()
        output = self.run_audit()
        self.assertIn('DIFFERENT asr_adapter.py', output)
        self.assertIn('DIFFERENT backend.py board=MISSING', output)
        self.assertIn('VOICE_MATCH 0/1', output)

    def test_exposes_backup_content_instead_of_treating_v1_marker_as_proof(self):
        (self.root/'labassistant.bak.100_1').write_bytes(b'LABMATE_UI_ASR_V1')
        (self.root/'asr_adapter.py.bak.100_1').write_bytes(b'wrong backup')
        output = self.run_audit()
        self.assertIn('V1_BACKUP 100_1 files=1/1 original_matches=0/1', output)
