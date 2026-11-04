# 构建输入与来源

- 原推理入口：D:/FPGA/labmate_lite_image_reader_board_v2/c_vision_lite/smoke_infer.cc，未改动算法。
- 原 Paddle-Lite 动态库：同一 v2 包，内含版本字符串 v2.14-rc。
- 头文件：[Paddle-Lite v2.14-rc 官方源码](https://github.com/PaddlePaddle/Paddle-Lite/tree/v2.14-rc/lite/api)，保留 Apache-2.0 版权头。
- Python 头文件：[CPython 3.7.6 官方发布](https://www.python.org/downloads/release/python-376/)，配置头取自本工作区出厂 rootfs。CPython LICENSE 保存在 sources/CPython-LICENSE。
- pyclipper：[PyPI 1.3.0.post5 源码分发](https://pypi.org/project/pyclipper/1.3.0.post5/)，下载时校验 PyPI 提供的 SHA-256；MIT 许可随离线包附带。
- 交叉工具链：D:/Xilinx/SDK/2018.3/gnu/aarch32/nt/gcc-arm-linux-gnueabi，Linux ARM hard-float GCC 7.3.1。未使用 arm-none-eabi 裸机工具链。
- libgomp：该现有工具链的 arm-linux-gnueabihf/lib/libgomp.so.1.0.0，复制命名为 libgomp.so.1。GCC GPLv3 与 Runtime Library Exception 见官方许可文本。
- native_fault.c：本次编写，仅用于诊断子进程，不安装到系统库目录。

重建脚本、下载记录和完整源码输入保留在电脑端同名输出目录的 fetch_sources.py、build_support.py、validate_support.py、sources/ 和 build/。部署 ZIP 仅包含板上所需的小文件与说明。

当前未进行实体板或模拟器执行验证。

本修正版移除了 pyclipper 编译时的 -fvisibility=hidden；CPython 3.7 的 PyMODINIT_FUNC 在本配置下不会自动覆盖该隐藏标记。原版初始化入口为 LOCAL，修正版必须为 GLOBAL DEFAULT 并出现在动态符号表中。
