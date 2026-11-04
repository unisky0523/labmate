# LabMate 板端增量改造说明

## 给修改代码的 AI

请在现有工程和现有界面框架上做增量修改，不要推倒重做，不要删除已有页面、菜单、驱动适配或记录逻辑。

目标：把 `D:\labmate_b` 的 PC 原型改成能在 ATK-ZYNQ 板端运行的 Python 3.7 应用，并在现有屏幕界面中加入“实验助手”页面。

必须遵守：

1. 保留现有 Linux、PL、RGB LCD、OV5640 和 ES8388 驱动。
2. 不引入 PYNQ Overlay。
3. 不重建 Ubuntu 或 PYNQ 系统。
4. 不删除或覆盖现有界面，只增加页面、面板、按钮和状态区域。
5. `main.py` 的统一记录写入继续作为唯一记录入口。
6. 记录 JSON 只能兼容扩展，不能破坏旧记录。
7. 代码必须兼容 Python 3.7.6。

## 已确认环境

```text
Linux ATK-ZYNQ 5.4.0-xilinx-v2020.2
armv7l
Python 3.7.6
pip 19.2.3
NumPy 1.17.0
内存约 496 MB，空闲约 442 MB
根文件系统约 7.1 GB，剩余约 6.1 GB
RGB LCD: /dev/fb0, /dev/dri/card0
音频播放: card 0, ES8388 playback
音频录音: card 0 device 1, ES8388 capture
摄像头: /dev/video0, OV5640, V4L2 multiplanar RGB3/BGR3
串口: USB Type-C + CH340, 115200 8N1
```

已知问题：

```text
DISPLAY 为空，现有界面应基于 framebuffer/DRM/EGLFS，而不是普通 X11 桌面。
import cv2 直接 Segmentation fault，当前不能依赖 OpenCV。
Vosk 未安装。
eth0/eth1 之前为 DOWN。
```

注意：`DISPLAY` 为空不代表没有显示。RGB LCD 已经工作，必须先找到现有界面的进程和源码，在原框架内增加“实验助手”页面。

## 现有代码盘点

### `main.py`

负责：

- 模拟仪表读数。
- 校验读数。
- 原子写 JSON 记录。
- 查询最近记录。
- 异常和作废批注。
- read/record 执行。

保留：

- `save_record()` 是唯一记录写入入口。
- 原子写文件和批注机制。
- 现有记录字段。

修改：

- `temporary_path.unlink(missing_ok=True)` 是 Python 3.8 特性，必须改成 `try/except FileNotFoundError`。
- 将 `get_reading()` 从 mock 改成可替换的数据源接口。
- 增加来源一致性字段和可选比较字段。
- 增加 UI 事件回调，不要只 `print()`。

### `text_cli.py`

负责：

- 中文命令和实验语句解析。
- 人工报数解析。
- read/record/批量/查询/异常/作废。
- `TextApplication` 状态机。

处理：

- 保留解析规则和业务语义，不要重写。
- 把 `print/input` 抽成可注入的 presenter 或 UI 回调。
- 无法完整理解时继续拒绝执行。

### `asr_cli.py`

负责：

- Vosk 离线中文识别。
- 交给 `text_cli.parse_command`。
- test/run/file 模式。
- ASR 日志和测试音频。

修改：

- 删除 `sounddevice` 直接依赖，改用 `board_audio`。
- Vosk 继续懒加载。
- 增加 partial/final 回调，供界面显示。
- 模型路径改为 `models/vosk-model-small-cn-0.22`。
- Vosk 缺失时界面显示错误，但主程序不能退出。

### `voice_cli.py`

这是 PC 端 MFCC + DTW 原型，依赖 `scipy` 和 `sounddevice`。

处理：

- 保留作为 PC 备用方案。
- 板端第一版不部署。
- 如果 Vosk 不可用，再评估移植。

### `record_test.py`

Windows 录音测试。

处理：

- 不部署到板端。
- 可移到 `tools/pc_prototype/`。

