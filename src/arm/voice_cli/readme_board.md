# LabMate B 板端运行说明

目标系统：

```text
ATK-ZYNQ Linux 5.4
Python 3.7.6
ES8388 ALSA capture: hw:0,1, S24_LE, 44100 Hz, 2 channels
ES8388 ALSA playback: default
RGB LCD: /dev/fb0
OV5640: /dev/video0
```

## 1. 运行板端入口

```bash
cd /home/root/labmate_b_audio_test
PYTHONIOENCODING=utf-8 sh run_board.sh --source mock --seconds 5
```

以上路径于 2026-10-22 由用户在开发板上查询确认。其他板先查找 `board_app.py`，不要预设目录存在。
`run_board.sh` 会切换到实际应用目录，把 `lib/` 和应用根目录加入 `LD_LIBRARY_PATH`，并使用 UTF-8。

检查依赖与实际模型加载（不是麦克风测试）：

```bash
LD_LIBRARY_PATH="$PWD/lib:$PWD" PYTHONIOENCODING=utf-8 python3 board_check.py --load-model
```

正常应显示 `APPLICATION_IMPORTS OK`、`VOSK_MODEL OK vosk_lite` 和 `"dependency_check": "PASS"`。
先在 `LabMate[board]>` 输入“读取数据”“当前状态”“查看记录”，核对文字流程后再录音。
`--source mock` 的读数是模拟值，不是实际仪表测量。

板端可选命令词表模式（原通用识别模式仍为默认）：

```bash
PYTHONIOENCODING=utf-8 sh run_board.sh --source mock --seconds 5 --mic-channel 0 --command-grammar
```

2026-10-22 用户在板上用同一段“记录电压三点三伏”录音对比，通用识别 25.62 秒，命令词表识别 2.66 秒。这是单份录音的识别计算时间，不含录音、初始化和转换，不代表其他语句保证相同速度或准确率。
该模式直接识别项目词表，仍保留音频故障、置信度和解析检查，报数仍需确认；不支持任意中文听写。需要测试不同数字、单位、取消和无关语句。去掉 `--command-grammar` 可恢复原模式。

使用 C 提供的 JSON 读数文件：

```bash
sh run_board.sh --source json --reading-json data/from_c/reading.json
```

没有安装 Vosk 时：

```bash
sh run_board.sh --no-vosk
```

## 2. 操作

- 按一次回车开始录音。等待“现在开始说话，录音约 5 秒”后说话；定时结束，无需第二次回车。
- 录音前有约 4 秒的硬件启动和预热，预热部分不送入识别。
- 输入文字后再发单字节 `0D` 执行；触发录音时只发一次 `0D`。
- `--mic-channel 0` 默认选择左路；只有确认右路接麦克风时才改为 `--mic-channel 1`。
- 直接输入文字命令，例如：

```text
读取数据
记录电压三点三零伏，电流一点二安
查看记录
退出程序
```

- 输入 `q` 退出。

可用回读确认模式：

```bash
sh run_board.sh --confirm-readback
```

系统会显示并尝试播报识别文字。确认词包括：

```text
可以、好的、是的、确认、行、没问题
不行、不可以、不是、取消、重说
```

新增动作命令：

```text
拍一下波形 / 调用摄像头拍摄波形
保存波形
当前状态
```

## 3. 音频设备

录音走队友 A 验证过的 ES8388 capture：

```bash
aplay -D default -t raw -f S24_LE -r 44100 -c 2 -d 16 /dev/zero &
arecord -D hw:0,1 -t raw -f S24_LE -r 44100 -c 2 -d 10 /tmp/mic_rate_test.raw
i2cset -f -y 0 0x10 0x0a 0x00 b
i2cset -f -y 0 0x10 0x03 0x09 b
i2cset -f -y 0 0x10 0x0d 0x03 b
```

播放走 ES8388 playback。注意：下面的直接播放仅适用于标准 S24_LE 数据；该板原始录音必须先按下文转换，否则可能全是杂音：

```bash
aplay -D default -t raw -f S24_LE -r 44100 -c 2 /tmp/mic_rate_test.raw
```

`board_mic.py` 会自动执行这套静音保活、raw 录制、i2cset 和 16 kHz 单声道转换。
录音与静音播放使用 `-q`。普通格式提示保存在 `capture_warnings`，不进入 `capture_errors`；
非零退出、超时、I2C 失败、录音短缺、overrun、underrun 和其他异常诊断仍会阻止识别。
2026-10-22 最新同文件对照：R2、R3 两份原始双声道数据，左右声道均为标准 LE 读法能还原人声，强制 MSB 重排为杂音（RMS 约 0.61，接近满幅样本约 16%）。此前根据单次听感固定采用 MSB 的结论不成立，已撤回。
板端采集现显式使用 `little`，解码 4 字节容器内有符号低 24 位，选择一路，再转为 16 kHz。MSB 仅保留为历史数据诊断选项，不用于正式采集。LE 回听仍有用户报告的“鸭子音”，尚未确认音频链完全正常；回放小音量也受诊断脚本的主动衰减影响。
在音频流启动后，设置 `ALC Capture Function=Off`、`Left Channel=4`、`Right Channel=4`，复现用户已验证的人声录制条件。
电脑端单元测试通过不代表板端识别通过；更新后仍需实际说话验证 Vosk 输出。

板端录制的音频会保存到：

```text
data/audio/asr_tests/
```

## 4. 状态文件

现有 RGB LCD 界面可以轮询：

```text
data/state/latest_status.json
```

主要字段：

```text
state
asr_text
asr_partial
asr_command
asr_error
last_console_line
audio_path
updated_at
```

`board_ui.ConsoleTee` 会把应用打印输出同步写入该文件。

## 5. Vosk

默认模型路径：

```text
models/vosk-model-small-cn-0.22
```

模型目录应包含：

```text
am/final.mdl
conf/
graph/
```

如果 ARMv7 + Python 3.7 没有可用的 Vosk wheel，先用 `--no-vosk` 验证文本流程和音频采集。

项目内置两层后端选择：

1. `asr_backend.py` 优先导入官方 `vosk` 包。
2. 官方包缺失时，自动使用 `vosk_lite.py` + 项目根目录的 `libvosk.so`。

`libvosk.so` 来自官方 Vosk 0.3.45 的 `linux_armv7l` wheel。`vosk_lite` 不需要 `srt`、`tqdm`、`requests`、`websockets`，也不需要 cffi 的 Python 包。

包内同时包含：

```text
lib/libatomic.so.1
```

它只依赖板端已有的 `libc` 和 `libpthread`，不会覆盖系统目录。

如果 A 想使用官方 wheel，可离线安装到项目目录：

```bash
python3 -m pip install --no-deps --target third_party vosk-0.3.45-py3-none-linux_armv7l.whl
PYTHONPATH=/home/root/labmate_b/third_party python3 board_app.py
```

## 6. 当前边界

- `board_app.py` 不依赖 sounddevice。
- `asr_cli.py` 在板端缺少 scipy/sounddevice 时自动使用 arecord。
- `voice_cli.py` 仍是 PC 端 MFCC + DTW 原型，不在板端部署。
- 视觉读数由 `--source json` 或后续 `sources/vision.py` 接入。
- 现有界面框架需要读取 `latest_status.json` 才能显示识别文字。
- “拍一下波形”“保存波形”只写入 `data/requests/`，需要其他程序执行实际动作。
- Windows `.venv` 不属于板端运行环境，部署时排除。
- 本次板端检查发现系统时间仍在 2023 年，日志文件名采用该板时钟；验收时间以电脑端记录为准。
