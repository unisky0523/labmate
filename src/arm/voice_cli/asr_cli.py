r"""LabMate：离线中文 ASR 与领域操作解析，复用 text_cli/main。

依赖：python3 -m pip install vosk==0.3.45（板端另用 arecord/aplay，不再依赖 sounddevice）
模型：https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip
解压到本文件旁 models/vosk-model-small-cn-0.22/，其中应有 am/final.mdl。
python asr_cli.py test    只识别、解析、保存测试音频和日志，不执行实验操作
python asr_cli.py run     接应用，报数/异常标记/连续次数先核对
python asr_cli.py file --wav data/audio/example.wav   仅离线识别文件

按回车开始，说完再按回车结束；q 退出；run 下可输入 /确认 或 /取消。
完整句子结束才解析，不执行中间识别结果；不强行替换数字、单位或同音字。
麦克风默认已验证编号 2；可 --device 修改。不是常开唤醒，不含 TTS。
采集最多默认 30 秒，达到上限后的截断录音只保存供检查，不执行操作。
--min-word-confidence 0.45 是未标定的初始筛查值，不是准确率保证。
模型效果须以用户独立录音验证；本文件不自行下载模型或上传录音。
Vosk API 参考：https://github.com/alphacep/vosk-api/tree/master/python/example
"""

import argparse
from datetime import datetime
from math import gcd
from pathlib import Path
import json
import time
from uuid import uuid4

import numpy as np

try:
    from scipy.io import wavfile
    from scipy.signal import resample_poly
except ImportError:
    wavfile = None
    resample_poly = None

import board_audio
import board_mic
import main as core
from text_cli import TextApplication, parse_command, describe_record


ROOT = Path(__file__).resolve().parent
AUDIO_DIR = ROOT / "data" / "audio" / "asr_tests"
LOG_DIR = ROOT / "data" / "asr_logs"
RATE = 16000
VERSION = "vosk_domain_v1"
READBACK_INTENTS = {"record_device", "record_manual", "annotate", "capture_image", "save_waveform"}
GRAMMAR_WORDS = [
    "读取", "数据", "记录", "保存", "连续", "每", "隔", "秒",
    "一次", "两次", "三次", "五次", "共", "当前", "电压", "电流",
    "伏", "安", "点", "零", "一", "二", "三", "四", "五", "六",
    "七", "八", "九", "十", "百", "千", "负", "上", "一条",
    "有", "问题", "撤销", "确认", "取消", "帮助", "退出",
    "拍", "拍摄", "拍照", "照片", "波形", "屏幕", "摄像头", "看",
    "状态", "存", "留下", "[unk]",
]
GRAMMAR_JSON = json.dumps(GRAMMAR_WORDS, ensure_ascii=False)
CONFIRM_GRAMMAR_WORDS = [
    "可以", "不", "行", "不行", "好", "好的", "是", "的",
    "不是", "对", "不对", "确认", "取消", "重说", "再", "说", "一遍",
    "错误", "没问题", "[unk]",
]
CONFIRM_GRAMMAR_JSON = json.dumps(CONFIRM_GRAMMAR_WORDS, ensure_ascii=False)


