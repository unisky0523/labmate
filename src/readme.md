# 源码索引

| 路径 | 内容 |
| --- | --- |
| `fpga/project/` | 我们采用的 Vivado 2020.2 工程，保留 ASR、视频、显示和 Zynq SPI 接口相关设计；ESP32 MCU 正式实现单独归档。 |
| `arm/ui/` | 当前 Qt 助手、Python 后台、语音运行源码、DG4102、FFT 接口、连续记录和扫频模块。 |
| `arm/desktop/` | 厂商桌面基础上的实验助手入口与资源。 |
| `arm/voice_cli/` | 独立语音命令行工程及测试，作为辅助入口与追溯材料。 |
| `arm/instruments/` | SA5041 与 SDS1202X 通信代码、依赖和测试。 |
| `arm/vision/` | 摄像头、OCR、Paddle Lite 和板端支持历史工程。 |
| `linux/kernel/` | 完整厂商 Linux 5.4.0 源码压缩包。 |
| `linux/drivers_reference/` | 从原始源码包提取的主要驱动与 DTS 参考。 |
| `linux/patched_reference/` | 原有准备脚本生成的 SPI 修改后参考快照。 |
| `linux/kit/` | 原内核构建脚本、配置、设备树片段与辅助工具。 |

归档中文件名按小写英文规范化，内容保持原始字节。**请先使用 `build/prepare.py` 恢复原始工程，再编译、运行测试或部署**；恢复路径和来源在 `build/source_map.json` 与 `report/source_inventory.csv` 中逐项记录。


新增 `esp32/camera_link/` 为项目正式 ESP32 工程；`web/camera_preview/index.html` 为内嵌网页；`arm/board_modules/` 为配套 ARM 采集、发送、仪器与 OCR 交接源码。使用 `prepare.py --component board_modules` 恢复整个交接，复用依赖由映射自动补齐，详见 `report/board_modules/readme.md`。
