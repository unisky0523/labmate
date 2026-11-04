# SDS1202X 板端移植与验收

状态：Windows + NI-VISA 已实测标量读数和 SCDP 截图。板上已通过 lsusb 识别 SDS1202X（f4ec:ee3a），有 libusb-1.0.so.0，但没有 PyUSB、/dev/usbtmcN 或可加载的 usbtmc 模块。新版包包含 Python 用户态 USB 依赖，尚未在板上实测读数，不能称作板端完成。

## 连接与依赖

2026-11-01：板上导入报 No module named typing，说明精简 Python 缺标准库模块。包内 compat_py37 携带 CPython v3.7.6 官方 typing.py 和许可证；启动器将该目录追加到搜索路径，仅在系统模块缺失时回退，不替换系统文件。此补充尚待板端验证；后续若仍报缺模块，需要保留完整 traceback。

- SDS1202X 后面板 USB Device 接 Zynq Linux 的 USB Host 口，不接调试串口或前面板 U 盘口。
- 当前板端推荐用户态 libusb + PyUSB + PyVISA-py，不需要 usbtmc 内核模块。六个兼容 Python 3.7 的纯 Python 包已作为 vendor 随包携带，不用在板上联网或运行 pip；系统仍须有 libusb-1.0.so.0。
- 原先的 /dev/usbtmcN 字符设备后端保留；只有内核驱动和设备节点都存在时才使用。
- 电脑端原有 --backend @ivi 路线保持不变。万用表继续使用 /dev/ttyUSB0 等实际 CP210x 串口节点，两个设备节点不能混用。

## 板端命令

必须复制并解压“含 vendor 的新版” labmate_sds1202x_board.zip，替换旧版 c_instrument 文件；不要只覆盖单个 Python 文件。连接示波器后，在包含 c_instrument 子目录的父目录执行：

    sh c_instrument/scope_board_check.sh
    sh c_instrument/run_scope_board.sh --list

若列表中出现 SIGLENT 的 USB0::...::INSTR 资源，先读两项标量（只有一个 USB 仪器时可自动选择）：

    sh c_instrument/run_scope_board.sh --measure PKPK FREQ

再保存当前屏幕（仅查询截图，不切换 Run/Stop、通道、触发设置）：

    sh c_instrument/run_scope_board.sh --screenshot

若 --list 返回多个 USB 仪器，将真实的 SIGLENT 地址作为 --resource "USB0::...::INSTR" 传给后两条命令。不要把万用表的 COM9 或 /dev/ttyUSB0 当作示波器地址。

输出的 image_path 指向 BMP 文件。若板端屏幕仍在变化，标量与截图不保证同一帧；对比时先在仪器面板按 Stop。

## 验收回传

请保留两次完整 JSON、截图文件、仪器当前屏幕照片或读数、scope_board_check.sh 输出以及板端系统与 Python 版本。
用户态标量应含 transport=visa、simulated=false、identity_verified=true，峰峰值与频率需和面板相符；截图文件应能打开且与面板对应。这里的 visa 指 Python 后端对 USBTMC 的访问，不代表板上安装了 NI-VISA。
未取得板端真实 USBTMC 节点和读数前，本交付物只属于“待上板验证的源码包”。

若 --list 仍找不到仪器，先保留完整报错和 lsusb 输出，检查 vendor 目录、libusb、设备描述符及 /dev/bus/usb 权限。不要盲目安装 Windows 驱动或手动创建 /dev/usbtmc0。当前板端 root 用户仍需以实测结果为准。
