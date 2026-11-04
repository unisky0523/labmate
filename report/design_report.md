# LabMate 设计与源码说明

本报告描述 2026-11-04 收集的工程材料。正文中的“支持”指所收录源码实现的功能；实机确认的范围单独见验证报告。较早文档保留在 `report/history/`，其中的旧待办、绝对路径和实验指令属于历史记录。

## 系统组成

```text
麦克风 / ES8388
  -> FPGA I2S / 音频格式化 / ASR 前端
  -> Linux ALSA -> ARM Vosk 与命令解析
  -> Python 业务调度 -> Qt 界面、确认保存和历史

USB 仪器 -> 万用表 / SDS1202X / DG4102 通信模块
          -> 读数、截图、发生器设置、连续记录、扫频曲线

OV5640 -> 原有 PL 视频链路 -> Linux V4L2
       -> ARM 图像读取 / OCR 历史工程
       -> ARM 原生 V4L2/JPEG -> Zynq SPI0 EMIO -> ESP32 热点与网页

SDS1202X 波形 -> ARM 取点与 FFT 文件协议
             -> PL FFT 桥接接口（硬件待交付）
```

## ARM 正式应用

主要源码在 `src/arm/ui/`，准备后对应 `arm/work/labmate_ui/`。Qt 工程入口为 `labassistant.pro`。本次采用当前本地源码，收齐其 Python 业务模块、语音运行源码、DG4102 子模块、资源和测试；另保留 11 月 2 日、11 月 3 日的已发布版本核验记录。

| 源文件或目录 | 职责 |
| --- | --- |
| `main.cpp` | Qt 触屏界面、语音状态、结果展示、手动确认、历史列表与详情、截图和频谱查看、曲线交互。 |
| `backend.py` | Qt 与 Python 的 JSON 协议、任务状态、异步调度、确认/取消、记录与历史操作。 |
| `asr_adapter.py` | 复用模型和录音流、语音确认、句尾判定、识别状态与耗时。 |
| `audio_frontend.py` | ARM 侧音频前处理及其配置/标定接口。 |
| `asr_runtime/board_listen.py` | 持续录音、按静音分句和正式 little PCM 路径。 |
| `asr_runtime/board_mic.py`、`board_audio.py` | 采样字节转换、声道选择、声卡及 ES8388 初始化。 |
| `asr_runtime/asr_cli.py`、`vosk_lite.py`、`asr_backend.py` | 识别器、Vosk 动态库加载、词表约束与识别入口。 |
| `asr_runtime/main.py`、`text_cli.py`、`asr_grammar.py` | 实验指令、数值与单位解析、确认和撤销词表。 |
| `instrument_adapter.py`、`command_executor.py` | 万用表和示波器读取、截图及仪器任务执行。 |
| `generator_control.py`、`generator_runner.py`、`dg4102_driver/` | DG4102 控制、设备绑定、波形设置和受控执行。 |
| `sweep_response.py` | 连续扫频采集、响应曲线组织与记录。 |
| `scope_waveform.py`、`fft_protocol.py`、`fft_control.py` | HOST4 原始取点、FFT 输入输出约定、结果校验与绘图调度。 |
| `record_store.py` | 读数、截图、曲线与频谱归档，确认保存、撤销、历史清除及持久化。 |
| `instruments.json` | 设备来源、查询超时、FFT 点数及待接入 worker 配置。 |
| `tests/` | 现有功能回归与夹具。 |

厂商桌面工程在 `src/arm/desktop/`，包含桌面入口、子进程生命周期和图片资源。准备后其工程文件恢复为 `QMainUI.pro`。现有 ARM ELF 程序在 `board/arm/bin/`；Qt 依赖板卡原有 ARM Linux/Qt 环境，不能作为 Windows 可执行程序运行。

`src/arm/voice_cli/` 是独立语音命令行工程，供调试和追溯；当前 Qt 应用使用 `ui/asr_runtime/`，原生库放在 `data/models/voice/`，预训练中文模型使用 `build/fetch_dependencies.py` 按固定清单获取，避免误用旧版语音入口。

`src/arm/instruments/` 收录 SA5041 万用表和 SDS1202X 示波器的现有通信模块、板端脚本、测试与依赖。DG4102 对接模块位于正式 UI 工程中。这些用户态仪器模块与 Linux 内核驱动分别归档。

## 摄像头、OCR 与图像模块

`src/arm/vision/` 收录已有摄像头与图像读取工程，包括 `c_vision`、`c_vision_lite`、`c_vision_paddle`、板端支持库、OV5640 自动对焦辅助代码、内核恢复补丁及相关测试记录。Paddle Lite 模型、字表和运行库也一并收录，原始模型位置由源码映射恢复。

该部分来自既有板卡/桌面备份，保留为独立子系统，没有将其描述为当前 Qt 实验助手中已完成的统一 OCR 流程。原工程中的早期版本同时保留，使用时以各子目录原说明和版本标记为准。

## FPGA 工程

`src/fpga/project/` 来自我们采用的 `Navigator_7010_ASR_SPI_ESP32_Vivado2020_2.zip`，包含 XPR、Block Design、约束、自定义 IP、生成的 HDL 和运行所需参考产物。准备后工程恢复在 `fpga/Navigator_7010/`。

