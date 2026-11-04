"""Persistent ALSA capture and pause-delimited commands on the round-one path.

Only the reader thread touches the audio pipe. Recognition and application
operations stay on the main thread. Each complete utterance is resampled once
with the original board_audio function; there is no streaming resampler.
"""

from collections import deque
from datetime import datetime
from pathlib import Path
import math
import queue
import signal
import subprocess
import tempfile
import threading
import time

import numpy as np

import board_audio
import board_mic


RATE = board_mic.DEFAULT_CAPTURE_RATE
FRAME_SAMPLES = RATE // 50  # 20 ms; exact at 44100 Hz.
FRAME_BYTES = FRAME_SAMPLES * 4 * 2
MAX_QUEUE_AGE = 5.0


class UtteranceSplitter:
    """Energy gate with 300 ms pre-roll and bounded utterance storage."""

    def __init__(self, threshold=0.01, end_silence=0.8, max_seconds=12.0):
        self.threshold = threshold
        self.end_frames = int(math.ceil(end_silence * 50))
        self.max_frames = int(math.ceil(max_seconds * 50))
        self.pre_roll = deque(maxlen=15)
        self.frames = []
        self.voiced = self.quiet = self.position = 0
        self.discarding = False
        self.rejected = 0

    def accept(self, frame):
        self.position += len(frame)
        centered = frame - np.mean(frame)
        speech = float(np.sqrt(np.mean(centered * centered))) >= self.threshold
        if self.discarding:
            self.quiet = 0 if speech else self.quiet + 1
            if self.quiet >= self.end_frames:
                self.discarding = False
                self.quiet = 0
            return None
        if not self.frames:
            if not speech:
                self.pre_roll.append(frame)
                return None
            self.frames = list(self.pre_roll)
            self.pre_roll.clear()
        self.frames.append(frame)
        self.voiced += int(speech)
        self.quiet = 0 if speech else self.quiet + 1
        if len(self.frames) >= self.max_frames:
            self.frames = []
            self.voiced = 0
            self.discarding = True
            self.rejected += 1
            return None
        if self.quiet < self.end_frames:
            return None
        frames, voiced = self.frames, self.voiced
        self.frames = []
        self.voiced = self.quiet = 0
        # A click or very short burst is not an utterance. Keep short "确认".
        if voiced < 10:  # 200 ms of above-threshold audio.
            return None
        audio = np.concatenate(frames)
        return audio, self.position - len(audio), self.position


