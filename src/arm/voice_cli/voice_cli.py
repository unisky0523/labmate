r"""LabMate B：PC 固定指令语音原型，MFCC + DTW。

安装：.\.venv\Scripts\python.exe -m pip install scipy
制作模板：.\.venv\Scripts\python.exe voice_cli.py train
仅识别：.\.venv\Scripts\python.exe voice_cli.py test
接应用：.\.venv\Scripts\python.exe voice_cli.py run
识别旧文件：.\.venv\Scripts\python.exe voice_cli.py file --wav 路径

放在 main.py 旁边。默认麦克风编号为已验证的 2，可用 --device 修改。
train 模式中各录三次；test/run 中每按一次回车录一次，q 退出。
第一版只支持 read/record，以本人、小词表、安静环境为开发边界。
匹配距离不是概率；阈值未经过真实独立录音标定，不宣称识别准确率。
run 复用 main.execute_command，当前应用中的仪表读数仍为模拟数据。
"""

import argparse
from datetime import datetime
from math import gcd
from pathlib import Path
import json
import time
from uuid import uuid4

import numpy as np
from scipy.fft import dct
from scipy.io import wavfile
from scipy.signal import resample_poly


ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "data" / "audio" / "templates"
TEST_AUDIO = ROOT / "data" / "audio" / "voice_tests"
LOGS = ROOT / "data" / "voice_logs"
COMMANDS = {
    "read": "读取数据",
    "record": "记录数据",
    "capture_image": "拍一下波形",
    "save_waveform": "保存波形",
    "status": "当前状态",
    "confirm_yes": "可以",
    "confirm_no": "不行",
}
TARGET_RATE = 16000
# 这两项只是起始值，必须用独立指令和非指令样本验证、调整。
MAX_DISTANCE = 1.20
MIN_MARGIN = 0.08
PIPELINE_VERSION = "mfcc_dtw_v1"


