"""Check command-only decoding without weakening dispatch checks."""
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

import asr_cli
import board_app


def transcript(text, confidence=0.9):
    return {"text": text, "words": [{"conf": confidence}], "segments": []}


class CommandGrammarTests(unittest.TestCase):
    def setUp(self):
        self.audio = (np.sin(np.arange(16000) * 0.1) * 0.1).astype(np.float32)

    def analyze(self, metadata=None, **kwargs):
        return asr_cli.analyze(self.audio, object(), metadata or {}, 0.45,
                               grammar=asr_cli.GRAMMAR_JSON, command_grammar=True,
                               **kwargs)

    def test_one_command_pass_preserves_number(self):
        with patch.object(asr_cli, "transcribe", return_value=transcript("记录 电压 三 点 三 伏")) as decode:
            result = self.analyze()
        self.assertEqual(result["command"]["intent"], "record_manual")
        self.assertEqual(result["command"]["measurements"][0]["value"], "3.3")
        self.assertEqual(result["recognizer_mode"], "command_grammar")
        self.assertEqual(decode.call_count, 1)
        self.assertEqual(decode.call_args.kwargs["grammar"], asr_cli.GRAMMAR_JSON)

    def test_bad_phrase_has_no_general_fallback(self):
        with patch.object(asr_cli, "transcribe", return_value=transcript("三 电压 取消 数据")) as decode:
            result = self.analyze()
        self.assertIsNone(result["command"])
        self.assertEqual(decode.call_count, 1)

    def test_low_score_still_rejected(self):
        with patch.object(asr_cli, "transcribe", return_value=transcript("读取 数据", 0.1)):
            self.assertIsNone(self.analyze()["command"])

    def test_capture_failures_block_decode(self):
        with patch.object(asr_cli, "transcribe") as decode:
            for metadata in ({"truncated": True}, {"capture_errors": ["overrun"]}):
                self.assertIsNone(self.analyze(metadata)["command"])
            self.audio[:] = 0
            self.assertIsNone(self.analyze()["command"])
            self.audio[:] = 1
            self.assertIsNone(self.analyze()["command"])
        decode.assert_not_called()

    def test_default_still_uses_general_decode(self):
        with patch.object(asr_cli, "transcribe", return_value=transcript("读取 数据")) as decode:
            result = asr_cli.analyze(self.audio, object(), {}, 0.45,
                                      grammar=asr_cli.GRAMMAR_JSON)
        self.assertEqual(result["recognizer_mode"], "baseline")
        self.assertNotIn("grammar", decode.call_args.kwargs)

    def test_board_option_defaults_off(self):
        self.assertFalse(board_app.build_asr_args(Path("model"), 0.45).command_grammar)
        self.assertTrue(board_app.build_asr_args(Path("model"), 0.45,
                                                command_grammar=True).command_grammar)

    def test_fast_readback_confirmation_and_cancel(self):
        for reply, expected_calls in (("确认", 1), ("取消", 0)):
            with self.subTest(reply=reply):
                args = board_app.build_asr_args(Path("model"), 0.45,
                                                confirm_readback=True, command_grammar=True)
                app = MagicMock()
                app.handle_text.return_value = False
                with patch.object(asr_cli, "transcribe", side_effect=[
                        transcript("记录 电压 三 点 三 伏"), transcript(reply)]) as decode, \
                     patch.object(asr_cli, "capture", return_value=(self.audio, {})), \
                     patch.object(asr_cli, "save_audio", return_value=Path("confirm.wav")), \
                     patch.object(asr_cli, "LOG_DIR", MagicMock()), \
                     patch.object(asr_cli.core, "write_json_atomically"), \
                     patch("readback.speak_text", return_value=True):
                    asr_cli.process(self.audio, Path("original.wav"), {}, object(), args,
                                    application=app, ask_label=False)
                self.assertEqual(decode.call_count, 2)
                self.assertEqual(decode.call_args.kwargs["grammar"],
                                 asr_cli.CONFIRM_GRAMMAR_JSON)
                self.assertEqual(app.handle_text.call_count, expected_calls)
                if expected_calls:
                    self.assertTrue(app.handle_text.call_args.kwargs["input_context"]["pre_confirmed"])


if __name__ == "__main__":
    unittest.main()