class ContinuousMicrophone:
    def __init__(self, args):
        self.args = args
        self.splitter = UtteranceSplitter(args.speech_threshold, args.end_silence,
                                          args.max_utterance)
        self.utterances = queue.Queue(maxsize=3)
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.dropped = 0
        self.reported_drops = (0, 0)
        self.playback = self.recording = self.worker = None
        self.logs = []
        self.directory = None

    def _log(self, name):
        path = Path(self.directory.name) / (name + ".log")
        writer = path.open("wb")
        reader = path.open("rb")  # Independent offset: never seek the child's fd.
        self.logs.append((name, writer, reader))
        return writer

    def check_devices(self):
        for name, writer, reader in self.logs:
            while True:
                offset = reader.tell()
                line = reader.readline()
                if not line or not line.endswith(b"\n"):
                    reader.seek(offset)
                    break
                board_mic._check_alsa_stderr(line.decode("utf-8", "replace"), name)
        for name, process in (("aplay", self.playback), ("arecord", self.recording)):
            if process is not None and process.poll() is not None:
                raise board_audio.AudioError("%s 提前退出，返回码 %s。" % (name, process.returncode))

    def __enter__(self):
        try:
            self.directory = tempfile.TemporaryDirectory(prefix="labmate_listen_")
            common = ["-t", "raw", "-f", "S24_LE", "-r", str(RATE), "-c", "2"]
            # Same devices/format as round one; omit -d for continuous operation.
            self.playback = subprocess.Popen(
                ["aplay", "-q", "-D", self.args.playback_device] + common + ["/dev/zero"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=self._log("aplay"), env=board_mic._alsa_environment(),
                start_new_session=True)
            time.sleep(1.0)
            self.check_devices()
            # No filename: ALSA writes raw PCM to stdout, not a growing disk file.
            self.recording = subprocess.Popen(
                ["arecord", "-q", "-D", self.args.audio_device] + common,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=self._log("arecord"), env=board_mic._alsa_environment(),
                start_new_session=True)
            started = time.monotonic()
            self.worker = threading.Thread(target=self._read, name="microphone", daemon=True)
            self.worker.start()  # Drain during warmup, so the pipe cannot fill.
            time.sleep(1.0)
            if self.error is not None:
                raise self.error
            self.es8388 = {"available": False, "errors": []}
            if not self.args.no_es8388_init:
                self.es8388 = board_mic.configure_es8388_mic()
                if not self.es8388["available"] or self.es8388["errors"]:
                    raise board_audio.AudioError("麦克风配置失败：%s" % self.es8388["errors"])
            remaining = board_mic.CAPTURE_WARMUP_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                raise board_audio.AudioError("初始化超过预留时间，请检查设备配置。")
            time.sleep(remaining)
            if self.error is not None:
                raise self.error
            self.ready.set()
            return self
        except BaseException:
            self.close()
            raise

    def _read(self):
        remaining_warmup = board_mic.CAPTURE_WARMUP_SECONDS * RATE
        try:
            while not self.stop.is_set():
                raw = self.recording.stdout.read(FRAME_BYTES)
                if self.stop.is_set():
                    break
                self.check_devices()
                if len(raw) != FRAME_BYTES:
                    raise board_audio.AudioError("持续录音流结束或采样帧不完整。")
                if remaining_warmup > 0:
                    remaining_warmup -= FRAME_SAMPLES
                    continue
                if not self.ready.is_set():
                    continue
                native = board_mic._decode_s24le(raw, 2, channel=self.args.mic_channel, byte_order="little")
                segment = self.splitter.accept(native)
                if segment is None:
                    continue
                audio, start, end = segment
                ended = time.monotonic()
                metadata = {
                    "recorded_at": datetime.fromtimestamp(
                        time.time() - len(audio) / float(RATE)).astimezone().isoformat(timespec="milliseconds"),
                    "native_rate": RATE, "device_name": self.args.audio_device,
                    "format": "S24_LE", "pcm_layout": "s24-le-low24-in-4",
                    "channels": 2, "selected_channel": self.args.mic_channel,
                    "discarded_startup_seconds": board_mic.CAPTURE_WARMUP_SECONDS,
                    "duration_seconds": len(audio) / float(RATE),
                    "capture_errors": [], "truncated": False, "es8388_init": self.es8388,
                    "continuous": True, "endpoint": "silence",
                    "stream_start_sample": start, "stream_end_sample": end,
                    "speech_threshold": self.args.speech_threshold,
                    "end_silence_seconds": self.args.end_silence,
                }
                converted = board_audio.resample_linear(audio, RATE, board_mic.TARGET_RATE)
                try:
                    self.utterances.put_nowait((converted, metadata, ended))
                except queue.Full:
                    self.dropped += 1  # Never block capture behind a long action.
        except Exception as error:
            if not self.stop.is_set():
                self.error = error

    def next_utterance(self):
        while not self.stop.is_set():
            if self.error is not None:
                raise self.error
            drops = (self.splitter.rejected, self.dropped)
            if drops != self.reported_drops:
                print("[跳过] 累计超长声音 %d 段、积压语句 %d 段；继续监听。" % drops)
                self.reported_drops = drops
            try:
                item = self.utterances.get(timeout=0.2)
            except queue.Empty:
                continue
            age = time.monotonic() - item[2]
            if age > MAX_QUEUE_AGE:
                self.dropped += 1
                continue
            item[1]["queue_wait_ms"] = round(age * 1000, 1)
            return item
        return None

    def close(self):
        self.stop.set()
        board_mic._terminate(self.recording)
        board_mic._terminate(self.playback)
        if self.worker is not None:
            self.worker.join()
        if self.recording is not None:
            self.recording.stdout.close()
        for name, writer, reader in self.logs:
            writer.close()
            reader.close()
        if self.directory is not None:
            self.directory.cleanup()

    def __exit__(self, *exc):
        self.close()


def run(args, model, asr_args, application, status):
    from asr_cli import process, save_audio

    microphone = ContinuousMicrophone(args)
    previous_sigint = signal.getsignal(signal.SIGINT)

    def interrupt(signum, frame):
        # TextApplication catches Ctrl+C inside a batch; remember exit anyway.
        microphone.stop.set()
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, interrupt)
    try:
        status.update(state="starting_audio")
        with microphone:
            print("[持续监听] 现在可以说话；句间停顿约 %.1f 秒。Ctrl+C 或说“退出程序”结束。"
                  % args.end_silence)
            print("[持续监听] 识别期间继续收音；报数和批量记录按提示说“确认”或“取消”。")
            status.update(state="listening")
            while not microphone.stop.is_set():
                item = microphone.next_utterance()
                if item is None:
                    break
                audio, metadata, ended = item
                print("[分句] %.2f 秒；排队 %.0f ms；累计跳过：超长 %d / 积压 %d。"
                      % (metadata["duration_seconds"], metadata["queue_wait_ms"],
                         microphone.splitter.rejected, microphone.dropped))
                path = save_audio(audio)
                status.update(state="recognizing", asr_partial="", audio_path=str(path))
                result, exit_requested = process(
                    audio, path, metadata, model, asr_args, application=application,
                    ask_label=False, on_partial=lambda text: status.update(asr_partial=text))
                handled_ms = (time.monotonic() - ended) * 1000
                print("[耗时] 句尾检测后至处理结束：%.0f ms（含排队、识别及操作）。" % handled_ms)
                status.update(state="listening", asr_text=result.get("text", ""),
                              asr_command=result.get("command"), asr_error=result.get("reason"),
                              end_to_handled_ms=round(handled_ms, 1))
                if exit_requested:
                    break
    except KeyboardInterrupt:
        print("\n持续监听已停止；未确认操作不保存。")
    except (board_audio.AudioError, OSError) as error:
        status.update(last_error=str(error))
        print("[持续监听停止] %s" % error)
        return 1
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
    return 0
