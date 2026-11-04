from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf


# 默认使用 Windows 当前麦克风。
# 如果需要指定设备，可以将 None 改成设备列表中的编号。
INPUT_DEVICE = 2
DURATION = 4  # 录音秒数


def main():
    device = sd.query_devices(INPUT_DEVICE, kind="input")
    sample_rate = int(device["default_samplerate"])

    print("麦克风：", device["name"])
    print("采样率：", sample_rate, "Hz")

    sd.check_input_settings(
        device=INPUT_DEVICE,
        channels=1,
        dtype="float32",
        samplerate=sample_rate,
    )

    input("\n按回车开始，然后说：记录数据")
    print("开始录音，持续四秒……")

    audio = sd.rec(
        frames=DURATION * sample_rate,
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        device=INPUT_DEVICE,
    )
    sd.wait()

    status = sd.get_status()
    if status:
        print("采集状态：", status)

    output_dir = Path(__file__).resolve().parent / "data" / "audio"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = datetime.now().strftime("mic_test_%Y%m%d_%H%M%S_%f.wav")
    output_file = output_dir / filename

    sf.write(output_file, audio, sample_rate, subtype="PCM_16")

    peak = float(np.max(np.abs(audio)))
    print("\n录音已保存：", output_file)
    print(f"音量峰值：{peak:.4f}")

    input("\n按回车回放录音")

    try:
        sd.play(audio, sample_rate)
        sd.wait()
        print("回放结束。")
    except sd.PortAudioError as error:
        print("回放失败：", error)
        print("录音文件已保存，可以用播放器打开检查。")


if __name__ == "__main__":
    main()