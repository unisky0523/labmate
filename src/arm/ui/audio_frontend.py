"""Validate the observed PCM layouts and preserve both microphone channels.

No model, ALSA control writes, normalization of recognized audio, or record I/O.
Calibration requires a clear sign-byte signature in a quiet one-second window.
It never selects a layout merely because that layout makes audio smaller.
"""
from collections import deque
from datetime import datetime
import queue
import threading
import time

import numpy as np


class AudioProfileError(RuntimeError):
    pass


def select_calibration(candidates):
    eligible = [row for row in candidates if row['hits'] >= 2 and row['confidence'] >= .45
                and row['noise_floor'] < .03]
    eligible.sort(key=lambda row:(row['hits'], row['confidence']), reverse=True)
    selected = eligible[0] if eligible else None
    if len(eligible) > 1:
        other = next((row for row in eligible[1:] if row['layout'] != selected['layout']), None)
        if other and other['hits']==selected['hits'] and selected['confidence']-other['confidence'] < .03:
            selected = None
    success = selected is not None
    message = ('检测通过：%s／%s声道，%d/3 命中，已应用。' %
               (selected['layout'], '右' if selected['channel'] else '左', selected['hits'])) if success else '检测未能确定可靠组合，本次未更改设置；请靠近麦克风后重试。'
    lines = ['%s／%s：%d/3，置信分数 %.2f' % (row['layout'], '右' if row['channel'] else '左', row['hits'], row['confidence']) for row in candidates]
    return dict(success=success, selected=selected, candidates=candidates, message=message, summary='\n'.join(lines))


def rms_frames(audio, frame_samples=882):
    frames = np.asarray(audio).reshape(-1, frame_samples)
    centered = frames - frames.mean(axis=1, keepdims=True)
    return np.sqrt(np.mean(centered * centered, axis=1))


def identify_profile(raw, decoder, frame_samples=882):
    if not raw or len(raw) % (frame_samples * 8):
        raise AudioProfileError('音频采样帧不完整。')
    octets = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 2, 4)
    if len(octets) < frame_samples * 25:
        raise AudioProfileError('音频自检样本不足。')
    # Both supported captures have the sign byte at opposite ends of the
    # low three bytes. Loud speech, zero input, and other packing stay ambiguous.
    sign = np.mean(np.isin(octets[:, :, (0, 2)], [0, 255]), axis=0)
    votes = []
    for fractions in sign:
        index = int(np.argmax(fractions))
        if fractions[index] >= .95 and fractions[1-index] <= .50 and fractions[index]-fractions[1-index] >= .45:
            votes.append(index)
    if not votes or len(set(votes)) != 1:
        raise AudioProfileError('无法可靠判断采样排列，请保持安静后重新打开助手。')
    winner = votes[0]
    layout = ('msb-first', 'little')[winner]
    floors = []
    for channel in (0, 1):
        audio = decoder(raw, 2, channel=channel, byte_order=layout)
        levels = rms_frames(audio, frame_samples)
        floor = float(np.percentile(levels, 95))
        if not np.isfinite(floor) or floor >= .03 or np.mean(np.abs(audio) >= .995) > .001:
            raise AudioProfileError('音频自检期间声音过大，请安静后重新打开助手。')
        floors.append(floor)
    return dict(byte_order=layout, sign_byte_fraction=sign.tolist(),
                noise_rms=floors, thresholds=[max(.01, value*2) for value in floors])


