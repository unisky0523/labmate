# 第三方组成

本目录仅记录第三方来源，不替团队选择项目整体许可证，也不改变任何上游许可。发布负责人统一处理自有代码授权、作者及最终公开发布所需的信息。

| 组成 | 来源与版本 | 许可位置 |
| --- | --- | --- |
| PyVISA 1.12.0、PyVISA-py 0.6.3、PyUSB 1.2.1 | 对应 PyPI 发行 wheel，见 requirements-scope-board.txt | `c_instrument/vendor/*dist-info/LICENSE*`，保留元数据 |
| typing-extensions 4.7.1、importlib-metadata 4.13.0、zipp 3.15.0 | 对应 PyPI 发行 wheel | 同上 |
| CPython typing 回退 | 保留的兼容模块 | `c_instrument/compat_py37/CPYTHON_LICENSE.txt` |
| stb_image_write 1.16 | https://github.com/nothings/stb ，提交 1ee679ca2ef753a528db5ba6801e1067b40481b8 | 原始头文件末尾 MIT / Public Domain 双许可 |
| musl | Zig 0.13.0 所带静态链接运行库 | `musl-COPYRIGHT`，从实际使用工具链保留 |
| Arduino-ESP32 2.0.17 | https://github.com/espressif/arduino-esp32/tree/2.0.17 ，PlatformIO framework 3.20017.241212+sha.dcc1105b | `arduino-esp32-LICENSE`，LGPL-2.1-or-later；第三方 SDK 组件各按其许可 |
| ESP-IDF 4.4 系列 SDK | Arduino-ESP32 2.0.17 所带 SDK，https://github.com/espressif/esp-idf | 主项目 Apache-2.0，部分组件及预编译库采用独立许可，不能统一改为 MIT |
| ArduinoJson 6.21.5 | https://github.com/bblanchon/ArduinoJson/tree/v6.21.5 | `ArduinoJson-LICENSE`，MIT |
| newlib | ESP32 工具链链接运行库 | `newlib-COPYING`，从实际工具链保留 |
| Paddle-Lite ARMv7hf 运行库/头文件 | https://github.com/PaddlePaddle/Paddle-Lite/releases/tag/v2.14-rc ，armlinux.armv7hf.gcc.with_extra 发行包 | 主项目 Apache-2.0，通用原文见 `Apache-2.0.txt`；头文件保留原始版权头 |
| PP-OCRv5 mobile det/rec 模型、alphabet | PaddleOCR 模型经 legacy 图导出后转换为 Paddle-Lite .nb；https://github.com/PaddlePaddle/PaddleOCR | `PaddleOCR-LICENSE`，保留实际上游许可；随包模型是推理资产，无训练集 |

固件与 ARM 程序是方便项目部署而附带的构建产物，文件摘要见 MANIFEST。仅附部分主项目许可不代表完成了所有 SDK 子组件的公开二进制分发审查；本包是交接给发布同学的代码与资产清单。公开二进制时，应按相应上游发行内容补齐组件 notices、源码提供义务等要求，或由最终开源工程重新构建发布。PlatformIO 和 Zig 工具链本身不随包分发。

vendor 从上游 wheel 解包，仅去除了 PyVISA/PyVISA-py 的 testsuite 目录。保留的 dist-info/RECORD 是原发行记录，不是本包裁剪后文件清单；本包实际内容以根目录 MANIFEST.sha256.json 为准。
