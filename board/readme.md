# 上板产物、启动与部署材料

- `fpga/`：所提供 SPI/ASR 工程已有的 bitstream 与 XSA。
- `arm/bin/`：已有助手和桌面 ARM ELF32 程序；准备后桌面文件名恢复为 `QMainApp`。
- `arm/tools/`：串口、启动、安装/回退、板端核验及历史调试脚本。
- `arm/settings/`：已有冻结版本的配置和模板快照。
- `linux/artifacts/`：已构建内核、设备树、匹配模块、配置、补丁及验证输出。
- `linux/boot/`：既有 SPI 自动启动、备份/回退材料及运行日志。

源文件名规范化后，实际运行这些工具前应先按 `report/reproduction.md` 恢复工作区。本目录保留已有部署能力和证据，本次整理未连接板卡或执行刷写。历史脚本的固定端口、设备身份、启动位置和 SDK 路径需按实际环境核对。

`linux/boot/final_check.log` 是已有自动启动核验的直接证据。队员正式 ESP32 固件现已收录在 `esp32/`；新图像发送使用恢复后的 `board_modules/c_camera_link/`，旧内核示例发送器不配套。本轮未执行端到端硬件实测。

新增 `esp32/`（合并固件与清单）、`arm/camera/`（静态 ARM 采集程序）及 `run_camera_preview.sh`（工作区中的匹配发送入口）。先按根目录说明恢复源码，再按 `report/board_modules/readme.md` 部署。