### `models/vosk-model-small-cn-0.22`

- 当前约 65.1 MB。
- 需要整体复制到板端。
- 必须存在 `am/final.mdl`。

## 目标架构

```text
现有厂商界面 / 菜单框架
        |
        +-- 新增页面：实验助手
                |
                +-- ui_bridge / page_adapter
                        +-- text_cli.TextApplication
                        +-- asr_service (Vosk)
                        +-- board_audio (arecord)
                        +-- board_speaker (aplay)
                        +-- sources (SCPI / vision / mock)
                        +-- main.save_record（唯一记录写入）
```

原则：

- 业务逻辑复用现有 `text_cli` 和 `main`。
- 板端硬件访问放到独立适配层。
- UI 只订阅状态，不直接做音频、Vosk、SCPI 或文件写入。
- 现有界面框架继续负责窗口、页面和触控。

## 新增模块

### `board_audio.py`

替代 `sounddevice`，使用 ALSA 录音。

建议接口：

```python
def capture_wav(seconds, path, device="plughw:0,1"):
    ...

def load_as_16k_mono(path):
    ...
```

策略：

1. 优先使用 48000 Hz、S16_LE、2 声道。
2. 混合为单声道。
3. 重采样到 16000 Hz。
4. 失败返回明确错误，不伪造空音频。

参考命令：

```bash
arecord -D plughw:0,1 -f S16_LE -r 48000 -c 2 -d 4 -t wav /tmp/mic48.wav
```

### `board_speaker.py`

使用 `aplay` 播放固定 WAV。

```python
def play_wav(path, device="plughw:0,0"):
    ...

def announce_event(event_id, **values):
    ...
```

第一版使用预生成 WAV：

```text
data/audio/prompts/
normal.wav
abnormal.wav
source_conflict.wav
record_saved.wav
read_failed.wav
digit_0.wav ... digit_9.wav
point.wav
minus.wav
volt.wav
ampere.wav
please_confirm.wav
```

不要在 Cortex-A9 上直接跑完整中文 TTS。

### `ui_bridge.py` 或现有界面新页面

页面名称：

```text
实验助手
```

第一版只显示：

```text
状态：待命/录音中/识别中/执行中/成功/失败
识别文字
理解结果
当前读数
数据来源
记录结果
异常提示
```

必须接入现有界面；没有现有源码时才用 `/dev/fb0` 写临时页面。

### `sources/`

```text
sources/
  __init__.py
  base.py
  mock.py
  scpi.py
  vision.py
```

统一读数格式：

```json
{
  "request_id": "...",
  "device_id": "...",
  "source_type": "scpi",
  "source_role": "primary",
  "value": 3.301,
  "raw_value": "3.3012",
  "raw_text": "3.3012 V",
  "unit": "V",
  "valid": true,
  "captured_at": "...",
  "image_path": null,
  "confidence": null,
  "error_code": null
}
```

视觉源增加：

```json
{
  "source_type": "vision",
  "source_role": "fallback",
  "confidence": 0.96,
  "image_path": "data/images/..."
}
```

## `main.py` 改造

### Python 3.7 兼容

把：

```python
temporary_path.unlink(missing_ok=True)
```

改成：

```python
try:
    temporary_path.unlink()
except FileNotFoundError:
    pass
```

### 数据源替换

保留 `acquire()`、`validate_reading()`、`save_record()`。

改成：

```python
def get_reading(request_id, simulate_failure=False, source=None):
    if source is None:
        source = get_default_source()
    return source.read(request_id, simulate_failure=simulate_failure)
```

### 记录 schema

旧记录继续可读。新记录增加：

```json
{
  "source_type": "scpi",
  "source_role": "primary",
  "sources": [
    {"source_type": "scpi", "value": 3.301, "unit": "V", "valid": true},
    {"source_type": "vision", "value": 3.30, "unit": "V", "valid": true}
  ],
  "source_consistency": {
    "status": "matched",
    "difference": 0.001,
    "tolerance": 0.01
  },
  "reference_comparison": null
}
```

