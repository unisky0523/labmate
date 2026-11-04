# 在领航者出厂桌面新增“实验助手”入口

核对日期：2026-10-28。结论来自用户本地的厂商源码、出厂 rootfs 和文档；尚未连接开发板核对当前 SD 卡的实际文件。

## 1. 结论

可以沿用厂商桌面的应用启动机制，新增一个“实验助手”图标，点击后启动独立的 800×480 Qt Widgets 应用。Qt 界面和 Python 识别后台运行在 PS 的 Linux 用户态。

当前菜单的 20 个应用分成 4 页，每页 5 个。保留原有应用并追加第 21 个入口时，需要把菜单扩展为 5 页。只多放一个可执行文件，不会自动生成桌面图标；只扩大应用数组，也不能让原来的滑动逻辑到达第 5 页。

本次仅提取参考源码、检查镜像内容并整理实施方案，没有修改厂商源码、运行镜像内的程序或部署到板端。

## 2. 真正的出厂桌面源码位置

```text
正点原子领航者(V2)ZYNQ开发板资料盘(A盘)/
  4_Source_Code/3_Embedded_Linux/资源文件.rar
    资源文件/QtDemo.zip
      QtDemo/mainUI/QMainUI/QMainUI.pro
```

已提取可直接阅读的参考副本：

```text
D:\fpga amd xinlx\work\vendor_factory_reference\QtDemo\
```

`4_Source_Code/6_Embedded_Qt_Design.zip` 内的 `Qt例程.zip/项目篇例程/01_appmainview` 是另一个教学演示工程。本次实施以 `QtDemo/mainUI/QMainUI` 为主。

出厂桌面参考工程使用 C++ / Qt Widgets / qmake，界面主要在 `.cpp` 中创建，没有需要修改的主界面 `.ui` 文件。

## 3. 已核实的启动和通信机制

已只读检查 `资源文件.rar/资源文件/出厂镜像相关/rootfs.tar.gz`，其中：

| 项目 | 镜像里的实际内容 |
| --- | --- |
| 启动脚本 | `/etc/init.d/qtGUI.sh` |
| 桌面启动命令 | `/opt/qt5/QMainApp >/dev/null 2>&1 &` |
| 显示平台 | `QT_QPA_PLATFORM=linuxfb:fb=/dev/fb0` |
| 字体目录 | `QT_QPA_FONTDIR=/usr/share/fonts` |
| 触摸设备变量 | `TSLIB_TSDEVICE=/dev/input/by-path/platform-e0005000.i2c-event` |
| 现有应用 | `/opt/qt5/apps/0/app` 至 `/opt/qt5/apps/19/app` |
| Qt Core 库 | `/usr/lib/libQt5Core.so.5.13.2` |

镜像中实际脚本和清单的检查结果另存于 `tmp/alientek_docs/rootfs_etc_init.d_qtGUI.sh.txt`、`rootfs_qt_inventory.json`，未把这些设置应用到电脑或开发板。

源码入口 `main.cpp:6` 把工作目录设为可执行文件所在目录。`mainwindow.cpp:233` 为每个应用拼接 `./apps/<编号>/app`；`slotAppBtnClicked()` 在应用未运行时通过 `QProcess` 启动它，已运行时发送 `show` 并隐藏桌面。应用启动成功后，桌面也会隐藏。

日历等子应用提供了返回协议，可参考 `calendar/QCalendar/mainwindow.cpp:134`：

- 子应用返回主页：向自己的标准输出写入精确的 `show` 并刷新，然后隐藏自身。
- 桌面收到该子应用的 `show` 后，重新显示主界面。
- 再点同一个图标：桌面向子应用的标准输入发送 `show`，子应用恢复显示。
- 桌面要求退出时：发送 `quit`，子应用应处理并退出。
- 子应用的“关闭”按钮应先通知桌面显示，再退出；否则现有桌面没有完整的子进程异常退出恢复逻辑，可能停留在空白画面。