class StereoFrontEnd:
    def __init__(self, decoder, splitter, frame_samples=882):
        self.decoder, self.splitter = decoder, splitter
        self.frame_samples = frame_samples
        self.calibration = []
        self.calibration_windows = 0
        self.profile = None
        self.preferred_channel = None
        self.profile_ready = threading.Event()
        self.frames = deque(maxlen=splitter.max_frames+16)
        self.health_window = []
        self.frames_seen = 0
        self.voiced_frames = 0
        self.last_levels = [0., 0.]

    def feed(self, raw):
        if len(raw) != self.frame_samples*8:
            raise AudioProfileError('音频采样帧不完整。')
        if self.profile is None:
            self.calibration.append(bytes(raw))
            if len(self.calibration) < 50:
                return None
            block = b''.join(self.calibration)
            self.calibration.clear()
            self.calibration_windows += 1
            try:
                self.profile = identify_profile(block, self.decoder, self.frame_samples)
            except AudioProfileError:
                if self.calibration_windows >= 5:
                    raise
                return None
            self.profile_ready.set()
            return None  # Calibration is never a command.

        self.health_window.append(bytes(raw))
        if len(self.health_window) == 50:
            block = b''.join(self.health_window)
            self.health_window.clear()
            try:
                observed = identify_profile(block, self.decoder, self.frame_samples)
            except AudioProfileError:
                observed = None  # Speech is not a quiet calibration window.
            if observed and observed['byte_order'] != self.profile['byte_order']:
                raise AudioProfileError('检测到输入采样排列改变，请关闭并重新打开助手完成自检。')

        pair = tuple(self.decoder(raw, 2, channel=c, byte_order=self.profile['byte_order'])
                     for c in (0, 1))
        levels = np.asarray([float(rms_frames(a, self.frame_samples)[0]) for a in pair])
        thresholds = np.asarray(self.profile['thresholds'])
        gate_channel = self.preferred_channel if self.preferred_channel is not None else int(np.argmax(levels / thresholds))
        # Only the gate sees a scaled proxy. The retained channel samples
        # are unscaled and are selected once for the complete utterance.
        proxy = pair[gate_channel]*(self.splitter.threshold/thresholds[gate_channel])
        self.frames.append((pair, levels))
        self.frames_seen += 1
        self.voiced_frames += int(np.any(levels >= thresholds))
        self.last_levels = levels.tolist()
        segment = self.splitter.accept(proxy)
        if segment is None:
            return None
        _, start, end = segment
        count = (end-start)//self.frame_samples
        if count > len(self.frames):
            raise AudioProfileError('音频分句缓存不完整。')
        selected = list(self.frames)[-count:]
        energies = np.asarray([item[1] for item in selected])
        voiced = np.count_nonzero(energies >= thresholds, axis=0)
        contrast = np.sum(np.maximum(energies/np.maximum(self.profile['noise_rms'], 1e-6)-1, 0), axis=0)
        channel = self.preferred_channel if self.preferred_channel is not None else max((0, 1), key=lambda c: (int(voiced[c]), float(contrast[c])))
        audio = np.concatenate([item[0][channel] for item in selected])
        metadata = dict(selected_channel=channel, channels=2,
                        pcm_layout='s24-le-low24-in-4' if self.profile['byte_order']=='little'
                        else 's24-low3-byte-reversed-in-4',
                        byte_order=self.profile['byte_order'],
                        noise_rms=self.profile['noise_rms'], channel_thresholds=self.profile['thresholds'],
                        speech_threshold=float(thresholds[channel]), channel_voiced_frames=voiced.tolist(),
                        stream_start_sample=start, stream_end_sample=end)
        return audio, metadata

    def diagnostic(self):
        return '收音帧 %d，其中有声帧 %d；最近电平 %.4f/%.4f' % (
            self.frames_seen, self.voiced_frames, self.last_levels[0], self.last_levels[1])


def create_microphone(listen, args, splitter):
    """Reuse the original ALSA/codec lifecycle; replace only its reader front end."""
    class ProfiledMicrophone(listen.ContinuousMicrophone):
        def __init__(self):
            super().__init__(args)
            self.splitter = splitter
            self.frontend = StereoFrontEnd(listen.board_mic._decode_s24le, self.splitter,
                                           listen.FRAME_SAMPLES)
            self.raw_queue = queue.Queue(maxsize=250)
            self.capture_raw = threading.Event()
            self.audio_lock = threading.Lock()
            self.requires_calibration = None

        def reset_frontend(self, profile, channel=None):
            with self.audio_lock:
                self.splitter = type(splitter)(args.speech_threshold, args.end_silence, args.max_utterance)
                self.frontend = StereoFrontEnd(listen.board_mic._decode_s24le, self.splitter, listen.FRAME_SAMPLES)
                self.frontend.profile = profile
                self.frontend.preferred_channel = channel
                if profile is not None:
                    self.frontend.profile_ready.set()
                self.requires_calibration = None
                while True:
                    try: self.utterances.get_nowait()
                    except queue.Empty: break

        def _read(self):
            warmup = listen.board_mic.CAPTURE_WARMUP_SECONDS*listen.RATE
            try:
                while not self.stop.is_set():
                    raw = self.recording.stdout.read(listen.FRAME_BYTES)
                    if self.stop.is_set():
                        break
                    self.check_devices()
                    if len(raw) != listen.FRAME_BYTES:
                        raise AudioProfileError('持续录音流结束或采样帧不完整。')
                    if warmup > 0:
                        warmup -= listen.FRAME_SAMPLES
                        continue
                    if not self.ready.is_set():
                        continue
                    if self.capture_raw.is_set():
                        try:
                            self.raw_queue.put_nowait((raw, time.monotonic()))
                        except queue.Full:
                            raise AudioProfileError('检测录音缓存积压，请重试。')
                        continue
                    if self.requires_calibration:
                        continue
                    with self.audio_lock:
                        try:
                            segment = self.frontend.feed(raw)
                        except AudioProfileError as error:
                            self.requires_calibration = str(error)
                            continue
                        if segment is None:
                            continue
                        self._enqueue(segment)
            except Exception as error:
                if not self.stop.is_set():
                    self.error = error

        def _enqueue(self, segment):
            native, metadata = segment
            ended = time.monotonic()
            duration = len(native)/float(listen.RATE)
            metadata.update(recorded_at=datetime.fromtimestamp(time.time()-duration).astimezone().isoformat(timespec='milliseconds'),
                                    native_rate=listen.RATE, device_name=args.audio_device,
                                    format='S24_LE', discarded_startup_seconds=listen.board_mic.CAPTURE_WARMUP_SECONDS,
                                    duration_seconds=duration, capture_errors=[], truncated=False,
                                    es8388_init=self.es8388, continuous=True, endpoint='silence',
                                    end_silence_seconds=args.end_silence)
            converted = listen.board_audio.resample_linear(native, listen.RATE,
                                                                  listen.board_mic.TARGET_RATE)
            try:
                self.utterances.put_nowait((converted, metadata, ended))
            except queue.Full:
                self.dropped += 1
    return ProfiledMicrophone()
