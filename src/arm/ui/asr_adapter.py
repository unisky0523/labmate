"""GUI adapter for the user's 20261015(1) board sources (Python 3.7+).

No TextApplication/process/run dispatch, terminal input, WAV recording or record
writes. Model and ALSA stream are initialized once per assistant process. Idle
audio is segmented in bounded RAM and is never selected for a later button press.
"""
import contextlib
import json
import os
from pathlib import Path
import queue
import sys
import time
from types import SimpleNamespace


class Cancelled(Exception):
    pass


def gui_splitter(base, args):
    """Preserve PCM/gates; tolerate brief weak noise during end silence."""
    class NoiseTolerantSplitter(base):
        def accept(self, frame):
            previous_quiet = self.quiet
            result = super().accept(frame)
            if previous_quiet and self.quiet == 0 and (self.frames or self.discarding):
                centered = frame - frame.mean()
                level = float((centered * centered).mean() ** 0.5)
                if level < self.threshold * 2:
                    # A 20 ms weak burst adds at most 60 ms of end delay,
                    # instead of resetting the full 800 ms silence window.
                    self.quiet = max(0, previous_quiet - 2)
            return result
    return NoiseTolerantSplitter(args.speech_threshold, args.end_silence, args.max_utterance)


class BoardRecognizer:
    def __init__(self, root, modules=None, clock=time.monotonic):
        self.root = Path(root).resolve()
        self.modules = modules  # Dependency injection for lifecycle/audio tests.
        self.clock = clock
        self.microphone = None
        self.model = None
        self.shutdown = None

    def check_cancelled(self, cancelled=None):
        if self.shutdown.is_set() or (cancelled is not None and cancelled.is_set()):
            raise Cancelled()

    def prepare(self, shutdown, progress):
        self.shutdown = shutdown
        if self.modules is None:
            if not (self.root / 'board_listen.py').is_file():
                raise RuntimeError('找不到语音源码目录：%s' % self.root)
            # Prepend only the separately deployed, frozen user source copy.
            sys.path.insert(0, str(self.root))
            with contextlib.redirect_stdout(sys.stderr):
                import asr_backend
                import asr_cli
                import asr_grammar
                import board_listen
            self.modules = SimpleNamespace(backend=asr_backend, cli=asr_cli,
                                           grammar=asr_grammar, listen=board_listen)
        self.check_cancelled()
        model_path = Path(os.environ.get('LABMATE_MODEL_PATH',
                                       str(self.root / 'models/vosk-model-small-cn-0.22')))
        if not (model_path / 'am/final.mdl').is_file():
            raise RuntimeError('找不到模型 am/final.mdl：%s' % model_path)
        progress('正在加载 Vosk 中文模型（本次打开只加载一次）……')
        started = self.clock()
        with contextlib.redirect_stdout(sys.stderr):
            self.modules.backend.SetLogLevel(-1)
            self.model = self.modules.backend.Model(str(model_path))
        self.check_cancelled()
        progress('模型已加载，用时 %.1f 秒；正在初始化麦克风……' % (self.clock() - started))
        args = SimpleNamespace(speech_threshold=0.01, end_silence=0.8,
                               max_utterance=12.0, playback_device='default',
                               audio_device='hw:0,1', mic_channel=0,
                               no_es8388_init=False)
        if hasattr(self.modules.listen, 'UtteranceSplitter'):
            from audio_frontend import create_microphone
            self.microphone = create_microphone(self.modules.listen, args,
                gui_splitter(self.modules.listen.UtteranceSplitter, args))
            progress('正在自检采样排列和左右声道，请先保持安静……')
        else:
            self.microphone = self.modules.listen.ContinuousMicrophone(args)
        with contextlib.redirect_stdout(sys.stderr):
            self.microphone.__enter__()
        self.check_cancelled()
        if hasattr(self.microphone, 'frontend'):
            frontend = self.microphone.frontend
            deadline = self.clock()+7
            while not frontend.profile_ready.wait(.1):
                self.check_cancelled()
                if self.microphone.error is not None:
                    raise RuntimeError(str(self.microphone.error))
                if self.microphone.requires_calibration:
                    self.ready_message = '请先点击“语音检测”，按提示说三遍“记录数据”。'
                    progress(self.ready_message)
                    return
                if self.clock() >= deadline:
                    raise RuntimeError('音频自检超时，请关闭助手并检查麦克风。')
            progress('音频自检通过：%s；左右声道均保留，按整句选择有效声道。' % frontend.profile['byte_order'])
            with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
                saved = json.loads((self.root.parent/'data/audio_diagnostics/voice_calibration.json').read_text(encoding='utf-8'))
                if saved['profile']['byte_order'] == frontend.profile['byte_order'] and saved['channel'] in (0, 1):
                    self.microphone.reset_frontend(frontend.profile, saved['channel'])
                    progress('已恢复与当前采样排列一致的语音检测结果。')
            with contextlib.suppress(OSError):
                path = self.root.parent/'data/audio_diagnostics/audio_profile_latest.json'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(frontend.profile, indent=2), encoding='utf-8')

    def recognize(self, cancelled, progress):
        try:
            self.check_cancelled(cancelled)
            mic = self.microphone
            if mic.error is not None:
                raise RuntimeError(str(mic.error))
            if getattr(mic, 'requires_calibration', None):
                raise RuntimeError('请先点击“语音检测”：'+mic.requires_calibration)
            # Discard queued idle/previous-turn audio. Also reject an utterance
            # still in progress at button time using its capture-time boundary.
            while True:
                try:
                    mic.utterances.get_nowait()
                except queue.Empty:
                    break
            cutoff = self.clock()
            rejected = mic.splitter.rejected
            progress('现在请说话；说完停顿约 0.8 秒，等待显示结果。')
            deadline = cutoff + 25.0
            while True:
                self.check_cancelled(cancelled)
                if mic.error is not None:
                    raise RuntimeError(str(mic.error))
                if getattr(mic, 'requires_calibration', None):
                    raise RuntimeError('请先点击“语音检测”：'+mic.requires_calibration)
                if mic.splitter.rejected != rejected:
                    detail = ('；'+mic.frontend.diagnostic()) if hasattr(mic, 'frontend') else ''
                    raise RuntimeError('连续声音超过 12 秒，未找到句尾静音，本轮已丢弃'+detail+'。')
                if self.clock() >= deadline:
                    detail = ('；'+mic.frontend.diagnostic()) if hasattr(mic, 'frontend') else ''
                    raise RuntimeError('25 秒内未形成完整语音'+detail+'。请检查麦克风和环境噪声。')
                try:
                    audio, metadata, ended = mic.utterances.get(timeout=0.1)
                except queue.Empty:
                    continue
                began = ended - metadata['duration_seconds']
                # Permit only the splitter's 300 ms pre-roll before the click.
                if began < cutoff - 0.32 or self.clock() - ended > 5.0:
                    continue
                break
            self.check_cancelled(cancelled)
            channel = '，%s声道' % ('右' if metadata.get('selected_channel') == 1 else '左') if 'selected_channel' in metadata else ''
            progress('收音结束（%.1f 秒%s），正在识别……' % (metadata['duration_seconds'], channel))
            quantities_heard = set()
            def partial(text):
                self.check_cancelled(cancelled)
                for name in ('电压', '电流', '频率'):
                    if name in text and name not in quantities_heard:
                        quantities_heard.add(name)
                        progress('已听到%s，正在核对数值及毫、微、纳、皮、千、兆等单位前缀……' % name)
            with contextlib.redirect_stdout(sys.stderr):
                result = self.modules.cli.analyze(
                    audio, self.model, metadata, 0.45, on_partial=partial,
                    grammar=self.modules.grammar.GRAMMAR_JSON, command_grammar=True, unit_context=True)
            self.check_cancelled(cancelled)
            if result.get('recognition_ms') is not None:
                progress('识别计算完成，用时 %.1f 秒。' % (result['recognition_ms'] / 1000.0))
            command = result.get('command')
            description = self.modules.cli.command_description(command) if isinstance(command, dict) else ''
            return {'text': result.get('text', ''), 'command': command,
                    'reason': result.get('reason'), 'simulated': False,
                    'summary': description + ('；请核对后确认。' if description else ''),
                    'recognition_ms': result.get('recognition_ms'),
                    'duration_seconds': metadata['duration_seconds']}
        except Cancelled:
            return None

    def calibrate(self, cancelled, progress):
        """Three raw recordings; ASR comparison only, never dispatch commands."""
        import numpy as np
        from audio_frontend import rms_frames, select_calibration
        mic = self.microphone
        if mic.error is not None:
            raise RuntimeError(str(mic.error))
        previous = mic.frontend.profile
        channel = mic.frontend.preferred_channel
        previous_error = mic.requires_calibration
        clips = []
        try:
            mic.capture_raw.set()
            for turn in range(3):
                self.check_cancelled(cancelled)
                while True:
                    try: mic.raw_queue.get_nowait()
                    except queue.Empty: break
                cutoff = self.clock()
                progress('第 %d/3 次：现在请说一遍“记录数据”，说完保持安静（录音 4 秒）。' % (turn+1))
                parts = []
                while len(parts) < 200:
                    self.check_cancelled(cancelled)
                    if mic.error is not None:
                        raise RuntimeError(str(mic.error))
                    if self.clock()-cutoff > 7:
                        raise RuntimeError('检测录音未收到足够采样，请重新打开助手。')
                    try: raw, ended = mic.raw_queue.get(timeout=.1)
                    except queue.Empty: continue
                    if ended >= cutoff: parts.append(raw)
                clips.append(b''.join(parts))
            mic.capture_raw.clear()
            candidates = []
            for layout in ('little', 'msb-first'):
                for selected in (0, 1):
                    hits, confidences, texts, floors = 0, [], [], []
                    for turn, raw in enumerate(clips):
                        self.check_cancelled(cancelled)
                        progress('录音完成，正在对比 %s／%s声道，第 %d/3 段……' % (layout, '右' if selected else '左', turn+1))
                        native = self.modules.listen.board_mic._decode_s24le(raw, 2, channel=selected, byte_order=layout)
                        floors.append(float(np.percentile(rms_frames(native), 20)))
                        audio = self.modules.listen.board_audio.resample_linear(native, 44100, 16000)
                        with contextlib.redirect_stdout(sys.stderr):
                            result = self.modules.cli.analyze(audio, self.model, {}, .45,
                                on_partial=lambda text:self.check_cancelled(cancelled),
                                grammar=self.modules.grammar.GRAMMAR_JSON, command_grammar=True)
                        text = ''.join(result.get('text', '').split())
                        words = [float(word['conf']) for word in result.get('words', []) if 'conf' in word]
                        confidence = min(words) if words else 0.
                        match = text == '记录数据' and not result.get('reason') and confidence >= .45
                        hits += int(match)
                        if match: confidences.append(confidence)
                        texts.append(text)
                    candidates.append(dict(layout=layout, channel=selected, hits=hits, texts=texts,
                                           confidence=float(np.mean(confidences)) if confidences else 0.,
                                           noise_floor=float(np.median(floors))))
            report = select_calibration(candidates)
            if report['success']:
                best = report['selected']
                noises = [next(row['noise_floor'] for row in candidates if row['layout']==best['layout'] and row['channel']==c) for c in (0, 1)]
                report.update(channel=best['channel'], profile=dict(byte_order=best['layout'],
                    noise_rms=noises, thresholds=[max(.01, noise*2) for noise in noises], calibrated=True))
            self.check_cancelled(cancelled)
            return report
        except Cancelled:
            return None
        finally:
            mic.capture_raw.clear()
            mic.reset_frontend(previous, channel)
            mic.requires_calibration = previous_error

    def apply_calibration(self, report):
        if not report.get('success'):
            return
        path = self.root.parent/'data/audio_diagnostics/voice_calibration.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(str(temporary), str(path))
        self.microphone.reset_frontend(report['profile'], report['channel'])

    def recognize_confirmation(self, cancelled, progress):
        """Wait on the same microphone/model; only an explicit confirm can save."""
        try:
            self.check_cancelled(cancelled)
            mic = self.microphone
            while True:
                try:
                    mic.utterances.get_nowait()
                except queue.Empty:
                    break
            cutoff = self.clock()
            progress('可点击“确认保存”，或说“确认”；说完停顿约 0.8 秒。')
            while True:
                self.check_cancelled(cancelled)
                if mic.error is not None:
                    raise RuntimeError(str(mic.error))
                try:
                    audio, metadata, ended = mic.utterances.get(timeout=0.1)
                except queue.Empty:
                    continue
                if ended - metadata['duration_seconds'] < cutoff - 0.32 or self.clock() - ended > 5.0:
                    continue
                def partial(text):
                    self.check_cancelled(cancelled)
                progress('已收音，正在识别确认语音……')
                with contextlib.redirect_stdout(sys.stderr):
                    result = self.modules.cli.analyze(
                        audio, self.model, metadata, 0.45, on_partial=partial,
                        grammar=self.modules.grammar.SAVE_CONFIRM_GRAMMAR_JSON,
                        command_grammar=True)
                self.check_cancelled(cancelled)
                text = ''.join(result.get('text', '').split())
                if (not result.get('reason') and text in ('确认', '确认保存')
                        and (result.get('command') or {}).get('intent') == 'confirm'):
                    return {'text': text}
                progress('未听到有效的“确认”，可再说一次，或点击“确认保存”。')
        except Cancelled:
            return None

    def close(self):
        if self.microphone is not None:
            microphone, self.microphone = self.microphone, None
            with contextlib.redirect_stdout(sys.stderr):
                microphone.close()
        self.model = None