新子应用的 stdout 应只用于兼容这套桌面协议。Python 日志应由子应用自己的 `QProcess` 接收，日志显示在控件或写文件，不可未经处理转发到子应用 stdout。新消息处理实现应按实际读取长度处理数据，并兼容厂商发送的 NUL 填充消息，不照抄未终止字符数组的比较方式。

## 4. 新增第 21 个入口的具体改动

下列行号对应未修改的参考源码。

| 文件与位置 | 现状 | 实施时需要修改 |
| --- | --- | --- |
| `mainUI/QMainUI/mainwindow.h:101` | `apps[20]` | 以统一应用总数常量定义数组，新增应用 ID 为 20。 |
| `mainUI/QMainUI/mainwindow.h:113` | `indexBars[4]` | 页数由总数和每页数量计算，21 个应用对应 5 页。 |
| `mainUI/QMainUI/mainwindow.cpp:216` | 图标容器宽 3200 | 按 800×页数计算，5 页宽 4000。 |
| `mainUI/QMainUI/mainwindow.cpp:227` | 创建 20 个图标和进程 | 循环到新的应用总数，保留原编号 0—19。 |
| `mainUI/QMainUI/mainwindow.cpp:233` | 路径 `./apps/<id>/app` | 可沿用，新增应用部署到 `apps/20/app`。 |
| `mainUI/QMainUI/mainwindow.cpp:244` 起 | 给各图标设置图片 | 给 `apps[20]` 增加“实验助手”图标及可见标题。原图标文字画在图片内，新图标也要有清晰可见的名称。 |
| `mainUI/QMainUI/iconres.qrc` | 编译进桌面的图片资源 | 注册新的图标资源。 |
| `mainUI/QMainUI/mainwindow.cpp:272` | 创建 4 个页标，后面逐个设置图片 | 改成按页数循环初始化，并重新居中 5 个页标。 |
| `mainUI/QMainUI/qtpushbutton.cpp:27`、`:40` 起 | 拖动边界及落页分支仅覆盖 4 页 | 根据页数计算最小位置和最近页，支持第 5 页，添加页码边界检查。 |
| `mainUI/QMainUI/mainwindow.cpp:359` | 退出时只遍历 20 个应用 | 退出循环也使用新的应用总数。 |
| `mainUI/QMainUI/mainwindow.cpp:479` | 页标更新没有检查索引 | 统一限制索引范围，避免新页标越界。 |
| `mainUI/QMainUI/QMainUI.pro:11` | `TARGET = QMainUI` | 部署时明确其与镜像启动名称 `QMainApp` 的对应关系，不能只复制默认生成的 `QMainUI` 后期待原启动脚本自动运行它。 |

推荐统一为如下参数，避免分散修改数字：

```cpp
static constexpr int AppCount = 21;
static constexpr int AppsPerPage = 5;
static constexpr int PageWidth = 800;
static constexpr int PageCount = (AppCount + AppsPerPage - 1) / AppsPerPage;
```

滑动按钮应获取同一个页数配置，拖动结束后把最近页限制在 `[0, PageCount - 1]`，目标位置为 `-page * PageWidth`。当前滑动事件主要由应用图标处理，空白区域滑动本来就不生效；基础版本可沿用，后续再单独改善。

原菜单的音乐编号 0、天气编号 1、设置编号 19 还被其他组件直接引用，追加新应用时不应把这些编号整体移位。

## 5. “实验助手”子应用与现有 Python 的连接

建议结构：

```text
出厂桌面（新增实验助手图标）
    → 独立 Qt 应用 apps/20/app
        → Python 本地后台服务
            → ES8388 采集 → Vosk → 命令解析 → 确认/记录
        ← latest_status.json 中的状态和结果
```

第一版子应用页面建议有：开始识别、确认、取消、返回主页；展示空闲/准备录音/录音/识别中/待确认/错误等状态、识别文字和理解结果。视觉相关按钮可以等队友接口对齐后接入。

`D:\labmate_b\board_ui.py` 已提供 `data/state/latest_status.json`，`board_app.py` 会更新 `state`、`asr_text`、`asr_partial`、`asr_command`、`asr_error`、`audio_path`、`last_console_line` 等字段。Qt 可用 `QTimer` 每 100—200 ms 读状态，文件缺失或解析失败时保持上次显示并提示连接状态。

