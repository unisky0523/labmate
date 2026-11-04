# LabMate 语音代码交接给 A

交接整理日期：2026-10-28。代码来源：`D:\labmate_b` 当前文件，主要修改时间为 2026-10-22。本说明没有把未完成的功能写成已经验收通过。

## 可以交哪些文件

`labmate_b` 就是当前语音项目主目录，可以作为源码交接。板端运行必须同时保留 Python 源码、`models/vosk-model-small-cn-0.22`、`libvosk.so`、`lib/libatomic.so.1`、`run_board.sh` 和本说明/README。不要只发一个 Python 文件。

建议发干净交接包，排除 Windows `.venv`、`__pycache__` 和历次 `data` 测试输出。程序运行时会创建需要的数据目录。若要复现某次识别问题，另附那次 WAV 与对应 ASR JSON；干净包不含此前全部录音和记录。

## 当前实现到哪里

离线识别和业务逻辑运行在 Zynq **PS 的 ARM Linux** 上，电脑串口用于交互和查看日志。当前没有自研的语音 PL 加速模块，也没有完成 Qt 页面和 Python 服务的联动。

```text
回车触发/输入文字
 → ES8388：arecord 采集 44.1 kHz / S24_LE / 双声道
 → 按 LE 低 24 位解码，选择一路，转为 16 kHz 单声道
 → Vosk 小中文模型
 → 领域命令解析
 → 待确认/执行/JSON 记录与状态输出
```

这是一套受限实验指令系统，不是任意中文对话助手。支持读数、人工报电压电流、连续记录、查最近记录、异常/作废标记、确认/取消等。拍波形和保存波形目前只生成动作请求，不代表相机或保存程序已经执行。

| 文件 | 作用 |
| --- | --- |
| `board_app.py` | 板端主入口，加载模型，回车录音，调用 ASR 和业务逻辑。 |
| `board_mic.py` | 静音播放保活、ALSA 录音、ES8388 配置、声道与 PCM 处理。 |
| `board_audio.py` | WAV 读写和重采样等辅助功能；正式采集转调 `board_mic`。 |
| `asr_cli.py` | 识别、音频筛查、词表、置信度与命令解析、确认流程、ASR 日志。 |
| `asr_backend.py`、`vosk_lite.py` | 优先官方 `vosk` 包，否则用 ctypes 加载随包 ARMv7 `libvosk.so`。 |
| `text_cli.py` | 文本归一化、中文数值/单位解析、待确认与动作分发。 |
| `main.py` | 统一记录保存、查询、异常/作废标记和数据校验。 |
| `board_sources.py` | 模拟读数、JSON 视觉数据接入；SCPI 适配仍未实现。 |
| `board_ui.py` | 原子更新 `data/state/latest_status.json`，还不是显示界面。 |
| `readback.py`、`board_speaker.py` | 回读尝试和提示音，中文 TTS 依赖板端已有 espeak 工具；缺少时不能保证播报完整文字。 |
| `board_check.py` | 板端依赖/模型检查，不测试实际麦克风质量。 |
| `voice_cli.py`、`record_test.py`、`pc_speaker.py` | PC 原型或辅助工具，不是正式板端启动入口。 |

## 两种识别模式

1. 默认：先通用中文识别；未得到可解析命令时，用领域词表再识别一遍。
2. 加 `--command-grammar`：直接使用项目词表，只做一遍命令识别。

当前主词表 54 项、确认词表 20 项，位于 `asr_cli.py` 的 `GRAMMAR_WORDS` 和 `CONFIRM_GRAMMAR_WORDS`。尚未完成此前讨论的全面扩词。文本解析器支持的句式不等于词表/声学模型能全部识别；新增词表也不会自动训练声学模型。

此前同一段“记录电压三点三伏”板端录音的用户对比记录为通用识别 25.62 秒、命令词表 2.66 秒。这仅是单份录音的识别计算时间，不包含采集和模型初始化，不作为准确率或整机响应时间保证。

## 板端环境与运行

