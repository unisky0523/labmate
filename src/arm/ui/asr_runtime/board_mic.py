"""Navigator ZYNQ microphone path verified by teammate A.

Sequence reproduced from A's working shell commands:
1. Keep an aplay silence stream running on the default playback device.
2. Start arecord on hw:0,1 as raw S24_LE 44.1 kHz stereo.
3. Write the ES8388 microphone registers through i2cset.
4. Decode signed little-endian low 24 bits in each 4-byte slot, then convert
   to 16 kHz mono. Paired raw-file playback on 2026-10-22 confirmed LE restored
   speech on both channels; the prior forced MSB-first path produced noise.
"""

from datetime import datetime
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import numpy as np

import board_audio


DEFAULT_CAPTURE_DEVICE = "hw:0,1"
DEFAULT_KEEPALIVE_DEVICE = "default"
DEFAULT_CAPTURE_RATE = 44100
DEFAULT_CAPTURE_FORMAT = "S24_LE"
DEFAULT_CAPTURE_CHANNELS = 2
TARGET_RATE = 16000
CAPTURE_WARMUP_SECONDS = 3

ES8388_I2C_BUS = "0"
ES8388_I2C_ADDRESS = "0x10"
ES8388_MIC_SETTINGS = (
    ("0x0a", "0x00"),
    ("0x03", "0x09"),
    ("0x0d", "0x03"),
)


def _alsa_environment():
    environment = os.environ.copy()
    # Stable diagnostics even when the serial console uses a Chinese locale.
    environment["LC_ALL"] = "C"
    return environment


def _check_alsa_stderr(stderr_text, program):
    """Only ALSA's normal raw-format banner is informational.

    Quiet mode suppresses that banner, but older builds/wrappers can still
    emit it. All other diagnostics remain failures, including recovered XRUNs
    for which ALSA may return exit code zero.
    """
    notices, errors = [], []
    banner = "Recording raw data " if program == "arecord" else "Playing raw data "
    suffix = " : Signed 24 bit Little Endian, Rate 44100 Hz, Stereo"
    for line in stderr_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(banner) and line.endswith(suffix):
            notices.append(line)
        else:
            errors.append(line)
    if errors:
        raise board_audio.AudioError("%s 采集链路异常：%s" % (program, "; ".join(errors)))
    return notices


def configure_es8388_mic():
    if shutil.which("i2cset") is None:
        return {"available": False, "errors": ["i2cset 不存在"]}
    errors = []
    for register, value in ES8388_MIC_SETTINGS:
        command = [
            "i2cset", "-f", "-y", ES8388_I2C_BUS,
            ES8388_I2C_ADDRESS, register, value, "b",
        ]
        try:
            board_audio.run_command(command)
        except board_audio.AudioError as error:
            errors.append(str(error))
    # Apply after the streams start: the codec driver resets these controls
    # during initialization. This is the fixed12 condition tested on board.
    for control, value in (("ALC Capture Function", "Off"),
                           ("Left Channel", "4"), ("Right Channel", "4")):
        try:
            board_audio.run_command(["amixer", "-q", "-c", "0", "sset", control, value])
        except board_audio.AudioError as error:
            errors.append(str(error))
    return {"available": True, "errors": errors}


def _decode_s24le(data, channels, channel=0, byte_order="little"):
    """Decode ALSA S24_LE: signed low 24 bits in a 4-byte container.

    S24_3LE is a different format and must not be guessed from byte length.
    Select one input rather than averaging potentially opposing MIC signals.
    """
    data = bytes(data)
    if not data:
        raise board_audio.AudioError("录音数据为空。")

    if channels < 1 or not 0 <= channel < channels:
        raise board_audio.AudioError("录音声道选择无效。")
    if len(data) % (4 * channels):
        raise board_audio.AudioError("S24_LE 数据不是完整的 4 字节采样帧。")
    words = np.frombuffer(data, dtype="<u4")
    if byte_order == "little":
        samples = (words & 0x00ffffff).astype(np.int32)
    elif byte_order == "msb-first":
        # Diagnostic-only alternative for inspecting historical recordings.
        # Current paired-file evidence supports LE for production capture.
        samples = (((words & 0xff) << 16) | (words & 0xff00)
                   | ((words >> 16) & 0xff)).astype(np.int32)
    else:
        raise board_audio.AudioError("未知 PCM 字节顺序：%s" % byte_order)
    samples = (samples ^ 0x00800000) - 0x00800000
    samples = samples.reshape(-1, channels)[:, channel]
    return samples.astype(np.float32) / 8388608.0


def _terminate(process):
    if process is None:
        return
    if process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
        try:
            process.wait(timeout=2)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass


