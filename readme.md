# LabMate 智能实验室助手

LabMate 是我们基于 Zynq-7010、ARM Linux 和 ESP32 开发的智能实验室助手，集成语音识别、Qt 触屏交互、仪器通信、FPGA 音频处理、摄像头/OCR 和网页预览。本仓库包含项目源码、构建脚本、部署工具和验证记录。提交范围见 [提交范围](report/submission_scope.md)。

版本日期：2026-11-04（北京时间）。目标平台：正点原子领航者 7010 / XC7Z010CLG400-1，ARM Linux、Qt 5 与 Vivado 2020.2。

我们按竞赛推荐结构组织工程，收录 FPGA 工程、语音识别、Qt 触屏界面、仪器通信、连续记录、扫频、FFT 的 ARM 接口、摄像头/OCR 历史模块、Linux 内核与驱动、构建脚本和验证记录。ESP32 固件、内嵌网页及 ARM 配套板端模块均已收录。 详见 [新增材料与复现入口](report/board_modules/readme.md)。 Zynq 侧 SPI RTL、Linux 设备树和 ARM 发送工具属于本次工程，继续保留。

## 目录对照

```text
labmate/
|-- readme.md
|-- src/                 # FPGA、ARM、Linux、ESP32 与网页源码
|-- sim/                 # 已有离线检查入口、参考工具与本次检查结果
|-- build/               # 源码准备、可复现构建、综合实现报告与校验清单
|-- board/               # bit/xsa、ARM 程序、Linux 镜像、启动与部署脚本
|-- data/                # 模型、离线依赖、测试输入、日志及参考结果
|-- skill/               # 三个可复用 FPGA 技能、脚本、案例与说明
`-- report/              # 设计说明、验证边界、来源和大模型协作记录
```

所有归档文件及目录名使用英文小写、数字、下划线、连字符和扩展名中的点。指南示例中的 `README.md` 在这里写作 `readme.md`，统一满足小写命名规则。原来中文文档的新位置见 [文档索引](report/document_index.md)。

## 先看这些内容

- [源码与功能说明](report/design_report.md)：ARM 各模块、FPGA 音频前端、SPI 和内核驱动的位置。
- [编译、测试与部署](report/reproduction.md)：从本交付副本准备工程，再按目标环境构建。
- [验证记录与结论](report/verification.md)：本次检查、原有构建结果及实机证据的范围。
- [待补材料](report/pending_items.md)：最终硬件验收、OCR、PL FFT 和后续测量附件。
- [文件来源清单](report/source_inventory.csv)、[完整文件校验](build/package_manifest.json)。

## 快速复现

在本目录运行，Python 环境需安装 NumPy：

```sh
python -B build/verify_package.py
python -B sim/run_checks.py --workspace /path/to/labmate_repro
```

Windows 的检查示例：

```powershell
python -B sim/run_checks.py --workspace D:/labmate_repro
```

**正式构建、运行已有测试或部署前，先用准备脚本恢复原始工程文件名。** Vivado、Qt 资源、Python 包元数据及第三方库会依赖大小写敏感文件名；本次仅改变归档路径，保留源文件原始字节，通过映射在交付目录以外重建原始工作区：

```sh
python -B build/prepare.py --out /path/to/labmate_repro --component all
```

准备后的 `arm/`、`fpga/`、`linux/`、`vision/`、`board/`、`boot/`、`board_modules/`、`skill/` 是工作副本。原文件名只在该构建工作区恢复；上游内核源码压缩包也保留其原有内部结构。不要直接在归档副本中把原来的 `Makefile`、`QMainUI.pro` 或元数据文件强行改名后编译。


## 首次运行真实语音前获取模型

先按上文准备工作区，再运行：

```sh
python -B build/fetch_dependencies.py --workspace /path/to/labmate_repro
```

脚本获取官方 `vosk-model-small-cn-0.22`，逐文件核对本项目原模型的 14 项 SHA256；然后放入工作区的 `arm/assets/voice/models/`。模型来源见 [Vosk 官方模型列表](https://alphacephei.com/vosk/models)。若已有完整备份，可离线复用：

```sh
python -B build/fetch_dependencies.py --workspace /path/to/labmate_repro --from-full /path/to/full_labmate
```

也可用 `--model-archive /path/to/vosk-model-small-cn-0.22.zip` 指定已下载 ZIP。离线单元检查使用模拟依赖，不必先下载模型。完成模型准备后，按部署说明把 `arm/assets/voice/` 放入既定板端模型位置。

## 测试与性能结果

本次已在精简提交副本上重新通过 Qt/ARM 业务检查 181 项、DG4102 检查 17 项、语音命令行检查 22 项，共 220 项。原始日志在 `sim/results/`。这些是离线功能回归，不代表新增的板卡实测。

我们保留的 FPGA 综合与实现报告记录了 LUT 12418/17600、FF 21261/35200、BRAM 12.5/60、DSP 7/80、Slice 4392/4400，约束内 setup/hold 裕量分别为 +0.135 ns / +0.029 ns。原报告及已有告警全部保留，见 `build/reports/fpga/`。

我们手动测量了 10 组配对 ASR 响应耗时，原始记录见 [ASR 响应日志](data/logs/asr_response_log.md)。原 ARM 流程与加入 FPGA 后流程的中位响应耗时分别为 5.595 s、1.605 s，本组实测中位耗时降低约 71.3%。实测 CSV、统计结果和后续复测表位于 `data/`，统计入口为 `sim/analyze_asr.py`。

当前 FFT 配置的 `worker_argv` 为空，ARM 可以取点并显示“待 FPGA”；PL FFT bitstream、DMA 驱动和桥接程序仍待交付。Linux SPI 自动启动日志可证明设备枚举、mode1 与 READY 输入配置，不能替代 ESP32 接收端或整条链路的性能验收。


## ESP32 与网页

源码分别位于 `src/esp32/camera_link/` 和 `src/web/camera_preview/`，固件在 `board/esp32/`。配套 ARM 发送/仪器/OCR 模块作为 `board_modules` 组件恢复。完整说明见 [材料检查与对接边界](report/board_modules/readme.md)。

```sh
python -B build/prepare.py --out /path/to/labmate_repro --component board_modules
python -B sim/check_board_modules.py --workspace /path/to/labmate_repro --out /path/to/checks.json
```

现有内核限频 4 MHz，先使用配套发送端的 `--ten-fps` 预设联调。旧内核交接的 `send_jpeg.py` 封包与本轮固件不同；最高帧率模式请求 8 MHz，需同步设备树和硬件实测。OCR 重编译、整机冷启动及最终固件现场验收仍待完成。


## FPGA 技能包

团队编写的三个可复用 FPGA 技能现已收录于 [skill/](skill/readme.md)，包含固定向量 RTL 黄金参考、实现报告审计及通用 PYNQ 契约预检。按 `prepare.py --component skill` 恢复原始 SKILL.md 文件名；要求对照与验证结果见 [技能包审阅](report/skill_review.md)。
