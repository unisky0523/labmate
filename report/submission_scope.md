# 200 MB 提交包范围

桌面 `Labmate/` 是唯一的标准交付源码目录，对应桌面 `labmate.rar`。原始完整材料、旧压缩包和处理中间文件已单独移到桌面 `Labmate_backup_20261104/`，不混入交付目录。

保留当前 ARM/Qt、语音运行模块、仪器通信、摄像头/OCR 源码和最新辅助模块，保留测试、OCR 模型、语音运行库、配置、FPGA 工程及构建所依赖的既有视频 IP HDL、约束、bit/XSA、Linux 内核源码与补丁、板端镜像、关键日志和复现脚本。

去掉内核归档中的 VS Code 索引、编辑器缓存、旧启动镜像和备份目录；内核源码文件内容逐项保留并记录 SHA256。源码改以 `.tar.xz` 保存，两个内核构建脚本和输入清单同步调整压缩格式。原始 Linux 归档中仅 `.vscode-ctags` 就有 632674411 字节，它不参与构建。

另外去掉视觉辅助包的临时构建目录、旧版/嵌套备份、重复录音、重复历史报告和收集用脚本；保留核心工程的实际构建入口和依赖。预训练 Vosk 中文模型使用官方固定版本下载，提供自动获取和逐文件 SHA256 校验，完整备份中仍保留原模型。可选的 CPython 解释器源码通过原下载清单获取，运行所需既有 payload 保留。

具体剔除清单见 `report/omitted_files.json`；内核保留文件内容、剔除缓存和归档哈希见 `build/kernel_source_manifest.json`。核心工程不需要等待额外 GitHub 仓库才能开始复现。ASR 十组数据保持“团队手动实测”，数值保持不变；队员正式 ESP32 固件、网页及配套 ARM 模块现已补齐。

上传文件是桌面 `labmate.rar`，按小于 200000000 字节进行检查；不要上传完整备份目录。RAR 内的目录和源文件映射遵循原提交结构。系统软件 Vivado、Qt SDK 和板卡基础 rootfs 仍属于复现环境前置条件。


FPGA 的 `ip_user_files/sim_scripts/` 是 Vivado 导出的模拟器脚本及支持文件，可用匹配 Vivado 重新导出，因此未随包重复提交；实际综合所需的 `.gen` HDL、ROM 初始化文件、BD、IP 和约束保留。RTL 及其现有实现报告保持完整。


本轮新增 195 个交接文件的恢复映射；同字节依赖、OCR 模型和运行库复用现有归档，完整交接可重建。原 FPGA ZIP 内较早 ESP-IDF 示例仍不采用；新增正式 PlatformIO 实现与网页已纳入 RAR。

本轮为容纳正式 ESP32/网页交接，将旧的 `report/history/fpga/recovery/original_asr_filtered.bit` 回退备份仅保留在桌面完整工程；当前 bitstream、XSA、参考 DCP 和全部构建源码仍在提交包内。


加入正式 ESP32/网页材料后，将内核 XZ 归档提高到 preset 9；独立解压并比较前后整个 tar 流的 SHA256，内容逐字节一致，未额外删减源码。内核归档摘要、两个构建入口的输入清单和来源映射已同步，78 项输入校验通过。记录见 `sim/results/kernel_recompression.json` 与 `sim/results/kernel_input_checks.json`。