冲突时：

```json
{
  "source_consistency": {
    "status": "conflict",
    "difference": 0.149,
    "tolerance": 0.02,
    "primary_source": "scpi",
    "message": "接口读数与视觉读数差值过大"
  }
}
```

### UI 事件

至少发布：

```text
state_changed
asr_partial
asr_final
command_parsed
reading_acquired
record_saved
source_conflict
error
```

## `text_cli.py` 改造

保留解析规则。把终端 IO 抽象为：

```python
class TextApplication:
    def __init__(self, presenter=None, confirm_batches=False):
        self.presenter = presenter or ConsolePresenter()
```

新增：

```python
class Presenter:
    def show_state(self, state): ...
    def show_message(self, text): ...
    def show_pending(self, text): ...
    def ask_confirm(self): ...
```

板端 UI 只显示，不修改 `parse_command` 语义。

## `asr_cli.py` 改造

保留：

- Vosk 流程。
- 置信度筛查。
- 交给 `TextApplication`。

替换：

- `sounddevice` 改为 `board_audio.capture_wav()`。
- `print()` 改为 UI 事件。

增加：

```python
def run_asr_service(model_path, audio_source, on_partial, on_final):
    ...
```

Vosk 缺失时：

```text
界面显示：Vosk 未安装
应用仍可进入文本输入模式
不能因 ImportError 退出整个界面
```

## 视觉部分

当前：

```text
/dev/video0
OV5640
V4L2 multiplanar
RGB3 / BGR3
```

要求：

1. 先修复 `cv2` 段错误，或确认它和 NumPy 1.17.0/系统库不兼容。
2. 不可用时，用 V4L2 抓原始帧，再交给 NumPy。
3. 不假设 `cv2.VideoCapture(0)` 一定可用。
4. 不修改摄像头驱动和设备树。

## 修改顺序

1. 定位现有界面进程和源码，确认新页面入口。
2. 修复 Python 3.7 兼容问题。
3. 新增 `board_audio` 和 `board_speaker`。
4. 把 `text_cli` 的终端交互抽成 presenter。
5. 在现有界面增加“实验助手”页面。
6. 把 `asr_cli` 录音替换为 `board_audio`。
7. 安装或离线部署 Vosk，测试 Python 3.7 / ARMv7。
8. 接入 C 的 vision 读数源。
9. 增加 source_consistency 和扬声器异常播报。
10. 整机联调。

## 验收

命令：

```bash
python3 --version
python3 main.py
python3 text_cli.py
arecord -D plughw:0,1 -f S16_LE -r 48000 -c 2 -d 4 -t wav /tmp/mic48.wav
aplay -D plughw:0,0 /tmp/mic48.wav
```

界面：

```text
启动后仍能进入原有界面
新增“实验助手”页面
页面能显示识别文字、状态和错误
原有页面和导航不被破坏
```

业务：

```text
语音或文本输入可触发 read/record
无有效读数时不保存正常记录
记录仍由 main.save_record 写入
SCPI 与视觉读数差值过大时，扬声器播报“数据异常”
所有记录带来源、时间和异常状态
```

## 不要做

- 不删除或覆盖厂商界面。
- 不替换现有 PL Bitstream。
- 不引入 PYNQ Overlay。
- 不使用 Python 3.8 及以上语法。
- 不在板端直接安装最新版 NumPy、OpenCV 或 SciPy。
- 不用 `eval()` 解析语音命令或公式。
- 不把视觉读数当作参考值。
- 不把语音播报文本当作测量源。

## 修改前必须确认

1. 现有界面进程名和源码路径。
2. 现有界面框架：Qt、LVGL、framebuffer 或其他。
3. 界面启动脚本和服务名。
4. 板端是否有 `scipy`、`PIL`、`pygame`、`serial`。
5. Vosk 是否有 ARMv7 + Python 3.7 wheel。
6. C 的视觉接口和 SCPI 仪器是否可用。
