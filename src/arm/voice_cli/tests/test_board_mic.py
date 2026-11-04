"""Capture regression tests; fake ALSA processes, never PC hardware evidence."""
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import board_audio
import board_mic
import asr_cli


class FakeProcess:
    def __init__(self, stderr=b"", returncode=0, timeout=False):
        self.stderr = io.BytesIO(stderr)
        self.returncode = None
        self.final_returncode = returncode
        self.timeout = timeout

    def poll(self):
        return self.returncode

    def communicate(self, timeout=None):
        if self.timeout:
            raise subprocess.TimeoutExpired("arecord", timeout)
        self.returncode = self.final_returncode
        return None, self.stderr.getvalue()

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class CaptureTests(unittest.TestCase):
    def capture(self, record_stderr=b"", playback_stderr=b"", returncode=0,
                timeout=False, short=False, init_errors=None):
        commands = []

        def popen(command, **kwargs):
            commands.append(command)
            self.assertEqual(kwargs["env"]["LC_ALL"], "C")
            self.assertIn("-q", command)
            if command[0] == "aplay":
                kwargs["stderr"].write(playback_stderr)
                return FakeProcess()
            frame_count = (8 if not short else 3) * 44100
            samples = np.tile(np.array([1000000, -1000000], dtype="<i4"), frame_count)
            Path(command[-1]).write_bytes(samples.tobytes())
            return FakeProcess(record_stderr, returncode, timeout)

        with patch.object(board_mic.subprocess, "Popen", side_effect=popen), \
                patch.object(board_mic.time, "sleep"), \
                patch.object(board_mic.time, "monotonic", side_effect=[0.0, 1.0]), \
                patch.object(board_mic, "configure_es8388_mic", return_value={
                    "available": True, "errors": init_errors or []}):
            return board_mic.capture_16k_mono(5)

    def test_normal_banner_is_only_a_notice_and_asr_is_reached(self):
        audio, metadata = self.capture(
            record_stderr=b"Recording raw data '/tmp/test.raw' : Signed 24 bit Little Endian, Rate 44100 Hz, Stereo\n")
        self.assertEqual(len(audio), 80000)
        self.assertEqual(metadata["capture_errors"], [])
        self.assertEqual(len(metadata["capture_warnings"]), 1)
        with patch.object(asr_cli, "audio_problem", return_value=None), \
                patch.object(asr_cli, "transcribe", return_value={
                    "text": "读取数据", "words": [], "segments": []}) as transcribe:
            result = asr_cli.analyze(audio, object(), metadata, 0.45)
        transcribe.assert_called_once()
        self.assertEqual(result["command"]["intent"], "read")

    def test_quiet_success(self):
        audio, metadata = self.capture()
        self.assertEqual(len(audio), 80000)
        self.assertEqual(metadata["capture_errors"], [])
        # End-to-end capture must retain the declared LE sample value, not
        # silently byte-swap it. The fake stream is left=+1000000 throughout.
        np.testing.assert_allclose(audio, 1000000 / 8388608.0)
        self.assertEqual(metadata["pcm_layout"], "s24-le-low24-in-4")

    def test_recovered_overrun_still_fails_with_exit_zero(self):
        with self.assertRaisesRegex(board_audio.AudioError, "overrun"):
            self.capture(record_stderr=b"overrun!!! (at least 50 ms long)\n")

    def test_playback_underrun_still_fails(self):
        with self.assertRaisesRegex(board_audio.AudioError, "underrun"):
            self.capture(playback_stderr=b"underrun!!! (at least 50 ms long)\n")

    def test_nonzero_exit(self):
        with self.assertRaisesRegex(board_audio.AudioError, "返回码 1"):
            self.capture(returncode=1)

    def test_timeout(self):
        with self.assertRaisesRegex(board_audio.AudioError, "超时"):
            self.capture(timeout=True)

    def test_short_capture(self):
        with self.assertRaisesRegex(board_audio.AudioError, "录音长度不足"):
            self.capture(short=True)

    def test_i2c_failure(self):
        with self.assertRaisesRegex(board_audio.AudioError, "麦克风配置失败"):
            self.capture(init_errors=["write failed"])

    def test_s24_sign_and_channel_selection(self):
        raw = np.array([0x007fffff, 0x00800000, 0x00ffffff, 0], dtype="<u4").tobytes()
        left = board_mic._decode_s24le(raw, 2, 0)
        right = board_mic._decode_s24le(raw, 2, 1)
        np.testing.assert_allclose(left, [8388607 / 8388608.0, -1 / 8388608.0])
        np.testing.assert_allclose(right, [-1, 0])

    def test_incomplete_frame_rejected(self):
        with self.assertRaises(board_audio.AudioError):
            board_mic._decode_s24le(b"\x00" * 6, 2)

    def test_board_msb_first_payload_sign_padding_and_channels(self):
        raw = bytes.fromhex("7fffff00 80000000 ffffff55 000001aa")
        np.testing.assert_allclose(
            board_mic._decode_s24le(raw, 2, 0, "msb-first"),
            [8388607 / 8388608.0, -1 / 8388608.0])
        np.testing.assert_allclose(
            board_mic._decode_s24le(raw, 2, 1, "msb-first"),
            [-1, 1 / 8388608.0])

    def test_historical_sample_alternate_decode_is_explicit_only(self):
        raw = bytes.fromhex("fedf5400 0060ae00 fe3fc300 00c07e00")
        np.testing.assert_allclose(
            board_mic._decode_s24le(raw, 2, 0, "msb-first"),
            [-0.008809566497802734, -0.013679146766662598])
        np.testing.assert_allclose(
            board_mic._decode_s24le(raw, 2, 1, "msb-first"),
            [0.002950429916381836, 0.0058743953704833984])

    def test_latest_board_raw_uses_le_sign_and_channel(self):
        # R2/R3 raw bytes provided with paired listening: LE speech, MSB noise.
        raw = bytes.fromhex("ff980000 c04bfd00 bf740000 4041fd00")
        np.testing.assert_allclose(board_mic._decode_s24le(raw, 2, 0),
                                   [39167 / 8388608.0, 29887 / 8388608.0])
        np.testing.assert_allclose(board_mic._decode_s24le(raw, 2, 1),
                                   [-177216 / 8388608.0, -179904 / 8388608.0])

    def test_codec_configuration_sets_fixed12_after_registers(self):
        with patch.object(board_mic.shutil, "which", return_value="/usr/sbin/i2cset"), \
                patch.object(board_audio, "run_command") as run:
            result = board_mic.configure_es8388_mic()
        self.assertEqual(result["errors"], [])
        self.assertEqual([call.args[0][0] for call in run.call_args_list],
                         ["i2cset"] * 3 + ["amixer"] * 3)
        self.assertEqual(run.call_args_list[3].args[0][-2:], ["ALC Capture Function", "Off"])

    def test_mixer_error_is_a_real_capture_failure(self):
        with patch.object(board_mic.shutil, "which", return_value="/usr/sbin/i2cset"), \
                patch.object(board_audio, "run_command", side_effect=[
                    None, None, None, board_audio.AudioError("amixer failed"), None, None]):
            result = board_mic.configure_es8388_mic()
        self.assertIn("amixer failed", result["errors"])


if __name__ == "__main__":
    unittest.main()
