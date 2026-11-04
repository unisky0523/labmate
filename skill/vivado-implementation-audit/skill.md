---
name: vivado-implementation-audit
description: 在已有 Zynq 工程中增加 PL 或 PS EMIO 接口时检查基线差异，并从 Vivado 布线后报告提取时序、约束覆盖、资源和 DRC。
---

# Vivado 实现报告审计与改造工作流

适用于维护既有 Vivado Block Design 的 FPGA 工程。脚本使用 Python 3 标准库，识别 Vivado 2020.2 的文本报告布局。版本、器件族或报告格式变化时，先用真实报表验证字段解析。使用同一布线检查点导出全部报告，避免把不同运行的结果混在一起。

## 用法

在 `skill/vivado-implementation-audit/` 下回放本项目的真实报告摘要。摘要删去了本机路径及不相关明细，保留原始统计表。

```sh
python scripts/audit_reports.py examples/navigator7010
```

审计自己工程时，在打开布线后设计的 Vivado Tcl Console 中执行下列命令，把输出目录传给检查脚本。

```tcl
file mkdir audit
report_timing_summary -file audit/timing.rpt
report_utilization -file audit/utilization.rpt
report_drc -file audit/drc.rpt
report_io -file audit/io.rpt
```

| 退出码 | 解释 |
|---|---|
| 0 | 报表可读，已约束路径、资源和 DRC 门限通过，四项约束覆盖计数均为零 |
| 1 | 输入缺失、表格格式不匹配、资源超容量、有时序违例，或出现 DRC Error／Critical Warning |
| 2 | 已约束路径、资源和 DRC 门限通过，仍有缺失或非零的约束覆盖计数需要人工核对 |

## 改造时保留的证据

| 触发条件 | 定位步骤 | 项目观察 |
|---|---|---|
| 新接口要借用扩展脚 | 对照目标版本原理图、封装脚和现有 `report_io`，标出复用外设和电平，再检查布线后实际接点 | 7010 的 J3 有 LCD 和原串口／CAN 复用脚。本项目保留 LCD，使用 UART/CAN 的四根信号，旁路对应板载收发器，并用 U4 追加 READY |
| 已经有 `.bit` 但 Linux 找不到新控制器 | 分开检查 PS 初始化、设备树、驱动绑定和 PL 走线。先核对地址、时钟和中断，再核对用户程序 | PS SPI0 经 EMIO 引出，硬件传输仍由 PS 控制器负责。新增 I/O 模块可见 `examples/navigator7010/spi_emio_master_io.v`，示例依赖 AMD I/O 原语和 Zynq 主机模式，封装脚不随代码移植 |
| WNS 为正但资源难以再加 | 同时看 LUT 和物理 Slice／CLB 占用。用 `check_timing` 明细定位缺时钟、未约束内部端点和 IO 约束缺口 | LUT 为 70.56%，物理 Slice 已到 99.82%。真实报告还有 214 个 no_clock 与 492 个未约束内部端点，返回 2 |
| 原厂 HLS 重生成卡住 | 固定可复现工具版本、核对 C 源码和 IP 配置。已有相同版本生成的 RTL 时，可保留它并重新执行综合、实现与校验 | 2020.2 原厂视频缓存 HLS 在分析阶段停留。复用逐文件一致的生成 RTL 后完成 bitstream。IP 配置、源码或工具版本变化需重新核对生成产物 |
| 工程能打开但换目录丢文件 | 解压到不同路径，检查源文件、相对引用、IP 产物和 BD 校验。最后按目标配置独立重建 | 实际交付 ZIP 换目录后打开，701 项工程文件缺失 0 项。该检查证明项目可打开，完整构建结果来自原实现流程 |

### 提示词模板

> 输入为 [基线 Block Design／XDC]、[器件和板卡版本]、[新增接口]。先给出需要改的 PS/PL 边界、现有引脚复用和受影响的地址。实现后提供实际端口连接、同一检查点的 timing/utilization/DRC 和基线差异。分别报告已约束时序、缺失约束和实机验证。若遇到 IP 重生成失败，定位实际失败阶段并说明复用旧生成 RTL 的前提。给出异地复现的最短命令。

## 验证和限制

本项目使用 Vivado 2020.2 完成综合与布局布线。包内真实报告回放得到 12,418 LUT、21,261 FF、12.5 个 BRAM36 等效块、7 DSP、4,392/4,400 Slice，WNS +0.135 ns、WHS +0.029 ns。DRC 有 58 条 Warning，按当前报告未检出 Error 或 Critical Warning。`audit_reports.py` 将约束覆盖单独列出，无法判断某项 IO 时序例外是否合理。实际放行仍需复核每项约束、引脚电平和板外时序，器件容量未超也无法预测下一次布局能否成功。
