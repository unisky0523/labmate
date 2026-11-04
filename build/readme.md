# 构建入口和报告

先在根目录阅读 `readme.md` 与 `report/reproduction.md`。构建和测试工作区放在交付目录以外。

| 文件或目录 | 用途 |
| --- | --- |
| `prepare.py` | 按映射恢复原始大小写文件名；逐文件核对 SHA256，不覆盖不同内容的文件。 |
| `source_map.json` | 归档路径、原始来源、恢复路径和哈希映射。 |
| `build_arm.sh` | 使用已安装的 Qt/ARM SDK 编译助手与桌面。 |
| `build_fpga.py` | 调用所提供的 Vivado 2020.2 生成 RTL 构建入口。 |
| `verify_package.py` | 校验命名、来源哈希、Qt 资源、ARM ELF、内核 CRC、DTB 和完整包清单。 |
| `package_manifest.json` | 整理完成后记录的全部文件 SHA256；自身不包含在哈希列表中。 |
| `reports/fpga/` | 用户提供工程的原始综合实现、时序、资源、I/O、DRC 和源文件审计。 |
| `reports/linux/` | 已有 Linux 内核编译日志。 |

完整 Linux 构建入口归档在 `src/linux/kit/build_spi.sh`，需经 `prepare.py --component linux` 恢复为 `linux/linux_kit/build_spi.sh` 后执行，确保其原文件名、依赖路径和输入校验保持一致。所有新构建产物留在工作区，不会覆盖提交副本的历史报告。


新增 `board_modules/` 的固件合并/原始交接清单工具通过 `prepare.py --component board_modules` 恢复后运行。ESP32 和网页构建、Zig ARM 构建及 OCR 重编译见 `report/board_modules/readme.md`。`sim/check_board_modules.py` 提供本轮独立离线核验。