def capture_16k_mono(seconds, device=DEFAULT_CAPTURE_DEVICE,
                     rate=DEFAULT_CAPTURE_RATE, channels=DEFAULT_CAPTURE_CHANNELS,
                     sample_format=DEFAULT_CAPTURE_FORMAT, configure_es8388=True,
                     channel=0, playback_device=DEFAULT_KEEPALIVE_DEVICE):
    if not math.isfinite(float(seconds)) or not 1 <= float(seconds) <= 60:
        raise board_audio.AudioError("录音时长应在 1 到 60 秒之间。")
    if (rate, channels, sample_format) != (44100, 2, "S24_LE"):
        raise board_audio.AudioError("当前 ES8388 配置只验证过 44100 Hz、双声道 S24_LE。")
    if channel not in (0, 1):
        raise board_audio.AudioError("麦克风声道应为 0（左）或 1（右）。")
    duration = max(1, int(math.ceil(float(seconds))))
    record_duration = duration + CAPTURE_WARMUP_SECONDS
    raw_path = None
    playback = None
    recording = None
    playback_log = None
    capture_errors = []
    es8388_result = {"available": False, "errors": []}

    try:
        handle = tempfile.NamedTemporaryFile(prefix="labmate_mic_", suffix=".raw", delete=False)
        raw_path = Path(handle.name)
        handle.close()
        # A file cannot fill a PIPE and stall the playback clock on repeated
        # underruns. Check it before terminating playback ourselves.
        playback_log = tempfile.TemporaryFile()

        playback_command = [
            "aplay", "-q", "-D", playback_device,
            "-t", "raw", "-f", sample_format,
            "-r", str(rate), "-c", str(channels),
            "-d", str(record_duration + 3), "/dev/zero",
        ]
        try:
            playback = subprocess.Popen(
                playback_command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=playback_log,
                env=_alsa_environment(),
            )
        except OSError as error:
            raise board_audio.AudioError("静音播放启动失败：%s" % error)

        time.sleep(1.0)
        if playback.poll() is not None:
            playback_log.seek(0)
            detail = playback_log.read().decode("utf-8", "replace")
            raise board_audio.AudioError("静音播放提前退出：%s" % detail.strip())

        record_command = [
            "arecord", "-q", "-D", device,
            "-t", "raw", "-f", sample_format,
            "-r", str(rate), "-c", str(channels),
            "-d", str(record_duration), str(raw_path),
        ]
        try:
            recording = subprocess.Popen(
                record_command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=_alsa_environment(),
            )
        except OSError as error:
            raise board_audio.AudioError("arecord 启动失败：%s" % error)

        recording_started = time.monotonic()
        time.sleep(1.0)
        if recording.poll() is not None:
            detail = recording.stderr.read().decode("utf-8", "replace")
            raise board_audio.AudioError("arecord 提前退出：%s" % detail.strip())
        if configure_es8388:
            es8388_result = configure_es8388_mic()
            if not es8388_result["available"] or es8388_result["errors"]:
                raise board_audio.AudioError(
                    "麦克风配置失败：%s" % "; ".join(es8388_result["errors"]))

        remaining = CAPTURE_WARMUP_SECONDS - (time.monotonic() - recording_started)
        if remaining <= 0:
            raise board_audio.AudioError("初始化超过预留时间，本次录音未用于识别。")
        time.sleep(remaining)
        print("现在开始说话，录音约 %d 秒。" % duration, flush=True)

        try:
            _, stderr = recording.communicate(timeout=duration + 8)
        except subprocess.TimeoutExpired:
            raise board_audio.AudioError("arecord 超时，本次录音未用于识别。")
        stderr_text = stderr.decode("utf-8", "replace").strip()
        if recording.returncode != 0:
            raise board_audio.AudioError("arecord 返回码 %s：%s" % (recording.returncode, stderr_text))
        capture_notices = _check_alsa_stderr(stderr_text, "arecord")
        if playback.poll() is not None:
            raise board_audio.AudioError("录音期间静音播放提前退出，本次不执行识别。")
        playback_log.seek(0)
        playback_stderr = playback_log.read().decode("utf-8", "replace").strip()
        capture_notices.extend(_check_alsa_stderr(playback_stderr, "aplay"))

        frame_bytes = 4 * channels
        raw = raw_path.read_bytes()
        expected_bytes = record_duration * rate * frame_bytes
        if len(raw) < expected_bytes:
            raise board_audio.AudioError("录音长度不足：预期 %d 字节，实际 %d。" %
                                        (expected_bytes, len(raw)))
        start = CAPTURE_WARMUP_SECONDS * rate * frame_bytes
        end = start + int(round(float(seconds) * rate)) * frame_bytes
        audio = _decode_s24le(raw[start:end], channels, channel=channel,
                              byte_order="little")
        audio_16k = board_audio.resample_linear(audio, rate, TARGET_RATE)
        metadata = {
            "recorded_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "native_rate": rate,
            "device_name": device,
            "format": sample_format,
            "pcm_layout": "s24-le-low24-in-4",
            "channels": channels,
            "selected_channel": channel,
            "discarded_startup_seconds": CAPTURE_WARMUP_SECONDS,
            "duration_seconds": len(audio) / float(rate),
            "capture_stderr": stderr_text,
            "playback_stderr": playback_stderr,
            "capture_warnings": capture_notices,
            "truncated": False,
            "capture_errors": capture_errors,
            "es8388_init": es8388_result,
        }
        return audio_16k, metadata
    finally:
        _terminate(recording)
        _terminate(playback)
        if playback_log is not None:
            playback_log.close()
        if raw_path is not None:
            try:
                raw_path.unlink()
            except OSError:
                pass
