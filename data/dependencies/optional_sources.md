# 可选第三方重建源码

原生库、OCR 模型、现有 ARM 程序、FPGA 设计和 Linux 构建源码已保留。Vosk 预训练中文模型使用官方固定版本下载，由 `build/fetch_dependencies.py` 自动获取并逐文件校验；完整备份中仍保留原模型。

视觉辅助包构建时使用的 CPython 3.7.6 原始 tarball 不再重复附带。其官方 URL、文件名与 SHA256 已保留在 `src/arm/vision/labmate_board_support_20261018_v2/sources/download_manifest.json`；准备 `vision` 工作区后可使用原 `fetch_sources.py` 获取。板卡运行依赖其已安装的 Python、NumPy、OpenCV、Qt 和对应 SDK/BSP。原辅助包 `payload/` 和实际 C/C++/Python 源码保留。

Vivado 和 ARM SDK 继续使用已安装的匹配工具环境，详见复现报告。完整版在提交包以外的本地 `Labmate/labmate/` 留存，可另行同步到指定 GitHub 仓库。
