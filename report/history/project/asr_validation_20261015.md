# LabMate B ASR 回归与交付说明

日期：2026-10-15

## 1. 目标环境

```text
开发板 Linux：ATK-ZYNQ 5.4.0-xilinx-v2020.2
架构：armv7l
Python：3.7.6
ES8388 录音：hw:0,1
录音格式：S24_LE, 44100 Hz, 2 channels
播放设备：default
```

## 2. ASR 版本

```text
Vosk Python API：0.3.45
中文模型：vosk-model-small-cn-0.22
模型大小：约 65.1 MB
```

官方 ARMv7 wheel 已确认存在：

```text
vosk-0.3.45-py3-none-linux_armv7l.whl
大小：2,388,263 bytes
下载来源：PyPI vosk 0.3.45 release
```

## 3. 板端运行策略

`asr_backend.py` 按顺序选择：

1. 官方 `vosk` Python 包。
2. 项目内 `vosk_lite.py` + `libvosk.so`。

`libvosk.so` 是从官方 ARMv7 wheel 中提取的 0.3.45 版本。

`vosk_lite.py` 只使用 Python 标准库 `ctypes`，不依赖：

```text
requests
tqdm
srt
websockets
cffi Python 包
```

因此板端即使没有网络、不能 pip 安装，也可以直接运行 ASR。

## 4. 录音路径匹配

`board_mic.py` 复现队友 A 验证过的顺序：

```bash
aplay -D default -t raw -f S24_LE -r 44100 -c 2 -d 16 /dev/zero &
arecord -D hw:0,1 -t raw -f S24_LE -r 44100 -c 2 -d 10 /tmp/mic_rate_test.raw
i2cset -f -y 0 0x10 0x0a 0x00 b
i2cset -f -y 0 0x10 0x03 0x09 b
i2cset -f -y 0 0x10 0x0d 0x03 b
```

Python 侧自动完成：

```text
启动静音 aplay 保持时钟
启动 arecord raw 录音
录音开始后写 ES8388 寄存器
读取 S24_LE raw PCM
转换为 16 kHz 单声道
```

## 5. ASR 识别策略

采用两阶段识别：

```text
第一遍：通用 Vosk 识别
    |
    +-- 如果命令解析成功：直接使用
    |
    +-- 如果失败：第二遍领域词表回退识别
             |
             +-- 如果命令解析成功：使用词表结果
             |
             +-- 如果仍失败：拒绝执行并提示重说
```

领域词表包括：

```text
读取、记录、保存、连续、每、隔、秒
一次、两次、三次、五次、共
当前、电压、电流、伏、安
数字、点、负、上、一条、问题
撤销、确认、取消、帮助、退出
```

## 6. 现有样本回归结果

测试集来自此前保存的 11 条 PC 录音，全部为 16 kHz 单声道。

```text
原通用识别命令解析：4/11
自研混合识别命令解析：9/11
剩余 1 条是 unknown 样本，被低置信度正确拒绝
剩余 1 条是困难人工报数样本，被拒绝并要求重说
```

重要说明：这是内部回归样本，不是独立准确率测试，不能对外宣称“准确率 82%”之类的总体指标。

## 7. 已覆盖的改进

- “帮我连续记录五次数据”可由词表回退解析。
- “每隔两秒记录一次，共三次”可由领域纠正解析。
- “上一条数据问题”可识别为异常标记。
- 人工报数缺单位时只做“推断 + 待确认”，不静默写入。
- 简单“读取数据”保持通用识别优先，不受词表干扰。

## 8. 仍需板端确认

1. `libvosk.so` 在 ATK-ZYNQ 上能否正常加载。
2. Vosk 模型加载时间和识别延迟。
3. 板载 ES8388 录制的 10 秒原始音频转换后的识别效果。
4. 内存峰值是否仍在 496 MB 以内。
5. 多说话人、实验室噪声和语速变化下的独立测试。

## 9. 交付给 A 的文件

```text
board_mic.py
board_audio.py
board_speaker.py
board_ui.py
board_sources.py
board_app.py
asr_cli.py
asr_backend.py
vosk_lite.py
libvosk.so
main.py
text_cli.py
models/vosk-model-small-cn-0.22/
```

官方 wheel 备份：

```text
dist/wheels/vosk-0.3.45-py3-none-linux_armv7l.whl
```
