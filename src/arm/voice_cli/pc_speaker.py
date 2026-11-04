"""Small PC-only audio feedback helper for ASR smoke tests."""

import platform
import subprocess


def _beep_windows(frequency, duration_ms):
    import winsound
    winsound.Beep(int(frequency), int(duration_ms))


def _beep_linux(frequency, duration_ms):
    try:
        command = [
            "speaker-test", "-t", "sine", "-f", str(int(frequency)),
            "-l", "1", "-p", str(int(duration_ms)),
        ]
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
    except Exception:
        print("\a")


def beep(frequency=880, duration_ms=150):
    if platform.system() == "Windows":
        try:
            _beep_windows(frequency, duration_ms)
            return True
        except Exception:
            return False
    _beep_linux(frequency, duration_ms)
    return True


def play_result(result):
    failed = result and (
        result.get("confirm_repeat_match") is False
        or result.get("dispatch_state") in ("confirmation_mismatch", "confirmation_cancelled", "application_error")
    )
    if result and result.get("command") is not None and not failed:
        beep(880, 120)
    else:
        beep(440, 300)


def speak_text(text):
    text = str(text or "").strip()
    if not text:
        return False
    if platform.system() == "Windows":
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Speak([Console]::In.ReadToEnd())"
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Sta", "-Command", script],
                input=text, universal_newlines=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=20,
            )
            return True
        except Exception:
            return False
    for executable in ("espeak-ng", "espeak"):
        if shutil.which(executable):
            try:
                subprocess.run([executable, "-v", "zh", text], timeout=20)
                return True
            except Exception:
                return False
    return False