def prepare_audio(audio, sample_rate):
    """转单声道，并实际重采样，绝不只修改 WAV 文件头。"""
    audio = np.asarray(audio)
    if audio.size == 0:
        raise ValueError("录音为空。")
    if audio.dtype.kind in "iu":
        if audio.dtype.kind == "u":
            midpoint = (np.iinfo(audio.dtype).max + 1) / 2
            audio = (audio.astype(np.float64) - midpoint) / midpoint
        else:
            scale = float(-int(np.iinfo(audio.dtype).min))
            audio = audio.astype(np.float64) / scale
    else:
        audio = audio.astype(np.float64)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if audio.ndim != 1 or sample_rate <= 0:
        raise ValueError("音频维度或采样率无效。")
    if not np.all(np.isfinite(audio)):
        raise ValueError("音频含无效数值。")
    if len(audio) / sample_rate > 10:
        raise ValueError("请使用不超过十秒的单条指令录音。")
    if sample_rate != TARGET_RATE:
        factor = gcd(int(sample_rate), TARGET_RATE)
        audio = resample_poly(audio, TARGET_RATE // factor, int(sample_rate) // factor)
    return audio.astype(np.float32)


def capture_audio(device_id, seconds):
    """用已经验证的麦克风采集。仅在真正录音时导入驱动库。"""
    import sounddevice as sd

    device = sd.query_devices(device_id, kind="input")
    name = device["name"]
    if "立体声混音" in name or "stereo mix" in name.lower():
        raise ValueError("选中了立体声混音，请改用麦克风编号。")
    native_rate = int(device["default_samplerate"])
    print(f"麦克风：{name}；采样率：{native_rate} Hz")
    sd.check_input_settings(device=device_id, channels=1,
                            dtype="float32", samplerate=native_rate)
    print(f"开始录音，持续 {seconds:g} 秒，请只说一条指令……", flush=True)
    audio = sd.rec(int(seconds * native_rate), samplerate=native_rate,
                   channels=1, dtype="float32", device=device_id)
    sd.wait()
    status = sd.get_status()
    if status:
        raise ValueError(f"采集异常：{status}；请重新录制。")
    print("录音完成。")
    return prepare_audio(audio, native_rate)


def save_wav(directory, audio):
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = directory / f"voice_{stamp}_{uuid4().hex[:8]}.wav"
    pcm = (np.clip(audio, -1, 1) * 32767).round().astype(np.int16)
    wavfile.write(path, TARGET_RATE, pcm)
    return path


def load_wav(path):
    sample_rate, audio = wavfile.read(path)
    return prepare_audio(audio, sample_rate)


def frame_audio(audio, frame_length, hop):
    if len(audio) < frame_length:
        audio = np.pad(audio, (0, frame_length - len(audio)))
    count = 1 + (len(audio) - frame_length) // hop
    indices = np.arange(frame_length)[None, :] + hop * np.arange(count)[:, None]
    return audio[indices]


def trim_speech(audio):
    """基于帧能量的简单端点检测，不是通用语音/噪声分类器。"""
    audio = audio.astype(np.float64) - float(np.mean(audio))
    if np.max(np.abs(audio)) < 0.003:
        raise ValueError("声音太小或没有说话；请检查输入设备。")
    frames = frame_audio(audio, 320, 160)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    threshold = max(0.003, float(rms.max()) * 0.12,
                    float(np.percentile(rms, 20)) * 2.5)
    active = np.flatnonzero(rms >= threshold)
    if len(active) < 8:
        raise ValueError("未检测到足够的人声，请在提示后说完整指令。")
    start = max(0, int(active[0]) * 160 - 800)
    end = min(len(audio), int(active[-1]) * 160 + 320 + 800)
    speech = audio[start:end]
    if len(speech) < int(0.20 * TARGET_RATE):
        raise ValueError("声音片段太短，请重新录制。")
    # 归一化只用于特征提取；保存的录音仍保留原始输入音量。
    return speech / max(float(np.max(np.abs(speech))), 1e-8)


def mel_filterbank():
    low = 2595 * np.log10(1 + 80 / 700)
    high = 2595 * np.log10(1 + 7600 / 700)
    frequencies = 700 * (10 ** (np.linspace(low, high, 28) / 2595) - 1)
    fft_frequencies = np.fft.rfftfreq(512, 1 / TARGET_RATE)
    filters = np.zeros((26, len(fft_frequencies)))
    for k in range(26):
        left, center, right = frequencies[k:k + 3]
        rising = (fft_frequencies - left) / (center - left)
        falling = (right - fft_frequencies) / (right - center)
        filters[k] = np.maximum(0, np.minimum(rising, falling))
    return filters


MEL_BANK = mel_filterbank()


def extract_features(audio):
    """25 ms 分帧、10 ms 步长、26 个 Mel 滤波器和 12 个 MFCC。"""
    speech = trim_speech(audio)
    emphasized = np.append(speech[0], speech[1:] - 0.97 * speech[:-1])
    frames = frame_audio(emphasized, 400, 160) * np.hamming(400)
    power = np.abs(np.fft.rfft(frames, n=512, axis=1)) ** 2 / 512
    log_mel = np.log(np.maximum(power @ MEL_BANK.T, 1e-10))
    features = dct(log_mel, type=2, norm="ortho", axis=1)[:, 1:13]
    features -= features.mean(axis=0, keepdims=True)
    features /= np.maximum(features.std(axis=0, keepdims=True), 1.0)
    return features.astype(np.float32)


def dtw_distance(a, b):
    """按实际路径长度归一化的 DTW 距离，越小表示模板越接近。"""
    if len(a) == 0 or len(b) == 0:
        raise ValueError("特征序列为空。")
    costs = np.sqrt(np.mean((a[:, None, :] - b[None, :, :]) ** 2, axis=2))
    n, m = costs.shape
    previous = np.full(m + 1, np.inf)
    previous[0] = 0
    previous_steps = np.zeros(m + 1, dtype=np.int32)
    for i in range(1, n + 1):
        current = np.full(m + 1, np.inf)
        current_steps = np.zeros(m + 1, dtype=np.int32)
        for j in range(1, m + 1):
            if abs(i / n - j / m) > 0.35:
                continue
            options = (previous[j - 1], previous[j], current[j - 1])
            chosen = int(np.argmin(options))
            if not np.isfinite(options[chosen]):
                continue
            steps = (previous_steps[j - 1], previous_steps[j], current_steps[j - 1])
            current[j] = options[chosen] + costs[i - 1, j - 1]
            current_steps[j] = steps[chosen] + 1
        previous, previous_steps = current, current_steps
    return float(previous[m] / max(int(previous_steps[m]), 1))


def load_templates():
    groups = {}
    for command_id in COMMANDS:
        paths = sorted((TEMPLATES / command_id).glob("*.wav"))
        if len(paths) < 3:
            raise ValueError(f"{command_id} 模板不足三条，请先运行 train。")
        groups[command_id] = [extract_features(load_wav(path)) for path in paths]
    return groups


def recognize(audio, templates, max_distance, min_margin):
    started = time.perf_counter()
    result = {"command_id": None, "reason": None, "scores": {},
              "max_distance": max_distance, "min_margin": min_margin}
    try:
        features = extract_features(audio)
        for command_id, group in templates.items():
            distances = sorted(dtw_distance(features, template) for template in group)
            # 使用距离最近的两个模板，减少单条异常模板的影响。
            result["scores"][command_id] = float(np.mean(distances[:2]))
        ordered = sorted(result["scores"].items(), key=lambda item: item[1])
        best_id, best_distance = ordered[0]
        second_distance = ordered[1][1]
        margin = second_distance - best_distance
        result["margin"] = margin
        if not np.isfinite(best_distance) or best_distance > max_distance:
            result["reason"] = "离已有模板较远，拒绝识别。"
        elif margin < min_margin:
            result["reason"] = "两个候选过于接近，拒绝识别。"
        else:
            result["command_id"] = best_id
            result["reason"] = "通过当前距离与差距阈值。"
    except ValueError as error:
        result["reason"] = str(error)
    result["inference_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return result


def display_result(result):
    for command_id, distance in sorted(result["scores"].items(), key=lambda item: item[1]):
        print(f"  {command_id:6s}（{COMMANDS[command_id]}）匹配距离：{distance:.3f}")
    if result["command_id"]:
        command_id = result["command_id"]
        print(f"[识别] {COMMANDS[command_id]} → {command_id}")
    else:
        print(f"[未识别] {result['reason']}")
    print(f"特征与匹配耗时：{result['inference_ms']:.2f} ms")


def log_result(result, audio_path, mode):
    LOGS.mkdir(parents=True, exist_ok=True)
    # JSON 不允许 inf；不可能对齐的距离用 null 表示。
    clean = {**result, "scores": {key: value if np.isfinite(value) else None
                                  for key, value in result["scores"].items()}}
    if "margin" in clean and not np.isfinite(clean["margin"]):
        clean["margin"] = None
    clean.update({"audio_path": str(audio_path), "mode": mode,
                  "created_at": datetime.now().astimezone().isoformat(),
                  "sample_rate": TARGET_RATE, "pipeline_version": PIPELINE_VERSION})
    path = LOGS / f"{audio_path.stem}_{uuid4().hex[:8]}.json"
    with path.open("x", encoding="utf-8") as file:
        json.dump(clean, file, ensure_ascii=False, indent=2, allow_nan=False)


def train(args):
    print("每条指令录三次，尽量自然说话，每次只说完整指令一次。")
    print("按回车立即开始录音，输入 q 可退出；多次 train 会追加模板。")
    for command_id, phrase in COMMANDS.items():
        for number in range(1, args.samples + 1):
            while True:
                answer = input(f"\n{phrase} [{number}/{args.samples}]，准备好后按回车：")
                if answer.strip().lower() == "q":
                    return
                try:
                    audio = capture_audio(args.device, args.seconds)
                    features = extract_features(audio)
                    path = save_wav(TEMPLATES / command_id, audio)
                    print(f"[模板已保存] {path}；有效特征帧：{len(features)}")
                    break
                except (ValueError, OSError, RuntimeError) as error:
                    print(f"[录制失败] {error}；本次未保存为模板，请重录。")
    print("\n模板已录制。下一步运行 voice_cli.py test，用新录音独立验证。")


def process_audio(audio, path, templates, args):
    result = recognize(audio, templates, args.threshold, args.margin)
    display_result(result)
    log_result(result, path, args.mode)
    if args.mode == "run" and result["command_id"]:
        from text_cli import TextApplication
        app = TextApplication()

        def action_handler(action, command, input_context):
            print(f"[动作] {action} -> {command}")

        app.set_action_handler(action_handler)
        print("调用应用；仪表读数当前仍是模拟数据。")
        app.handle_text(COMMANDS[result["command_id"]])
    return result


def main():
    parser = argparse.ArgumentParser(description="LabMate：两条固定指令的 PC 语音原型")
    parser.add_argument("mode", choices=("train", "test", "run", "file"))
    parser.add_argument("--device", type=int, default=2)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=MAX_DISTANCE)
    parser.add_argument("--margin", type=float, default=MIN_MARGIN)
    parser.add_argument("--wav", type=Path)
    args = parser.parse_args()
    if not (1 <= args.seconds <= 8 and args.samples >= 3):
        parser.error("--seconds 须为 1—8 秒，--samples 至少为 3。")
    if args.threshold <= 0 or args.margin < 0:
        parser.error("距离阈值须为正数，候选差距阈值不能为负数。")
    print("LabMate：固定指令模板匹配原型")
    print("距离阈值是初始值；先用 test 检查新录音和非指令的结果。")
    try:
        if args.mode == "train":
            train(args)
            return
        templates = load_templates()
        print("模板数量：", {key: len(value) for key, value in templates.items()})
        if args.mode == "file":
            if args.wav is None:
                parser.error("file 模式需要 --wav 文件路径。")
            process_audio(load_wav(args.wav), args.wav.resolve(), templates, args)
            return
        if args.mode == "test":
            print("本模式仅识别，不调用仪表应用。")
        else:
            # 启动时检查应用可导入，避免录完才发现文件位置错误。
            from main import execute_command
            print("本模式会调用 read/record；当前保存的是模拟仪表读数。")
        while True:
            answer = input("\n按回车录制新指令，输入 q 退出：")
            if answer.strip().lower() == "q":
                return
            try:
                audio = capture_audio(args.device, args.seconds)
                path = save_wav(TEST_AUDIO, audio)
                process_audio(audio, path, templates, args)
                print(f"测试录音：{path}")
            except (ValueError, OSError, RuntimeError) as error:
                print(f"[本次失败] {error}")
    except (EOFError, KeyboardInterrupt):
        print("\n已退出。")
    except (ValueError, OSError, RuntimeError, ImportError) as error:
        print(f"[错误] {error}")


if __name__ == "__main__":
    main()
