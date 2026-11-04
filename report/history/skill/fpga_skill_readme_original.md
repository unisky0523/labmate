# LabMate FPGA 技能包

按竞赛指南 3.3.5.2 整理。三个技能可以分别移入其他项目。每个目录的 `SKILL.md` 都可交给大模型作为执行说明，脚本也可单独运行。

| 技能 | 适用场景 | 用法 | 已验证效果与失效条件 |
|---|---|---|---|
| [定点流式 RTL 黄金参考](fixed-point-stream-golden/SKILL.md) | 定点 FIR、预处理和其他 ready/valid 流模块 | 运行 XSim 回归，再按接口契约替换算法和黄金模型 | 2020.2 下滤波及旁路共 24,000 次比对通过。更换数据格式、滤波参数或时钟后须重新生成向量并检查时序 |
| [Vivado 实现报告审计与改造工作流](vivado-implementation-audit/SKILL.md) | 给已有 Zynq 工程新增接口或核对布局布线结果 | 用同一布线结果导出 timing、utilization、DRC，运行 Python 检查器 | 领航者实报回放得到 WNS +0.135 ns、WHS +0.029 ns、Slice 99.82%，并提示约束覆盖待复核。报表结构变化时需适配解析器 |
| [通用 PYNQ Overlay 契约预检](pynq-overlay-contract/SKILL.md) | 在 PYNQ 板上接入有 HWH 描述的 AXI 外设 | 自定义 IP 路径、VLNV、地址窗和寄存器偏移，用快照或 Overlay 元数据检查 | 离线正例、反例和模拟 PYNQ 调用通过。实体 PYNQ 板上的 Overlay 解析、下载和 MMIO 读取待复测 |

将整个 `skill/` 目录放到提交包根目录。音频子包包含原项目 RTL、独立整数模型、测试台和固定向量。Vivado 子包包含真实报告摘录、SPI EMIO 接线案例、可复制的提示词工作流和排错步骤。PYNQ 子包的契约与示例使用独立的通用 IP 路径，换板时按新工程的 `.bit`、`.hwh` 和寄存器定义填写。

仿真结果用于说明 RTL 的功能正确性。实现报告只说明对应检查点的资源、DRC 和时序。端到端识别提速和 SPI 外部时序需要单独上板测量，评审示例数据不作为实测证据。
