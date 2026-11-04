# LabMate 可复用 FPGA 技能包

本目录收录团队编写的三个独立技能，按现有竞赛指南 3.3.5.2 对照整理。每项均包含适用范围、调用方法、已验证效果、来源观察及失效条件。它们可作为大模型的任务说明，也可由人工直接运行配套脚本。

| 技能与说明 | 适用范围和使用入口 | 已验证效果及主要边界 |
| --- | --- | --- |
| [定点流式 RTL 黄金参考](fixed-point-stream-golden/skill.md) | FIR/预处理等 ready/valid 流模块；`scripts/run_xsim.py --vivado-bin PATH` | 固定输入、独立整数黄金模型及 SV 测试台；滤波/旁路、两轮复位、反压与元数据比对。更换算法、位宽、采样格式或时钟须重建向量并检查时序。 |
| [Vivado 实现报告审计](vivado-implementation-audit/skill.md) | 同一布线结果的 timing/utilization/DRC 审计；`scripts/audit_reports.py examples/navigator7010` | 附真实报告摘录、接口改造观察和提示词；返回 2 表示约束覆盖需要人工复核。不能把 WNS 为正扩大为所有外部时序都通过。 |
| [通用 PYNQ Overlay 契约](pynq-overlay-contract/skill.md) | 自定义 IP/VLNV/地址窗/寄存器的元数据预检；`scripts/check_overlay.py CONTRACT --snapshot SNAPSHOT` | 离线快照与反例可运行，真实 PYNQ 下载和跨板复测待验收。契约与本队语音/SPI 项目解耦，可用于别的 AXI 外设。 |

源码取自队员原 ZIP，全部 21 个文件均已保留。归档采用小写 `skill.md`/`readme.md` 以遵守现有目录命名规则；若需标准 `SKILL.md` 文件名或保持原包目录，请先恢复工作区：

```sh
python -B build/prepare.py --out /path/to/labmate_repro --component skill
```

恢复后的目录为 `/path/to/labmate_repro/skill/`，三个子目录分别保留原 `SKILL.md`。固定向量回归及报告/快照检查只需 Python 标准库和 XSim；重新生成 FIR 系数/频响/向量额外需要 NumPy、SciPy。PYNQ 实板检查额外需要匹配的 PYNQ 环境和同次构建 `.bit`/`.hwh`。

```sh
cd /path/to/labmate_repro/skill/vivado-implementation-audit
python scripts/audit_reports.py examples/navigator7010
cd ../pynq-overlay-contract
python scripts/check_overlay.py examples/contract.example.json --snapshot examples/snapshot.example.json
```

第一条真实报告回放预期退出码为 **2**，表示 WNS/WHS/资源/DRC 基本门限通过，但存在需人工检查的约束覆盖问题；这是明确的审计结论。PYNQ 离线正例预期为 0。

完整要求对照及本轮验证见 [技能包审阅](../report/skill_review.md)。原交接总说明位于 `report/history/skill/fpga_skill_readme_original.md`。本项目 ASR 的十组响应耗时继续按团队手动实测保存；技能用例中的向量和通用快照不改变该数据分类。