现有项目依据：ATK-ZYNQ / ARMv7 / Linux 5.4 / Python 3.7.6，板上已有 NumPy 1.17.0。采集使用 `hw:0,1`，播放使用 `default`。依赖 `arecord`、`aplay`、`i2cset`、`amixer` 以及当前 ES8388 配置。这套音频参数不能直接用于资料盘里另一套 WM8960 底板。

先进入**实际应用目录**。此前板端用户确认过 `/home/root/labmate_b_audio_test`；新交接若放 `/home/root/labmate_b`，则进入新位置。不要假设目录一定存在，也不要在原目录外再套一层 `labmate_b`。

依赖检查（在板端执行，电脑 Windows 不能加载随包 ARM 动态库）：

```sh
LD_LIBRARY_PATH="$PWD/lib:$PWD" PYTHONIOENCODING=utf-8 python3 board_check.py --load-model
```

注意检查器目前没有单独检测 `amixer`；即使 PASS 也不等于音频链路已通过。

默认通用识别：

```sh
sh run_board.sh --source mock --seconds 5 --mic-channel 0
```

命令词表识别：

```sh
sh run_board.sh --source mock --seconds 5 --mic-channel 0 --command-grammar
```

`--source mock` 的仪表读数是模拟值。真实视觉程序应提供 JSON，再改为：

```sh
sh run_board.sh --source json --reading-json data/from_c/reading.json --command-grammar
```

`--no-vosk` 可检查文字业务流程并保存录音，不会进行语音识别。输入 `q` 退出。按一次回车开始录音，等“现在开始说话”提示后说话，默认 5 秒后自动结束，不需要第二次回车。

适合演示的命令：读取数据、记录电压三点三伏、确认、取消、连续记录三次数据、查看记录、上一条数据有问题、拍一下波形、当前状态。它们是已实现的解析意图示例，不保证当前麦克风对每句话都稳定识别。

主要输出：`data/audio/asr_tests/` 录音，`data/asr_logs/` 识别日志，`data/records/` 记录，`data/requests/` 动作请求，`data/state/latest_status.json` 当前状态。

## 已知问题与下一步

- 音频仍有用户报告的“鸭子音”，不能交接为音质已解决。最新生产采集使用 little-endian 低 24 位/4 字节容器；此前固定采用 MSB 重排的结论已经撤回，MSB 只保留为历史诊断选项。
- 每轮仍重启静音播放和录音，启动/预热约 4 秒，然后才是默认 5 秒有效录音。常驻音频流及降低等待尚未实施，不能简单删除时间等待。
- 默认最小词置信度是 0.45，只是未标定筛查阈值，不等于准确率。
- **回读确认分支待修**：`asr_cli.process()` 中第二次 `analyze()` 已可能返回低置信度拒绝，但随后又解析第二次文字决定确认。2026-10-28 用 mock 输入“确认”、置信度 0.1，仍复现了命令被交给应用。A 应先补齐这一分支的有效性判断和回归测试；本次交接没有静默修改识别代码。`--confirm-readback` 不能当作已经完整验证的保护措施。
- 现有状态 JSON 是输出接口，Qt 按钮输入服务尚未实现；`board_app.py` 仍阻塞在终端 `input()`。
- 摄像头/波形动作只是请求文件；`--source json` 需要视觉程序持续提供真实数据。SCPI 未接通。
- 连续记录执行期间不会并行监听“停止”语音口令，目前靠 Ctrl+C 中止。
- 后续路线已约定为 PS 跑通并测基线，再选合适模块迁移 PL，比较包含数据搬运的端到端耗时。

本次 PC 检查：现有 22 项单元测试通过；根目录 Python 文件通过 Python 3.7 语法解析检查。测试使用模拟音频/进程，不代表新的板端实测，也没有消除上面的确认分支问题。

资料目录旧的 `dist/labmate_b_board_20261015.zip` 早于 10 月 22 日修改，不能当作当前源码快照。以本说明随附的新交接包或当前源码为准。
