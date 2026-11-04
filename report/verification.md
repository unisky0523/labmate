# 验证结果与证据边界

记录日期：2026-11-04（北京时间）。本次归档保留原始证据，并在交付副本恢复出的 ARM 工作区运行已有离线检查。未重新操作板卡、下载 FPGA、交叉编译完整系统或采集真实 ASR 配对数据。

## 本次检查

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Qt/ARM 应用现有回归 | 181 项通过 | `sim/results/arm_ui.log` |
| DG4102 现有离线检查 | 17 项通过 | `sim/results/dg4102.log` |
| 独立语音命令行检查 | 22 项通过 | `sim/results/voice_cli.log` |
| 本次检查汇总 | 220 项通过 | `sim/results/local_checks.json` |
| 英文小写命名、源文件 SHA256、Qt 资源、ARM ELF32、内核 CRC、DTB 和包清单 | 由 `build/verify_package.py` 统一核验 | `build/package_manifest.json`，运行脚本可重验 |

初次测试遇到系统临时目录权限限制，并发现 DG4102 测试需要从 Python 包父目录运行。修正本次复现脚本的临时目录和调用方式后全部通过；原业务源码未因此修改。初次环境问题的日志保留在完整备份；提交副本仅保留最终通过日志。

这些检查覆盖已有业务测试、语音分句/确认、数值单位、仪器调度、记录与历史、FFT 契约和软件参考等路径，采用模拟依赖。离线通过不等于真实麦克风、仪器输出、摄像头和新内核组合均已完成现场验收。

## 原有 FPGA 综合实现

证据来自我们采用的 Vivado 2020.2 FPGA ZIP，归档在 `build/reports/fpga/`。这是所提供工程的历史构建结果，本次没有重新生成。

| 指标 | 原报告数值 |
| --- | ---: |
| Slice LUT | 12418 / 17600，70.56% |
| Slice FF | 21261 / 35200，60.40% |
| Slice | 4392 / 4400，99.82% |
| Block RAM Tile | 12.5 / 60，20.83% |
| DSP | 7 / 80，8.75% |
| WNS / TNS | +0.135 ns / 0.000 ns |
| WHS / THS | +0.029 ns / 0.000 ns |
| 约束内 setup / hold 失败端点 | 0 / 0 |

时钟摘要记录 `clk_fpga_0` 100 MHz、`clk_fpga_1` 148.170 MHz、`clk_fpga_2` 200 MHz、`clk_fpga_3` 12.012 MHz，另有 LCD、音频及 RGMII 时钟，详见原 `timing.rpt`。这些是工程约束/分析频率，不能直接当作系统最大频率或语音吞吐率。

原 DRC、I/O 和时序告警保持原样；报告指出的约束内通过结论不能覆盖未约束的外部 SPI 路径。Slice 已接近占满，后续增加 PL FFT 需要另做资源/时序评估。后续收到的 FPGA 技能包已补齐专用音频前端测试台和固定黄金向量，本轮仿真结果见文末。

## 原有 ARM 与板端记录

`data/logs/development/` 保留语音、桌面入口、截图与历史、单位解析、连续记录、DG4102、扫频和 FFT 的开发与部署日志。`data/logs/accepted_sweep/` 保存已冻结版本清单、核验报告及引用关系。历史文档中的验收结论仍限定在对应日期、版本和操作范围内。

FFT 记录中，HOST4 从 SDS1202X 读取 700000 个实际采样点，原触发模式 AUTO 得到恢复；整理后为 4096 点输入。该次采样整理约 8.59 s、波形读取约 4.43 s。合成正弦软件参考峰值为 976.5625 Hz、约 0.800419 Vpeak。前者是一次采样记录，后者是参考向量，均不能证明 PL FFT 已实现或具有相同性能。

## 原有 Linux SPI 启动记录

`board/linux/boot/final_check.log` 和 `autoboot.log` 记录：

- 运行内核 `5.4.0-xilinx-v2020.2-spi-test-20261104`。
- `/dev/spidev1.0` 对应 `labmate,esp32-image-link`，SPI mode1、8 位。
- READY 为输入，该次 gpiochip base 下的节点为 `gpio962`。
- `/dev/video0`、`/dev/fb0` 枚举存在，启动资产 SHA256 校验通过。
- 已验证一次无人为打断的重新启动；原记录未完成断电再上电验证。

这些材料可确认 Linux SPI 初始化和启动链的已有结果。原记录明确未在这一轮重发图片；完整 ESP32 端到端接收、CRC、吞吐和相机/显示/音频联合回归仍需后续证据。原始 FPGA 构建文档写有“未上板”，后来的 Linux 启动日志是不同阶段记录，二者均保留，不能互相扩大结论。

## ASR 响应耗时

`data/logs/asr_response_log.md` 的十组数据为我们团队的手动实测结果。原 ARM 流程中位响应耗时为 5.595 s，加入 FPGA 后流程为 1.605 s，减少 3.990 s；本组手动实测的中位耗时降低约 71.3%。

实测 CSV 为 `data/asr_response_measurements.csv`，标记 `kind=measurement`、`measurement_method=manual`；统计结果为 `data/asr_measurement_statistics.json`。`status=measured` 表示已报告手动计时数值，不额外推造逐次准确率、录像或自动测量记录。脚本直接统计这十组实测，不需要样例开关。

原附件中的录像、统一版本哈希等内容作为后续复测方案保留，不声称它们已用于本批手动测量。原附件旧措辞与当前测量记录的关系已在日志和历史来源说明中注明。


## 本轮 ESP32、网页与板端材料核验

新交接 ZIP CRC 检查及 SHA256 已记录，195 个文件全部收录，恢复后原始清单的 194 个负载文件全部匹配。106 个 Python 文件通过语法编译及 Python 3.7 语法解析；网页 JavaScript 经 Node.js 语法检查通过。

三个 ARM 采集/编码程序的大小、SHA256、ELF32 ARM 格式及静态链接属性通过检查，构建清单指向的 C 源码和头文件摘要匹配。ESP32 合并固件大小 885056 字节、SHA256 匹配清单，其中实际嵌入的 HTML 与随包网页原始字节一致。

使用交接中的实际 Python 协议实现验证 27 组长度/序号边界的封包、CRC、1024 字节分块和重组，另核对 8 组非法帧/ACK 拒绝路径。GPIO 定义和现有 XDC 对应，发现并记录旧发送脚本封包不兼容及 4/8 MHz 配置差异。

以上结果见 `sim/results/board_modules_checks.json`。本轮未重新执行 PlatformIO/Zig 交叉构建，未重新编译 ESP32/ARM 程序，也未访问硬件。原交接 `verification.md` 的 117 项回归、浏览器交互和编译结果仅作为团队编写的历史检查记录，相关原始日志/测试脚本未随本 ZIP 提供。已有 Qt/ARM 220 项离线检查对应的业务源码未被本轮修改。


## 新增 FPGA 技能和 RTL 仿真

技能包中的音频 RTL/系数与主工程逐字节相同。本轮使用 XSim 2026.1 跑通滤波/旁路各两轮，每轮 6000 字，共 24000 次比对；它验证该前端模块的算术、握手、反压和复位，不等同于全系统音频实测。实现报告审计预期返回 2（约束覆盖待复核），PYNQ 离线正例、六类反例和模拟 metadata-only 调用通过，未访问实际 PYNQ 板。详见 `report/skill_review.md` 和 `sim/results/fpga_skill_checks.json`。