音频前端在 `asr/rtl/asr_audio_frontend.v` 和 `fir_coeff.vh`。模块提供 `BYPASS` 参数：旁路路径进行音频传输，滤波路径逐声道去直流并执行 127 抽头 FIR。源码注释记录 100 MHz 时钟、44.1 kHz 双声道 24 位输入；实际交付工程配置和连接以 BD/XCI 为准，模块参数默认值不能替代工程实例参数。

SPI 部分使用 PS SPI0 经 PL EMIO 引出，新增 GPIO READY 输入并调整相关 UART1/CAN0 引脚。其 FPGA I/O RTL 在 `spi/rtl/`，Linux 侧设备树和 ARM 发送工具仍保留。这里的 FPGA SPI 接口属于 Zynq。原 ZIP 的早期 ESP-IDF 示例不作为项目正式实现；本轮另收录正式 Arduino/PlatformIO 接收端与内嵌网页，见 `src/esp32/`、`src/web/`。

交付构建沿用未改动视频 IP 的既有生成 RTL，重新执行综合、布局、布线和 bitstream 生成。该方式及原始 HLS 重生成入口都在原脚本中保留；直接重生成旧视频 HLS 仍依赖匹配的工具环境。`build/reports/fpga/` 保存原始时序、资源、DRC、I/O、源文件审计和编译日志。

## Linux 内核与驱动

完整厂商 Linux 5.4.0 源码在 `src/linux/kernel/atk-zynq-linux-xlnx.tar.xz`。本次内核构建包包含原板配置、SPI 设备树片段、spidev compatible 补丁、离线主机构建依赖和验证脚本；构建入口经准备后恢复为 `linux/linux_kit/build_spi.sh`。

| 材料 | 归档位置和作用 |
| --- | --- |
| 原始内核源码 | `src/linux/kernel/`，完整压缩包，内部文件名保持上游结构。 |
| 主要驱动参考 | `src/linux/drivers_reference/`，SPI Cadence、spidev、GPIO、OV5640、USBTMC、I2C 和音频等源码。它们是原始源码快照。 |
| SPI 修改后参考 | `src/linux/patched_reference/`，既有准备脚本产生的 spidev 和板级 DTS 快照。 |
| 配置与准备工具 | `src/linux/kit/`，原板配置、设备树、辅助脚本和离线构建入口。 |
| 编译产物 | `board/linux/artifacts/`，uImage、zImage、DTB、匹配内核模块、Module.symvers、补丁和验证输出。 |
| 启动材料 | `board/linux/boot/`，已有 boot.cmd/boot.scr、初始化服务、备份与回退脚本，以及串口证据。 |
| 构建日志 | `build/reports/linux/` 和 `data/logs/development/`。 |

现有 SPI 内核版本为 `5.4.0-xilinx-v2020.2-spi-test-20261104`，设备 compatible 为 `labmate,esp32-image-link`。配置差异中还记录：所供厂商源码缺少可选 Realtek 蓝牙驱动，因此该候选内核将 `CONFIG_BT_RTK_HCIBTUSB` 从模块关闭；该差异没有被隐去。

已有启动日志记录 `/dev/spidev1.0`、mode1 和 READY 输入，GPIO 全局编号取决于 gpiochip base，程序应按 base+65 查找。`/dev/video0`、`/dev/fb0` 的存在只证明节点枚举，不能直接证明视频、显示和音频全部通过功能回归。

## 参考数据和性能口径

ASR 响应时间按日志口径，从口令播放结束到界面首次显示正确结果。我们手动测量了 10 组配对响应耗时：两组中位数分别为 5.595 s 和 1.605 s，本组实测中位耗时降低约 71.3%。实测日志、英文列名 CSV、统计结果及后续复测表见 `data/readme.md`；原附件作为历史来源另行保留。

FFT 数据包含 HOST4 实际取点记录和合成正弦参考向量。`sim/fft_reference.py` 为软件数值对照，正式应用拒绝把 `software_reference` 当 FPGA 结果。当前只交付 ARM 协议和准备流程，尚无本项目真实 PL FFT 的性能结论。


## 正式 ESP32、网页与配套 ARM 模块

本轮补齐的链路为 OV5640 V4L2 → ARM JPEG → PS SPI0/EMIO → ESP32 → 本地热点浏览器。ESP32 源码在 `src/esp32/camera_link/`，网页在 `src/web/camera_preview/`，三块 JPEG 缓冲区分别保存接收、最新、冻结帧；HTTP 服务提供状态、版本绑定图像、快照、冻结/恢复和标注。网页负责显示与 PNG 合成，标注状态在 ESP32 客户端间共享。

源目录按提交规范归档，`board_modules` 映射重建其原始可部署目录，模型和依赖复用已有相同字节。新仪器包装和 OCR 作为独立交接保留；现有 Qt 业务源码未改。当前 DTB 限频 4 MHz，新最高帧率预设请求 8 MHz；新帧协议与旧内核交接示例不同，详见 [对接说明](board_modules/readme.md)。


## 可复用 FPGA 技能

`skill/` 提供定点流式 RTL 黄金参考、Vivado 实现报告审计、通用 PYNQ Overlay 契约。专用测试台所用 RTL/系数与主工程相同，本轮 XSim 2026.1 的 24000 次比对通过；主工程原综合实现仍为 Vivado 2020.2。技能内容和比赛要求对照见 `report/skill_review.md`。