def prepare_audio(audio, sample_rate, max_seconds):
    audio = np.asarray(audio)
    if not audio.size or sample_rate <= 0:
        raise ValueError("音频为空或采样率无效。")
    if audio.dtype.kind in "iu":
        if audio.dtype.kind == "u":
            middle = (np.iinfo(audio.dtype).max + 1) / 2
            audio = (audio.astype(np.float64) - middle) / middle
        else:
            audio = audio.astype(np.float64) / float(-int(np.iinfo(audio.dtype).min))
    else:
        audio = audio.astype(np.float64)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if audio.ndim != 1 or not np.all(np.isfinite(audio)):
        raise ValueError("音频格式或数值无效。")
    if len(audio) / sample_rate > max_seconds + 0.01:
        raise ValueError(f"录音超过 {max_seconds:g} 秒，请分成独立指令。")
    if sample_rate != RATE:
        if resample_poly is not None:
            factor = gcd(int(sample_rate), RATE)
            audio = resample_poly(audio, RATE // factor, int(sample_rate) // factor)
        else:
            audio = board_audio.resample_linear(audio, int(sample_rate), RATE)
    return audio.astype(np.float32)


def capture(device_id, max_seconds, audio_device=None):
    try:
        import sounddevice as sd
    except ImportError:
        sd = None

    if sd is None:
        return board_mic.capture_16k_mono(
            max_seconds,
            device=audio_device or board_mic.DEFAULT_CAPTURE_DEVICE,
        )

    device = sd.query_devices(device_id, "input")
    if "立体声混音" in device["name"] or "stereo mix" in device["name"].lower():
        raise ValueError("输入设备是立体声混音，请改用麦克风编号。")
    native_rate = int(device["default_samplerate"])
    sd.check_input_settings(device=device_id, channels=1, dtype="float32", samplerate=native_rate)
    chunks, errors = [], []
    count, maximum, truncated = 0, int(max_seconds * native_rate), False

    def callback(indata, frames, timing, status):
        nonlocal count, truncated
        if status:
            errors.append(str(status))
        take = min(frames, maximum - count)
        if take:
            chunks.append(indata[:take, 0].copy())
            count += take
        if count >= maximum:
            truncated = True
            raise sd.CallbackStop

    print(f"麦克风：{device['name']}；采样率：{native_rate} Hz")
    recorded_at = core.now_iso()
    with sd.InputStream(device=device_id, channels=1, dtype="float32", samplerate=native_rate,
                        blocksize=int(native_rate * 0.05), callback=callback):
        answer = input(f"正在录音：请说完整句子，说完按回车停止（上限 {max_seconds:g} 秒）：")
    if answer.strip().lower() == "q":
        return None
    if not chunks:
        raise ValueError("没有采集到音频，请稍等麦克风启动后再说话。")
    audio = prepare_audio(np.concatenate(chunks), native_rate, max_seconds)
    return audio, {"recorded_at": recorded_at, "native_rate": native_rate,
                   "device_name": device["name"], "truncated": truncated, "capture_errors": errors}


def save_audio(audio):
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = AUDIO_DIR / f"asr_{stamp}_{uuid4().hex[:8]}.wav"
    if wavfile is not None:
        wavfile.write(path, RATE, (np.clip(audio, -1, 1) * 32767).round().astype(np.int16))
    else:
        board_audio.write_wav_16k(path, audio, RATE)
    return path


def read_audio_file(path, max_seconds):
    if wavfile is not None:
        sample_rate, audio = wavfile.read(path)
    else:
        sample_rate, audio = board_audio.read_wav_mono(path)
    return prepare_audio(audio, sample_rate, max_seconds)


def audio_problem(audio):
    if len(audio) < RATE * 0.25:
        return "录音过短，请说完再停止。"
    if float(np.mean(np.abs(audio) >= 0.995)) > 0.005:
        return "录音明显削波，请降低增益或离麦克风稍远。"
    centered = audio - float(np.mean(audio))
    blocks = centered[:len(centered) // 320 * 320].reshape(-1, 320)
    energy = np.sqrt(np.mean(blocks ** 2, axis=1))
    if float(np.max(np.abs(centered))) < 0.003 or np.count_nonzero(energy > 0.003) < 4:
        return "未检测到足够的声音；没有执行操作。"
    return None


def transcribe(audio, model, on_partial=None, grammar=None):
    from asr_backend import KaldiRecognizer

    if grammar:
        recognizer = KaldiRecognizer(model, RATE, grammar)
    else:
        recognizer = KaldiRecognizer(model, RATE)
    recognizer.SetWords(True)
    pcm = (np.clip(audio, -1, 1) * 32767).round().astype("<i2").tobytes()
    segments = []
    for offset in range(0, len(pcm), 8000):
        if recognizer.AcceptWaveform(pcm[offset:offset + 8000]):
            segments.append(json.loads(recognizer.Result()))
        elif on_partial is not None:
            partial = json.loads(recognizer.PartialResult()).get("partial", "").strip()
            if partial:
                on_partial(partial)
    segments.append(json.loads(recognizer.FinalResult()))
    # 自然停顿可能产生多个段，必须合并整句，不能只使用最后一段。
    transcript = " ".join(part.get("text", "").strip() for part in segments if part.get("text", "").strip())
    words = [word for part in segments for word in part.get("result", [])]
    return {"text": transcript, "segments": segments, "words": words}


def _evaluate_transcript(text, words, minimum_confidence):
    text = (text or "").strip()
    if not text:
        return None, None, "没有识别出文字，请重说。"
    confidences = [float(word["conf"]) for word in words if "conf" in word]
    minimum = min(confidences) if confidences else None
    if confidences and minimum < minimum_confidence:
        return None, minimum, "部分词的识别分数较低，本次不执行，请核对显示文字并重说。"
    try:
        return parse_command(text), minimum, None
    except ValueError as error:
        return None, minimum, str(error)


def analyze(audio, model, metadata, minimum_confidence, on_partial=None, grammar=None,
            command_grammar=False):
    result = {"text": "", "words": [], "segments": [], "command": None, "reason": None,
              "duration_seconds": round(len(audio) / RATE, 3)}
    if metadata.get("truncated"):
        result["reason"] = "录音达到长度上限，句子可能不完整，请缩短后重说。"
        return result
    if metadata.get("capture_errors"):
        result["reason"] = "音频采集有丢帧等异常，请重新录制：" + "; ".join(metadata["capture_errors"])
        return result
    problem = audio_problem(audio)
    if problem:
        result["reason"] = problem
        return result
    started = time.perf_counter()
    if command_grammar:
        if not grammar:
            raise ValueError("命令词表模式需要提供词表。")
        transcript = transcribe(audio, model, on_partial=on_partial, grammar=grammar)
        result.update(transcript)
        command, minimum, reason = _evaluate_transcript(
            transcript["text"], transcript["words"], minimum_confidence)
        result.update(command=command, min_word_confidence=minimum, reason=reason,
                      recognizer_mode="command_grammar")
        result["recognition_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return result
    baseline = transcribe(audio, model, on_partial=on_partial)
    result.update(baseline)
    result["text_baseline"] = baseline["text"]
    result["words_baseline"] = baseline["words"]
    result["segments_baseline"] = baseline["segments"]
    command, minimum, reason = _evaluate_transcript(
        baseline["text"], baseline["words"], minimum_confidence)
    result["min_word_confidence"] = minimum

    if command is not None:
        result["command"] = command
        result["reason"] = None
        result["recognizer_mode"] = "baseline"
    elif grammar:
        grammar_result = transcribe(audio, model, grammar=grammar)
        grammar_command, grammar_minimum, grammar_reason = _evaluate_transcript(
            grammar_result["text"], grammar_result["words"], minimum_confidence)
        result["text_grammar"] = grammar_result["text"]
        result["words_grammar"] = grammar_result["words"]
        result["segments_grammar"] = grammar_result["segments"]
        result["min_word_confidence_grammar"] = grammar_minimum
        if grammar_command is not None:
            result.update(grammar_result)
            result["min_word_confidence"] = grammar_minimum
            result["command"] = grammar_command
            result["reason"] = None
            result["recognizer_mode"] = "grammar_fallback"
        else:
            result["reason"] = reason or grammar_reason
            result["recognizer_mode"] = "baseline"
    else:
        result["reason"] = reason
        result["recognizer_mode"] = "baseline"
    result["recognition_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return result


def command_description(command):
    intent = command["intent"]
    if intent == "record_manual":
        return "人工报数：" + describe_record({"record_kind": "manual", **command})
    if intent == "record_device":
        return f"从仪表采集并记录 {command['count']} 次，间隔 {command['interval']:g} 秒"
    if intent == "annotate":
        return "将上一条记录标记异常" if command["status"] == "abnormal" else "将上一条记录作废"
    if intent == "capture_image":
        return "调用摄像头拍摄当前屏幕或波形"
    if intent == "save_waveform":
        return "保存当前波形"
    if intent == "status":
        return "查看当前状态"
    return {"read": "读取仪表数据，不保存", "last": "查看最近记录", "help": "显示帮助",
            "exit": "退出程序", "confirm": "确认待核对操作", "cancel": "取消待核对操作",
            "stop": "停止记录"}[intent]


def semantic_key(command):
    if command is None:
        return None
    result = {**command}
    if result["intent"] == "record_manual":
        result["measurements"] = sorted(
            ({key: item[key] for key in ("quantity", "value", "unit")} for item in result["measurements"]),
            key=lambda item: item["quantity"])
    return result


def label_test(result):
    print("可选：输入刚才实际说的完整句子作统计；非指令填 unknown；回车跳过。")
    while True:
        expected = input("实际内容：").strip()
        if not expected:
            return
        if expected.lower() == "unknown":
            expected_command = None
        else:
            try:
                expected_command = parse_command(expected)
            except ValueError as error:
                print(f"标签句子还不在支持范围内：{error} 可直接回车跳过。")
                continue
        result["expected_text"] = expected
        result["expected_command"] = expected_command
        result["semantic_correct"] = semantic_key(result["command"]) == semantic_key(expected_command)
        print("[核对一致]" if result["semantic_correct"] else "[核对不一致] 已记录这次问题。")
        return


def process(audio, audio_path, metadata, model, args, application=None, ask_label=True, on_partial=None):
    command_grammar = getattr(args, "command_grammar", False)
    grammar = GRAMMAR_JSON if command_grammar or getattr(args, "grammar_fallback", True) else None
    result = analyze(audio, model, metadata, args.min_word_confidence,
                     on_partial=on_partial, grammar=grammar,
                     command_grammar=command_grammar)
    result.update({"mode": args.mode, "audio_path": str(audio_path.resolve()), "metadata": metadata,
                   "created_at": core.now_iso(), "model_path": str(args.model.resolve()),
                   "minimum_word_confidence": args.min_word_confidence,
                   "pipeline_version": VERSION, "sample_rate": RATE})
    print("[识别文字] " + (result["text"].replace(" ", "") or "（空）"))
    if result.get("recognizer_mode") == "grammar_fallback":
        print("[词表回退] 通用识别未形成命令，领域词表识别成功。")
    if result["command"] is not None:
        print("[理解结果] " + command_description(result["command"]))
    else:
        print("[未执行] " + result["reason"])
    if "recognition_ms" in result:
        print(f"识别计算耗时：{result['recognition_ms']:.0f} ms（不含录音与模型加载）")
    if args.mode == "test" and ask_label:
        label_test(result)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{audio_path.stem}_{uuid4().hex[:8]}.json"
    result["dispatch_state"] = "not_dispatched"
    core.write_json_atomically(log_path, result)
    exit_requested = False
    pre_confirmed = False
    if (args.mode == "run" and application is not None and result["command"] is not None
            and result["command"].get("intent") in READBACK_INTENTS
            and getattr(args, "confirm_readback", False)):
        readback_text = result["text"].replace(" ", "")
        print("[语音回读] " + readback_text)
        try:
            from readback import speak_text
            if not speak_text(readback_text):
                print("[回读提示] 当前没有可用 TTS，请查看屏幕文字。")
        except Exception as error:
            print(f"[回读失败] {error}")
        print("[等待确认] 请说：可以/好的/是的/确认/行；否定说：不行/不可以/不是/取消/重说。")
        confirmed = False
        for _ in range(2):
            second = capture(args.device, getattr(args, "confirm_seconds", args.max_seconds),
                             args.audio_device)
            if second is None:
                result["reason"] = "回读确认取消，本次未执行。"
                result["dispatch_state"] = "readback_cancelled"
                core.write_json_atomically(log_path, result)
                print("[已取消] 未执行。")
                return result, False
            second_audio, second_metadata = second
            second_path = save_audio(second_audio)
            second_result = analyze(second_audio, model, second_metadata,
                                    args.min_word_confidence, grammar=CONFIRM_GRAMMAR_JSON,
                                    command_grammar=command_grammar)
            confirm_text = (second_result.get("text") or "").replace(" ", "")
            result["confirm_readback_text"] = second_result.get("text")
            result["confirm_readback_audio_path"] = str(second_path)
            try:
                confirm_command = parse_command(confirm_text)
            except ValueError:
                confirm_command = None
            if confirm_command is not None and confirm_command.get("intent") == "confirm":
                confirmed = True
                break
            if confirm_command is not None and confirm_command.get("intent") == "cancel":
                result["reason"] = "用户未确认，本次未执行。"
                result["dispatch_state"] = "readback_rejected"
                core.write_json_atomically(log_path, result)
                print("[已取消] 没有执行。")
                return result, False
            print("[确认未识别] 请再说“可以”或“不行”。")
        if not confirmed:
            result["reason"] = "回读确认未通过，本次未执行。"
            result["dispatch_state"] = "readback_not_confirmed"
            core.write_json_atomically(log_path, result)
            print("[未执行] 没有收到有效确认。")
            return result, False
        print("[确认通过] 开始执行。")
        pre_confirmed = True
    elif (args.mode == "run" and application is not None and result["command"] is not None
            and result["command"].get("intent") in READBACK_INTENTS
            and getattr(args, "confirm_repeat", False)):
        print("[二次确认] 请用同样的话再说一遍，两遍一致才会执行。")
        second = capture(args.device, args.max_seconds, args.audio_device)
        if second is None:
            result["confirm_repeat_match"] = False
            result["reason"] = "二次确认取消，本次未执行。"
            result["dispatch_state"] = "confirmation_cancelled"
            core.write_json_atomically(log_path, result)
            print("[二次确认取消] 未执行。")
            return result, False
        second_audio, second_metadata = second
        second_path = save_audio(second_audio)
        second_result = analyze(second_audio, model, second_metadata,
                                args.min_word_confidence, grammar=grammar,
                                command_grammar=command_grammar)
        result["confirm_repeat_text"] = second_result.get("text")
        result["confirm_repeat_command"] = second_result.get("command")
        result["confirm_repeat_audio_path"] = str(second_path)
        match = semantic_key(result["command"]) == semantic_key(second_result.get("command"))
        result["confirm_repeat_match"] = match
        if not match:
            result["reason"] = "二次确认不一致，本次未执行。"
            result["dispatch_state"] = "confirmation_mismatch"
            core.write_json_atomically(log_path, result)
            print("[二次确认失败] 两遍识别结果不一致，未执行。")
            return result, False
        print("[二次确认通过] 两遍识别结果一致。")
        pre_confirmed = True
    if args.mode == "run" and application is not None and result["command"] is not None:
        context = {"source": "voice", "audio_path": str(audio_path.resolve()),
                   "asr_text": result["text"], "asr_log": str(log_path),
                   "recorded_at": metadata.get("recorded_at"), "model_path": str(args.model.resolve()),
                   "pre_confirmed": pre_confirmed}
        try:
            # 部分应用操作会进入待确认状态；交给统一应用维护，不能绕过。
            exit_requested = application.handle_text(result["text"], input_context=context)
            result["dispatch_state"] = "delivered_to_application"
        except (ValueError, TypeError, OSError, KeyError) as error:
            result["dispatch_state"] = "application_error"
            result["application_error"] = str(error)
            print(f"[应用未完成] {error}")
        try:
            core.write_json_atomically(log_path, result)
        except OSError as error:
            print(f"[日志更新失败] {error}；操作已经交给应用，请先查看记录，勿直接重复提交。")
    print(f"录音：{audio_path}\n日志：{log_path}")
    return result, exit_requested


def main():
    parser = argparse.ArgumentParser(description="LabMate：离线中文语音识别与应用")
    parser.add_argument("mode", nargs="?", default="test", choices=("test", "run", "file"))
    parser.add_argument("--model", type=Path, default=ROOT / "models" / "vosk-model-small-cn-0.22")
    parser.add_argument("--device", type=int, default=2)
    parser.add_argument("--audio-device", default=board_mic.DEFAULT_CAPTURE_DEVICE)
    parser.add_argument("--max-seconds", type=float, default=30)
    parser.add_argument("--confirm-seconds", type=float, default=3.0)
    parser.add_argument("--min-word-confidence", type=float, default=0.45)
    parser.add_argument("--command-grammar", action="store_true",
                        help="只使用项目命令词表识别，保留置信度和确认检查")
    parser.add_argument("--no-grammar-fallback", action="store_false",
                        dest="grammar_fallback", default=True)
    parser.add_argument("--speak-events", action="store_true",
                        help="PC 端识别成功/失败时播放蜂鸣反馈")
    parser.add_argument("--confirm-repeat", action="store_true",
                        help="run 模式下同一条命令说两遍，一致才执行")
    parser.add_argument("--confirm-readback", action="store_true",
                        help="run 模式下回读识别文字，只说可以/确认后执行")
    parser.add_argument("--wav", type=Path)
    args = parser.parse_args()
    if not 1 <= args.max_seconds <= 60 or not 1 <= args.confirm_seconds <= 60 or not 0 <= args.min_word_confidence <= 1:
        parser.error("max-seconds/confirm-seconds 范围为 1—60；min-word-confidence 范围为 0—1。")
    if args.mode == "file" and args.wav is None:
        parser.error("file 模式需要 --wav 路径。")
    if not (args.model / "am" / "final.mdl").is_file():
        print(f"找不到完整模型：{args.model}")
        print("请解压官方中文模型；该文件夹下应直接存在 am、conf、graph 等目录。")
        print("模型下载：https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip")
        return
    try:
        from asr_backend import Model, SetLogLevel
        SetLogLevel(-1)
        print("正在加载离线中文模型；仅本地处理音频……", flush=True)
        model = Model(str(args.model))
        print("模型已加载。识别分数只是筛查值，不代表数字一定正确。")
        if args.mode == "file":
            audio = read_audio_file(args.wav, args.max_seconds)
            process(audio, args.wav, {}, model, args, ask_label=False)
            return
        app = TextApplication(confirm_batches=True) if args.mode == "run" else None
        if app is not None:
            def action_handler(action, command, input_context):
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                request = {"action": action, "command": command, "input_context": input_context,
                           "created_at": core.now_iso()}
                path = ROOT / "data" / "requests" / f"{action}_{stamp}.json"
                core.write_json_atomically(path, request)
                print(f"[动作请求] {path}")
            app.set_action_handler(action_handler)
        if app is None:
            print("test：只识别和解析；不会保存实验记录、标记异常或执行退出口令。")
        else:
            print("run：会执行操作；仪表仍为 mock。报数、批量次数与异常标记先核对。")
            print("待核对时可再录音说“确认/取消”，或在下面键入 /确认、/取消。")
            print("批次执行时用 Ctrl+C 中止；批次期间未监听麦克风。反馈仅显示在终端。")
        labeled = correct = 0
        while True:
            answer = input("\n按回车开始录音，q 退出" + ("，/命令 使用键盘" if app else "") + "：").strip()
            if answer.lower() == "q":
                break
            if app and answer.startswith("/"):
                try:
                    if app.handle_text(answer[1:]):
                        break
                except (ValueError, TypeError, OSError, KeyError) as error:
                    print(f"[未完成] {error}")
                continue
            if answer:
                print("请按回车录音，或输入 q 退出。")
                continue
            try:
                captured = capture(args.device, args.max_seconds, args.audio_device)
                if captured is None:
                    break
                audio, metadata = captured
                path = save_audio(audio)
                result, exit_requested = process(audio, path, metadata, model, args, app)
                if args.speak_events:
                    from pc_speaker import play_result
                    play_result(result)
                if "semantic_correct" in result:
                    labeled += 1
                    correct += int(result["semantic_correct"])
                    print(f"[本轮已标注样本] 理解一致 {correct}/{labeled}；这不是总体准确率。")
                if exit_requested:
                    break
            except (ValueError, TypeError, OSError, RuntimeError) as error:
                print(f"[本次未完成] {error}")
    except (EOFError, KeyboardInterrupt):
        print("\n已退出；未确认的操作不会保存。")
    except ImportError as error:
        print(f"缺少依赖：{error}")
        print("可安装官方 ARMv7 wheel，或使用项目内的 vosk_lite 兜底。")
    except Exception as error:
        print(f"[启动或识别失败] {type(error).__name__}: {error}")


if __name__ == "__main__":
    main()
