# 实验助手：显示资料与 Qt 源码定位记录

更新日期：2026-10-28。当前工作目录：`D:\fpga amd xinlx`。

## 2026-10-28 最新结论

板卡资料已下载到本地。已找到出厂桌面源码，入口是 `4_Source_Code/3_Embedded_Linux/资源文件.rar → 资源文件/QtDemo.zip → QtDemo/mainUI/QMainUI`，不是 Qt 教学包里的 `01_appmainview`。

参考源码已提取到 `D:\fpga amd xinlx\work\vendor_factory_reference\QtDemo`。已只读核对配套出厂 rootfs：启动程序为 `/opt/qt5/QMainApp`，现有 20 个独立应用，Qt 库为 5.13.2。新增“实验助手”可沿用子应用机制，追加第 21 个入口时同步扩展到 5 页。

详细改动位置、编译及部署方案见 [出厂桌面新增实验助手入口](labmate_factory_qt_entry_plan.md)。下文中“未下载”“未解压”等结论是 2026-10-25 的历史记录，已经由本次核对更新；实际板端当前文件和运行状态仍未检查。

## 已确认的本地资料

| 目录 | 内容及当前用途 |
| --- | --- |
| `【正点原子】4.3寸RGB LCD电容触摸屏模块资料` | 屏幕用户手册、原理图、触摸芯片资料及 STM32 示例源码。 |
| `【正点原子】4.3寸RGB LCD电容触摸屏模块资料（新资料）` | ATK-MD0430R 用户手册 V1.1、使用说明 V1.0、原理图和 STM32 示例源码。 |
| `【正点原子】OV5640单目摄像头模块` | 摄像头新旧资料。已检查文件清单，本次未逐个审查摄像头示例实现。 |

已读取屏幕新旧用户手册和新版使用说明，并列出两套屏幕资料中 `2，程序源码` 的全部 8 个 ZIP 包内容；未解压、执行或修改厂商程序。这 8 个包没有 `.pro`、`.ui`、`.qml` 或 `CMakeLists.txt`，文件名和说明对应 STM32F429/F767/H743/F750/H750 示例。它们可用于查屏幕硬件接口，不能直接作为领航者 Zynq Linux 上的 Qt 界面工程使用。

ATK-MD0430R 系列同时存在 480×272 和 800×480 型号。用户提供的产品页面为 **4.3 寸 RGB LCD、电容触摸、800×480**，后续界面暂按 800×480 横屏设计；这不等于已经通过板端运行参数核实实际屏幕型号、显示方向和触摸功能。现阶段不占用队友的开发板。

屏幕手册：

- `【正点原子】4.3寸RGB LCD电容触摸屏模块资料（新资料）\ATK-MD0430R模块用户手册_V1.1.pdf`
- `【正点原子】4.3寸RGB LCD电容触摸屏模块资料（新资料）\ATK-MD0430R模块使用说明_V1.0.pdf`

## 2026-10-25 在官方资料盘目录中确认的下载位置（历史记录）

用户先前截图里的资料盘链接与官方领航者 V2 资料页匹配；这只确认资料入口，尚未据此确认实物底板的具体硬件版本。

- [领航者 V2 官方资料页源文件](https://github.com/alientek-openedv/Products/blob/master/zdyz_docs/boards/fpga/zdyz_linhanz%28V2%29.rst)
- [资料 A 盘](https://pan.baidu.com/s/1vXxmhg_mZm_OVg4xQeiCVQ?pwd=zdyz)，提取码 `zdyz`。
- [4.3 寸 800×480 RGB LCD 官方资料页源文件](https://github.com/alientek-openedv/Products/blob/master/zdyz_docs/modules/lcd/4.3-RGBLCD-800480.rst)

2026-10-25 已通过浏览器查看 A 盘的可见目录，确认以下名称和大小；**尚未下载或解压下面的 Qt 包，不能据目录名称断言其具体工程、Qt 版本或板端兼容性**。

```text
正点原子领航者(V2)ZYNQ开发板资料盘(A盘)/
├── 1_领航者ZYNQ开发板出厂综合测试/
├── 2_文档教程/
└── 4_Source_Code/
    ├── 3_Embedded_Linux/
    │   ├── Linux_app.rar              341 KB
    │   ├── Linux驱动例程.rar          2.21 GB
    │   ├── vivado_prj.rar             219.5 MB
    │   ├── zynq_petalinux.rar         350.4 MB
    │   └── 资源文件.rar               1.15 GB
    ├── 6_Embedded_Qt_Design.zip       332.6 MB
    ├── 7_Linux C应用编程.rar          289.9 MB
    └── 源码说明(必读).txt
```

为寻找界面源码，应优先下载 `4_Source_Code/6_Embedded_Qt_Design.zip`；若目标是给当前出厂桌面增加入口，还需要检查 `1_领航者ZYNQ开发板出厂综合测试` 里的源码或说明。出厂综合测试目录已在根目录中看到，内部文件尚未核对，不能声称已找到当前桌面对应的主工程。

截至本次本地检查，上述 Zynq Qt 包和出厂综合测试源码尚未出现在工作目录的文件清单中。开发板资料仍由用户下载中，不将未完成的下载当作损坏文件处理。

## 其他已检查的本地工程

- `D:\qt example\untitled`：Qt Creator 默认的空白 QWidget 工程，包含 `CMakeLists.txt`、`main.cpp`、`mainwindow.cpp/.h/.ui`。已有构建目录指向桌面 Qt 6.9.2 / MSVC 2022 64 位，不能当作已经适配 ARM Linux 的板端程序。
- `D:\fpga`：已发现的项目为其他 FPGA/Quartus 示例，尚未发现所需的领航者 Qt 工程。

## Qt 包到齐后的核对顺序

1. 先读 `源码说明(必读).txt`、Qt 教程和工程 README，定位 `.pro`、`.ui`、QML 或 `CMakeLists.txt`。
2. 区分单项教学示例与板端正在使用的综合桌面，定位 `main()`、主窗口和菜单入口；确认 QWidget 或 QML。
3. 从厂商编译配置确认 Qt 版本、ARM 交叉编译器、sysroot、Qt 平台插件，以及显示和触摸的启动设置。当前不得从电脑安装的 Qt 6 推断板端版本。
4. 在自己的工作副本中新增“实验助手”页面，沿用现有显示/触摸接口，先用模拟状态验证 800×480 布局和按钮交互。
5. 对接 Python 后台的本地控制接口和 `latest_status.json`，让界面能触发识别并显示过程及结果；现有命令行程序仍需服务入口，不能只把阻塞的终端 `input()` 放进 Qt 主线程。
6. 开发板空闲后，再核对实际运行环境并部署匹配的应用做实机验证。

相关方案：[现有显示框架接入实验助手](labmate_ui_integration_plan.md)、[PS 基线与 PL 迁移计划](labmate_ps_baseline_and_pl_migration.md)。

当前只做资料核对，没有连接串口、占用开发板、刷写 SD 卡或改变现有系统。增加 Qt 应用页面通常只涉及匹配板端环境的应用和资源部署；是否需要系统层调整，应在核对现有工程后判断，不能为做界面先重刷系统。
