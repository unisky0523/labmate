"""Board audio helpers for the ATK-ZYNQ ES8388 ALSA path."""

from datetime import datetime
import math
from pathlib import Path
import subprocess
import tempfile
import wave

import numpy as np


DEFAULT_CAPTURE_DEVICE = "hw:0,1"
DEFAULT_PLAYBACK_DEVICE = "default"
DEFAULT_CAPTURE_RATE = 44100
DEFAULT_CAPTURE_CHANNELS = 2
DEFAULT_CAPTURE_FORMAT = "S24_LE"
TARGET_RATE = 16000


class AudioError(RuntimeError):
    pass


def run_command(command):
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except OSError as error:
        raise AudioError("无法执行命令：%s" % error)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise AudioError("命令失败：%s\n%s" % (" ".join(command), detail))
    return result


def resample_linear(audio, source_rate, target_rate=TARGET_RATE):
    audio = np.asarray(audio, dtype=np.float32)
    if source_rate <= 0 or target_rate <= 0:
        raise AudioError("采样率无效。")
    if source_rate == target_rate or len(audio) == 0:
        return audio
    target_length = int(round(len(audio) * float(target_rate) / float(source_rate)))
    if target_length <= 1:
        return audio[:1]
    old_positions = np.arange(len(audio), dtype=np.float64)
    new_positions = np.linspace(0.0, float(len(audio) - 1), target_length, dtype=np.float64)
    return np.interp(new_positions, old_positions, audio.astype(np.float64)).astype(np.float32)


def read_wav_mono(path):
    path = Path(path)
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.getnframes()
            data = handle.readframes(frames)
    except (OSError, wave.Error) as error:
        raise AudioError("无法读取 WAV：%s" % error)
    if width != 2:
        raise AudioError("仅支持 16 bit PCM WAV，当前位深：%d" % (width * 8))
    audio = np.frombuffer(data, dtype="<i2").astype(np.float32)
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return rate, audio / 32768.0


def write_wav_16k(path, audio, rate=TARGET_RATE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767.0)
    pcm = pcm.round().astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())
    return path


def _arecord(device, seconds, path, rate, channels):
    duration = max(1, int(math.ceil(float(seconds))))
    command = [
        "arecord",
        "-D", device,
        "-f", "S16_LE",
        "-r", str(rate),
        "-c", str(channels),
        "-d", str(duration),
        "-t", "wav",
        str(path),
    ]
    run_command(command)


def capture_16k_mono(seconds, device=DEFAULT_CAPTURE_DEVICE,
                     rate=DEFAULT_CAPTURE_RATE, channels=DEFAULT_CAPTURE_CHANNELS):
    # Keep this public helper compatible with the board-verified microphone path.
    import board_mic

    return board_mic.capture_16k_mono(
        seconds,
        device=device,
        rate=rate,
        channels=channels,
    )

    candidates = []
    if device:
        candidates.append((device, rate, channels))
    candidates.extend([
        (DEFAULT_CAPTURE_DEVICE, 48000, 2),
        ("plughw:0,1", 44100, 2),
        ("hw:0,1", 48000, 2),
    ])

    seen = set()
    last_error = None
    for candidate_device, candidate_rate, candidate_channels in candidates:
        key = (candidate_device, candidate_rate, candidate_channels)
        if key in seen:
            continue
        seen.add(key)
        temporary_path = None
        try:
            handle = tempfile.NamedTemporaryFile(prefix="labmate_", suffix=".wav", delete=False)
            temporary_path = Path(handle.name)
            handle.close()
            _arecord(candidate_device, seconds, temporary_path, candidate_rate, candidate_channels)
            source_rate, audio = read_wav_mono(temporary_path)
            audio_16k = resample_linear(audio, source_rate, TARGET_RATE)
            metadata = {
                "recorded_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                "native_rate": source_rate,
                "device_name": candidate_device,
                "truncated": False,
                "capture_errors": [],
            }
            return audio_16k, metadata
        except AudioError as error:
            last_error = error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    raise AudioError("ALSA 录音失败；尝试过 %s；最后错误：%s" % (list(seen), last_error))
