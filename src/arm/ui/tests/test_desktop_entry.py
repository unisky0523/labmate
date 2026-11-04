"""A factory desktop update must keep a verified original and be reversible."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

tool = next((p/'tools/install_desktop_entry.py' for p in Path(__file__).resolve().parents
             if (p/'tools/install_desktop_entry.py').is_file()), None)
if tool is None:
    raise unittest.SkipTest('Desktop installer is outside the standalone application')
spec = importlib.util.spec_from_file_location('desktop_installer', str(tool))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class DesktopInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.stage = self.root/'stage'
        self.stage.mkdir()
        self.backup = self.root/'backup'
        self.desktop = self.root/'QMainApp'
        self.original = b'original factory executable'
        self.desktop.write_bytes(self.original)
        data = bytearray(32)
        data[:5] = b'\x7fELF\x01'
        data[18:20] = (40).to_bytes(2, 'little')
        self.updated = bytes(data) + installer.MARKER
        (self.stage/'QMainApp').write_bytes(self.updated)
        for name in ('run_ui_desktop.sh', 'run_ui_instruments.sh', 'run_ui_voice.sh', 'run_ui_test.sh'):
            (self.stage/name).write_bytes(b'# LABMATE_DESKTOP_CHILD\n')

    def tearDown(self):
        self.temp.cleanup()

    def install(self):
        return installer.install(self.stage, self.desktop, self.backup,
                                 hashlib.sha256(self.original).hexdigest())

    def test_install_is_idempotent_and_rollback_restores_exact_original(self):
        self.install()
        self.install()
        self.assertEqual(self.desktop.read_bytes(), self.updated)
        self.assertEqual((self.backup/'QMainApp.original').read_bytes(), self.original)
        installer.rollback(self.desktop, self.backup)
        self.assertEqual(self.desktop.read_bytes(), self.original)

    def test_unknown_desktop_and_invalid_arm_binary_are_not_replaced(self):
        self.desktop.write_bytes(b'other firmware')
        with self.assertRaisesRegex(RuntimeError, 'Unexpected current'):
            self.install()
        self.assertEqual(self.desktop.read_bytes(), b'other firmware')
        self.desktop.write_bytes(self.original)
        (self.stage/'QMainApp').write_bytes(b'not an ARM executable')
        with self.assertRaisesRegex(RuntimeError, 'Expected ARM'):
            self.install()
        self.assertEqual(self.desktop.read_bytes(), self.original)

    def test_failed_replacement_keeps_current_program_and_verified_backup(self):
        with patch.object(installer.os, 'replace', side_effect=OSError('test write error')):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual(self.desktop.read_bytes(), self.original)
        self.assertEqual((self.backup/'QMainApp.original').read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main()