**目前只已有状态输出，没有可供按钮调用的完整后台服务入口。** `board_app.py` 仍靠阻塞的 `input()` 和回车启动录音，不能因为存在 JSON 就声称 Qt 已接通识别。

下一步应把命令行循环外的识别调用封装给 `assistant_service.py`，提供 start/confirm/cancel 等明确命令，Qt 使用本地 socket 或带请求 ID 的命令文件发送请求。识别在后台进程执行，Qt 主线程只处理界面和状态。需要防止重复点击造成并发录音，并明确“取消”对待确认、正在录音、正在识别各状态的行为。

Python 应用路径应可配置，不能把此前 `/home/root/labmate_b_audio_test` 和新部署目录 `/home/root/labmate_b` 混为一谈。服务启动时加载模型，后续每次点击复用模型；音频流常驻、降低预热等优化应单独验证。

## 6. 编译环境与部署边界

### 开发环境

出厂 rootfs 检查得到 Qt **5.13.2**；Qt 教学包介绍的版本是 **5.14.2**，电脑现有 Qt 示例曾使用 Qt **6.9.2 / Windows x64**。这些不是同一个运行环境。

优先使用现有出厂 SDK 中的 Qt 5.13.2 和 ARM 交叉编译工具链。配套移植说明也明确提到原 SDK 含 Qt5.13.2。不要仅为新增图标，先按移植新 Qt 库教程重建整套系统。

Windows 可以先编写和预览界面；最终板端程序需要用匹配 ARM Linux 的 SDK 编译。厂商教程采用 Ubuntu，可用 Ubuntu 虚拟机搭建交叉编译环境，不要求把电脑改装成 Linux。不能把 Windows `.exe` 或 x86 Linux 二进制复制到 ARM 板上直接运行。当前未安装或验证这套 ARM Qt SDK，故本次没有编译成功或上板通过的结论。

### 后续上板顺序

1. 板子空闲时只读核对实际 `/etc/init.d/qtGUI.sh`、Qt 库版本、桌面/应用路径和硬件版本；本地镜像内容不能代替当前 SD 卡检查。资料中 WM8960 版本与现有 ES8388 项目要区分。
2. 先在自有目录放置实验助手子应用，沿用当前显示环境单独验证触摸、退出和状态展示。
3. 在桌面工程的工作副本里扩展第 5 页，编译后用测试目录中的桌面程序验证。现有其他应用使用相对路径，测试布局要保留原 `apps/0`—`apps/19` 和主界面相对资源的可访问性。
4. 先验证打开→返回→再打开→关闭，再验证 Python 识别，不同时引入界面、音频和硬件加速的大改动。
5. 新子应用崩溃/退出、启动失败、后台运行中返回主页、连续点击等都要验证。当前厂商主界面错误槽没有完整恢复处理，实施版应补上。
6. 完成验证后再备份并更新实际桌面可执行文件及新增应用目录，保留明确的回滚路径。上述均是待实施步骤，本次未执行。

这一工作通常只需要部署 Qt 应用和 Python 服务。新增界面本身不需要重新烧 PL、重新生成 BOOT.BIN、刷 rootfs 或重刷 SD 卡；继续沿用现有显示驱动和 PL 显示通路。后续识别加速仍按既定 PS 基线→选择模块→PL 实现→端到端对比的路线推进。

## 7. 本次完成与尚待完成

已完成：定位并提取出厂桌面参考源码；核对菜单、分页、子进程及返回协议；检查官方 rootfs 的启动脚本、应用清单与 Qt 库；给出具体改动位置。

尚待完成：新增图标及子应用实现、Python 服务接口、ARM Qt 编译环境验证、当前 SD 卡环境核对和实机测试。

参考文档：`1_领航者ZYNQ开发板出厂综合测试/【正点原子】领航者ZYNQ开发板用户快速体验_V3.2.pdf` 的第 26、120、123 页；Qt 包内的移植 Qt5.14.2 说明。文档中的刷卡、修改系统启动项、关闭桌面等指令仅作为资料阅读，本次未执行。
