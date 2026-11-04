"""Process-level checks; no board, microphone or third-party packages needed."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


SCRIPT = Path(__file__).resolve().parents[1] / "backend.py"


class BackendProcessTests(unittest.TestCase):
    def setUp(self):
        self.process = None
        self.messages = queue.Queue()

    def launch(self, *extra, script=SCRIPT):
        environment = dict(os.environ, PYTHONIOENCODING="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, "-u", str(script), "--demo-delay", "0.15"] + list(extra),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, encoding="utf-8", env=environment)

        def read():
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except ValueError:
                    self.messages.put({"invalid_stdout": line})

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        ready = self.take("ready")
        self.assertEqual((ready["state"], ready["mode"]), ("idle", "demo"))

    def take(self, event):
        message = self.messages.get(timeout=4)
        self.assertEqual(message.get("event"), event, message)
        self.assertEqual(message["protocol"], 1)
        return message

    def send(self, action, request_id, target=None):
        request = dict(protocol=1, action=action, id=request_id)
        if target is not None:
            request["target"] = target
        self.raw(json.dumps(request, ensure_ascii=False) + "\n")

    def raw(self, text):
        self.process.stdin.write(text)
        self.process.stdin.flush()

    def start(self, operation="round-1"):
        self.send("start", operation)
        message = self.take("state")
        self.assertEqual((message["state"], message["operation_id"]), ("running", operation))

    def result(self, operation="round-1"):
        result = self.take("result")
        self.assertEqual((result["state"], result["operation_id"]), ("pending", operation))
        self.assertTrue(result["simulated"])
        self.assertEqual(result["command"]["measurements"][0]["value"], "3.3")
        return result

    def tearDown(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            if not self.process.stdin.closed:
                try:
                    self.send("quit", "teardown-quit")
                except (OSError, ValueError):
                    pass
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.reader.join(timeout=1)
        errors = self.process.stderr.read()
        code = self.process.returncode
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()
        self.assertEqual(code, 0, errors)
        self.assertEqual(errors, "")

    def test_start_result_confirm_and_duplicate_confirmation(self):
        self.launch()
        self.start("第1轮")
        result = self.result("第1轮")
        self.assertEqual(result["text"], "记录电压三点三伏")
        self.send("confirm", "confirm-1", "第1轮")
        reply = self.take("confirmed")
        self.assertEqual((reply["state"], reply["effect"]), ("idle", "demo_only"))
        self.send("confirm", "confirm-1", "第1轮")
        self.assertEqual(self.take("error")["code"], "duplicate_request")
        self.send("confirm", "confirm-2", "第1轮")
        self.assertEqual(self.take("error")["code"], "wrong_target")

    def test_history_loads_existing_data_in_the_actual_backend_process(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = SCRIPT.parent / 'tests/fixtures/legacy_mock_record.json'
            shutil.copy2(str(fixture), str(Path(directory) / 'record_fixture.json'))
            with patch.dict(os.environ, LABMATE_RECORD_DIR=directory, LABMATE_HISTORY_DIRS=''):
                self.launch()
            self.raw(json.dumps(dict(protocol=1, id='history', action='history', page=0, size=4)) + '\n')
            message = self.take('history')
            self.assertEqual((message['state'], message['total']), ('idle', 1))
            self.assertEqual(message['rows'][0]['source'], '模拟数据')

    def test_embedded_resources_include_every_module_needed_for_history(self):
        with tempfile.TemporaryDirectory() as directory:
            extracted = Path(directory) / 'embedded'
            for node in ET.parse(str(SCRIPT.parent / 'resources.qrc')).findall('.//file'):
                destination = extracted / node.text
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((SCRIPT.parent / node.text).read_bytes())
            records = Path(directory) / 'records'
            records.mkdir()
            shutil.copy2(str(SCRIPT.parent / 'tests/fixtures/legacy_mock_record.json'),
                         str(records / 'record_fixture.json'))
            with patch.dict(os.environ, LABMATE_RECORD_DIR=str(records), LABMATE_HISTORY_DIRS='',
                            LABMATE_ASR_ROOT='', LABMATE_RECORD_RUNTIME=''):
                self.launch(script=extracted / 'backend.py')
            self.send('history', 'from-embedded')
            self.assertEqual(self.take('history')['total'], 1)

    def test_backend_boots_and_reads_history_without_audio_standard_library(self):
        # Reproduce the reduced board image: audio modules must not be needed
        # merely to import the backend and inspect already-saved records.
        with tempfile.TemporaryDirectory() as directory:
            records = Path(directory) / 'records'
            records.mkdir()
            shutil.copy2(str(SCRIPT.parent / 'tests/fixtures/legacy_mock_record.json'),
                         str(records / 'record_fixture.json'))
            bootstrap = Path(directory) / 'reduced_python.py'
            bootstrap.write_text('''import runpy
import sys
from pathlib import Path
script = Path(SCRIPT_PATH)
sys.path.insert(0, str(script.parent))
class NoAudioModules:
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('wave', 'chunk', 'audioop'):
            raise ModuleNotFoundError('Not included in board Python', name=fullname)
sys.meta_path.insert(0, NoAudioModules())
runpy.run_path(str(script), run_name='__main__')
'''.replace('SCRIPT_PATH', repr(str(SCRIPT))), encoding='utf-8')
            with patch.dict(os.environ, LABMATE_RECORD_DIR=str(records), LABMATE_HISTORY_DIRS='',
                            LABMATE_ASR_ROOT='', LABMATE_RECORD_RUNTIME=''):
                self.launch(script=bootstrap)
            self.send('history', 'missing-wave-history')
            page = self.take('history')
            self.assertEqual(page['total'], 1)
            self.assertEqual(page['rows'][0]['source'], '模拟数据')

    def test_cancel_and_restart_never_delivers_old_result(self):
        self.launch("--demo-delay", "0.4")
        self.start("old")
        self.send("cancel", "cancel-old", "old")
        self.assertEqual(self.take("cancelled")["operation_id"], "old")
        self.start("new")
        self.result("new")
        self.send("confirm", "stale-confirm", "old")
        error = self.take("error")
        self.assertEqual((error["code"], error["state"]), ("wrong_target", "pending"))
        self.send("confirm", "confirm-new", "new")
        self.assertEqual(self.take("confirmed")["operation_id"], "new")

    def test_busy_start_and_early_confirmation_keep_original_operation(self):
        self.launch("--demo-delay", "0.5")
        self.start()
        self.send("start", "another-round")
        self.assertEqual(self.take("error")["code"], "busy")
        self.send("confirm", "early-confirm", "round-1")
        self.assertEqual(self.take("error")["code"], "not_pending")
        self.result()

    def test_cancel_pending_result_cannot_be_confirmed(self):
        self.launch()
        self.start()
        self.result()
        self.send("cancel", "cancel-pending", "round-1")
        self.assertEqual(self.take("cancelled")["state"], "idle")
        self.send("confirm", "after-cancel", "round-1")
        self.assertEqual(self.take("error")["code"], "wrong_target")

    def test_invalid_frames_do_not_crash_or_start_an_operation(self):
        self.launch()
        self.raw('bad json\n[]\n{"id":4,"protocol":1}\n')
        self.assertEqual(self.take("error")["code"], "invalid_json")
        self.assertEqual(self.take("error")["code"], "invalid_request")
        self.assertEqual(self.take("error")["code"], "invalid_id")
        self.raw('{"protocol":true,"id":"bad-version","action":"start"}\n')
        self.assertEqual(self.take("error")["code"], "protocol_mismatch")
        self.raw('{"protocol":1,"id":"nan","value":NaN}\n')
        self.assertEqual(self.take("error")["code"], "invalid_json")
        self.send("unknown", "unknown-action")
        self.assertEqual(self.take("error")["code"], "unknown_action")
        self.start()
        self.result()

    def test_split_and_oversized_frames_recover_at_newline(self):
        self.launch()
        self.raw("x" * 70000 + "\n")
        self.assertEqual(self.take("error")["code"], "invalid_json")
        self.raw('{"protocol":1,"id":"split",')
        self.raw('"action":"start"}\n')
        self.assertEqual(self.take("state")["operation_id"], "split")
        self.result("split")

    def test_worker_failure_returns_idle_and_allows_another_request(self):
        self.launch("--demo-error")
        self.start()
        error = self.take("error")
        self.assertEqual((error["code"], error["state"]), ("recognition_failed", "idle"))
        self.start("retry")
        self.assertEqual(self.take("error")["operation_id"], "retry")

    def test_quit_during_work_exits_promptly(self):
        self.launch("--demo-delay", "10")
        self.start()
        self.send("quit", "quit-now")
        self.assertEqual(self.take("stopped")["state"], "stopped")
        self.assertEqual(self.process.wait(timeout=2), 0)

    def test_eof_during_work_exits_promptly(self):
        self.launch("--demo-delay", "10")
        self.start()
        self.process.stdin.close()
        self.assertEqual(self.process.wait(timeout=2), 0)


if __name__ == "__main__":
    unittest.main()
