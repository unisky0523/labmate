# 技能包目录说明

按推荐目录结构保留本目录。本次收到的材料没有独立项目技能包，未编造已安装的技能或额外工具调用记录。

项目复现操作可复用以下入口：

1. `build/verify_package.py`：确认交付副本完整性。
2. `build/prepare.py`：准备正确文件名和目录关系的工作区。
3. `sim/run_checks.py`：执行已有离线功能检查。
4. `report/reproduction.md`：按 ARM、FPGA、Linux 分别构建和部署。
5. `report/pending_items.md`：依据真实交付补齐 PL FFT、最终硬件验收和测量证据。

大模型参与本次整理的输入、动作、验证和限制见 `report/collaboration/work_record.md`。

ESP32 与网页已收录：按 `report/board_modules/readme.md` 选择匹配发送端并恢复 board_modules 工作区。
