"""Speaker helpers for the ATK-ZYNQ ES8388 playback path."""

import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import wave

import board_audio


PROMPT_DIR = Path(__file__).resolve().parent / "data" / "audio" / "prompts"


def play_wav(path, device=board_audio.DEFAULT_PLAYBACK_DEVICE):
    path = Path(path)
    if not path.is_file():
        raise board_audio.AudioError("提示音频不存在：%s" % path)
    board_audio.run_command(["aplay", "-D", device, str(path)])
    return True


def play_prompt(name, device=board_audio.DEFAULT_PLAYBACK_DEVICE):
    filename = name if name.endswith(".wav") else name + ".wav"
    path = PROMPT_DIR / filename
    if not path.is_file():
        return False
    return play_wav(path, device)


def write_tone(path, frequency=880.0, seconds=0.25, rate=48000, amplitude=0.35):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(rate * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        for index in range(frames):
            value = int(32767.0 * amplitude * math.sin(2.0 * math.pi * frequency * index / rate))
            handle.writeframes(struct.pack("<h", value))
    return path


def play_tone(frequency=880.0, seconds=0.25, device=board_audio.DEFAULT_PLAYBACK_DEVICE):
    temporary_path = None
    try:
        handle = tempfile.NamedTemporaryFile(prefix="labmate_tone_", suffix=".wav", delete=False)
        temporary_path = Path(handle.name)
        handle.close()
        write_tone(temporary_path, frequency=frequency, seconds=seconds)
        return play_wav(temporary_path, device)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass


def alert(device=board_audio.DEFAULT_PLAYBACK_DEVICE):
    if play_prompt("source_conflict", device):
        return True
    play_tone(660.0, 0.20, device)
    play_tone(880.0, 0.20, device)
    return True


def speak_text(text, device=board_audio.DEFAULT_PLAYBACK_DEVICE):
    text = str(text or "").strip()
    if not text:
        return False
    for executable in ("espeak-ng", "espeak"):
        if shutil.which(executable):
            try:
                subprocess.run([executable, "-v", "zh", text], timeout=20)
                return True
            except Exception:
                break
    play_tone(660.0, 0.15, device)
    return False
