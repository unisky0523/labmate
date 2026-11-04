# 实验助手界面：逐步实施记录

### 用户确认真实语音版已在板运行（2026-10-29）

用户更新后反馈“目前功能比较正常”，提供板载屏幕照片：真实语音模式、模型加载与麦克风初始化提示、收音结束后识别、实际文字返回、解析拒绝原因均可见。因此真实麦克风→Vosk→Python→Qt 显示链路已有实机证据，不能继续描述为仅模拟通信。

照片当前轮次明确显示“本轮未通过检查，请重新开始”和未完整理解指令的提示；这证明拒绝原因能显示，不能当作该指令识别正确、确认保存或所有按钮完整验收通过。用户尚未提供固定语料准确率、连续多轮取消/重试结果、记录落盘、桌面图标入口、独立开机启动或 PL 加速验证。下一阶段优先考虑原桌面入口与返回流程，随后按需求接确认保存；保留 PS 实现作为未来 PL 加速对比基准。

### 真实语音接入源码已准备（2026-10-29，待手动更新验收）

用户照片确认模拟版已在板卡显示真实 Qt/Python 进程的结果；串口输出确认关闭助手返回码 0 并恢复出厂桌面。用户随后检查 `/home/root/labmate_b_audio_test`，board_app/board_listen/asr_cli/asr_grammar、libvosk.so 与 models/vosk-model-small-cn-0.22/am/final.mdl 存在，NumPy 导入成功。没有据此声称模型加载或新 GUI 真实识别已经实测通过。

已在 `work/labmate_ui` 实现真实模式接入，保持用户指定原语音源文件不变：冻结所需 Python 副本，独立适配 ContinuousMicrophone/asr_cli.analyze，后台线程复用模型/录音、选择点击后新语音、过滤取消结果；Qt 新增真实模式与进度显示、较长初始化等待和后台正常清理。确认仍仅核对识别结果，不分派实验写入。首次需重新 ARM 编译，之后可用独立后台路径更新 Python。

新启动器 `tools/run_ui_voice.sh` 与 `upload_ui_serial.ps1 -RealAsr` 已准备。本地 20 项后台/适配器测试通过，Python 3.7 语法、脚本解析和打包检查通过，均未用来冒充板端真实录音验证。当前 dist/armhf 中仍是旧模拟二进制，真实上传会检查新程序版本标识防止误部署。本轮未打开 COM6 或接管电脑。用户操作详见 `docs/labmate_ui_real_voice_steps.md`。

### 当前手动上板测试进度（2026-10-29）

COM6 只读实机探测已通过：ARMv7 Linux 5.4.0 / Xilinx 2020.2、Python 3.7.6、Qt 5.13.2、`/dev/fb0` 与电容触摸 event1 均存在。出厂程序 `/opt/qt5/QMainApp` 正在运行；板端没有非 loopback IPv4 地址。完整输出：`tmp/qt_board_environment_probe_20261029.log`。

用户已将 ARM 产物复制至 `dist/armhf/labassistant`，大小 1163696 字节，ELF32 ARM little-endian，SHA256 `7d3c1bb7c5e5a9d5ba6d03e7ea88620a0ea43579bf4c327084e121d12dd658cb`。用户要求自行操作，不使用电脑接管，也不由助手直接操作串口。

新增手动执行的 `tools/upload_ui_serial.ps1`（默认 COM6/115200）及配套接收器 `ui_serial_receiver.py`、启动器 `run_ui_test.sh`。上传器只写 `/home/root/labmate_ui_test`，不启动界面；已有同名测试文件备份后替换。接收时验证压缩包 SHA256、ZIP CRC 和 ARM ELF；终端 echo 在 finally 恢复。启动器临时 SIGTERM 退出确切名称 QMainApp，运行独立测试界面，退出后调用原 qtGUI.sh start 恢复桌面，不使用厂商 stop 中的宽泛 kill -9。

本地 `-PrepareOnly` 验证打包、解包、二进制逐字节一致，约 408KB/354 个串口数据块；接收器通过 Python 3.7 语法解析，PowerShell 解析通过。尚未执行上传脚本的串口传输，也未实测启动器或 LCD，不能将本地检查当作上板通过。下一步用户关闭占用 COM6 的终端，在 Windows PowerShell 手动运行上传器，随后重开串口终端执行 `sh /home/root/labmate_ui_test/run_ui_test.sh`，反馈界面与按钮行为。

开始日期：2026-10-28。用户要求逐步操作和反馈；不再处理语音交接包。

## 目标与路线

现有出厂桌面新增“实验助手”入口，点击打开 800×480 Qt Widgets 子应用，再由它控制板端 Python 识别后台。界面和后台都运行在 PS 的 Linux 用户态，继续使用现有显示与触摸通路。

每阶段达到检查结果后再进入下一阶段，不把未验证的操作当作已完成。

2026-10-28 操作进展：用户已进入安装后的 Ubuntu 18.04.6 桌面，实际用户名 `labmat`。在 Software & Updates 切换至 Main server 后，用户截图确认 bionic、updates、backports、security 四项均 Hit，apt 更新完成且无失败警告。此前多次连接失败的旧镜像源问题已解决。

2026-10-29 已确认：`open-vm-tools-desktop` 的安装日志为 installed；Qt Creator 4.5.2 与 Qt 5.9.5 已安装。后台 unattended-upgrades 曾持续占锁，暂停 apt-daily/apt-daily-upgrade 的 timer 与当前任务后安装完成。`qt5-default` 补齐默认 Qt 选择配置。用户已把工程复制到 Ubuntu，并提供“实验助手 · 界面预览”的实际运行截图：中文、固定 800×480 布局及演示标识可见。第一版已成功编译运行，但三个按钮的逐项验收尚未得到明确反馈。

用户现授权接入 Python 后台通信。已备份第一版至 `backups/labmate_ui_before_python_20261029`，在 `work/labmate_ui` 新增标准库 Python 3.6+ 后台、JSON Lines 请求/响应、请求与轮次编号，以及异步 QProcess 界面。模拟结果由 Python 返回；Qt 的本地模拟计时器已移除。取消、过期确认、进程退出、超时与关闭均有处理，真实麦克风、Vosk 和记录写入仍未接入，界面保持“Python 已连接 · 模拟识别”的明确标识。

本机 9 项 Python 子进程协议测试通过，Python 3.6 语法检查通过。2026-10-29 用户随后提供新版实际运行截图，确认本次 C++ 已在 Ubuntu 编译运行，窗口显示“Python 已连接 · 模拟识别”，日志包含 start 请求、Python 收到请求和结果返回，界面进入待确认状态。当前已完成真实 Qt/Python 进程通信，真实语音和板端部署尚未接入。操作详见 `work/labmate_ui/README.md`。后续上板前仍必须完成 ARM Qt SDK 阶段，不能混用桌面与 ARM 构建产物。

### 最新语音源码基准（用户 2026-10-29 指定）

后续语音接入以 `D:\fpga amd xinlx\labmate_b_board_20261015(1)\labmate_b_board_20261015` 为准；不再用 `D:\labmate_b` 或旧 dist ZIP 推断当前实现。已只读检查入口、采集、词表及识别接口，19 个顶层 Python 运行文件通过 Python 3.7 语法解析。源码哈希见 `docs/labmate_asr_source_baseline.json`，本次未改动该目录运行文件。

实际代码具备 `--continuous` 常驻收音与能量分句；`board_listen.ContinuousMicrophone` 管采集，`asr_cli.analyze` 返回识别/解析结果，`asr_grammar.GRAMMAR_JSON` 提供短语词表。默认句尾静音 0.8 秒、单句上限 12 秒；不据此声称已在板端实测通过。当前运行文件没有 `StreamingTranscriber` 或 `--stream-asr`，目录残留的第二轮说明不能作为启用这些接口的依据。

Qt 接入应调用识别接口、保留硬件采集配置和词表，再由界面确认分派操作；不能直接启动 `board_listen.run` 或 `asr_cli.process`，它们会进入原来的命令执行链。包内 `libvosk.so` 为 ELF32 ARM（machine 40），不能直接在电脑 x86_64 Ubuntu 加载；电脑联调需使用对应平台依赖。板端录音与持续模式退出/取消还需后续单独验证。

### ARM Qt SDK 已安装并验证环境（2026-10-29）

已找到 `tools/sdk.sh`（2052127424 字节）和 `tools/rootfs.manifest`（60904 字节）。只读查看安装脚本，确认标题为 PetaLinux SDK installer version 2020.2，x86_64 宿主，支持 `-d <dir>` 指定安装目录，默认 `/opt/petalinux/2020.2`。环境文件名为 `environment-setup-cortexa9t2hf-neon-xilinx-linux-gnueabi`。配套 manifest 中 qtbase/qtdeclarative 为 5.13.2，架构 cortexa9t2hf_neon，与之前出厂参考镜像对应；仍需实际板端核对。

XZ 尾部与索引 CRC 检查通过，索引记录的解压 tar 大小约 10.21 GiB；本机未对全压缩载荷解压校验。用户随后在 Ubuntu 安装至 `/home/labmat/petalinux_sdk_2020_2`，截图显示安装成功。另一次截图确认 source 环境后 qmake 位于该 SDK 的 `sysroots/x86_64-petalinux-linux/usr/bin/qmake`，Qt 为 5.13.2，库位于 Cortex-A9 目标 sysroot；CC 为 `arm-xilinx-linux-gnueabi-gcc -mthumb -mfpu=neon -mfloat-abi=hard -mcpu=cortex-a9 --sysroot=...`。因此 SDK 已安装且 ARM 环境选择正确。

用户随后提供完整终端日志，确认已在独立目录 `~/labmate_ui_build_arm` 执行 qmake 与 make -j2，ARM C++ 编译、资源编译和 Qt Widgets/Gui/Core 链接均正常完成。`file` 检查生成的 `labassistant` 为 ELF32 LSB ARM、EABI5、动态链接，解释器 `/lib/ld-linux-armhf.so.3`，BuildID `67997b246e3e140154db4d7edd363b5a88b33717`。因此 ARM 构建与架构检查已通过；没有上板运行证据。当前源码的识别仍为模拟数据。

当前下一步：板子空闲后获取板端终端，先只读核对实际 Qt/Python/图形环境，再把 ARM 程序复制到独立测试目录，协调现有出厂 Qt 桌面对 framebuffer/触摸设备的占用，验证显示与后台通信。真实语音适配、桌面入口与开机集成仍待完成。Ubuntu 桌面构建与 ARM 构建不得共用目录。本机没有执行安装器、没有更改板卡或 SD 卡。

| 阶段 | 操作 | 通过标志 |
| --- | --- | --- |
| 1. 电脑环境确认 | 在 VMware 中确认是否已有可启动的 Ubuntu 虚拟机；没有时再准备。 | 可以进入 Ubuntu 桌面并打开终端。 |
| 2. ARM Qt 编译环境 | 使用与现有出厂系统匹配的厂商 SDK，检查编译器、qmake 和 sysroot。 | qmake 指向 ARM 目标配置，编译器可用，Qt 版本与板端对应。 |
| 3. 最小助手窗口 | 新建自己的 Qt 工程，先完成标题、按钮、状态文字与返回逻辑。 | 电脑预览窗口布局正确，按钮用模拟状态反馈，不声称已接通识别。 |
| 4. 板端独立运行 | 板子空闲后核对实际环境，将 ARM 程序放在独立测试目录验证。 | LCD 正常显示，触摸准确，关闭与恢复原桌面可用。 |
| 5. 桌面入口 | 在厂商桌面的工作副本中增加应用 ID 20、第五页和新图标。 | 原有 20 个入口保留，新入口可以打开、返回、再次打开助手。 |
| 6. Python 控制服务 | 将终端输入循环外的识别逻辑封装为服务，提供开始、确认、取消命令。 | 不依赖电脑终端回车即可完成一次请求，模型在服务中复用。 |
| 7. Qt 与 Python 联调 | Qt 按钮发本地请求，读取状态和结果；处理繁忙、错误及退出。 | 在屏幕上完成开始识别→显示文字→确认/取消，界面保持响应。 |
| 8. 固化部署 | 备份后部署验证过的桌面和子应用，最后验证开机进入与回滚。 | 断开电脑后，板载屏幕可独立操作。 |

## 当前环境证据

- 用户回答：不确定有没有 Ubuntu 虚拟机，目前只确定有 VMware 软件。
- 用户随后提供的 VMware Workstation 16 Pro 截图确认：库中只有“我的计算机”，未显示已登记的虚拟机。下一步准备 Ubuntu 安装镜像。
- 2026-10-28 已核对 Ubuntu 官方发布页：Ubuntu 18.04.6 Desktop AMD64 ISO 仍可下载，页面标注大小约 2.3G。使用 18.04 系列是为了匹配厂商说明中的旧 SDK 参考环境。
- 下一步下载地址：`https://releases.ubuntu.com/18.04/ubuntu-18.04.6-desktop-amd64.iso`。当前尚未下载，也未创建或安装虚拟机。
- 当前只读检查得到 D 盘约 120.8 GiB 可用；内存查询未成功，不据此假设电脑内存容量，创建虚拟机分配内存前仍需确认。

### 2026-10-28 下载完成后的确认

- 用户 ISO：`D:\Ubuntu镜像\ubuntu-18.04.6-desktop-amd64.iso`，2514124800 字节。
- SHA256：`f730be589aa1ba923ebe6eca573fa66d09ba14c4c104da2c329df652d42aff11`，与 Ubuntu 官方 `https://releases.ubuntu.com/18.04/SHA256SUMS` 一致。
- 重新只读查询成功：电脑内存约 15.7 GiB，24 个逻辑处理器；D 盘当前约 118.5 GiB 可用。上一条内存查询失败不再作为未知项。
- 创建虚拟机建议：名称 `LabMate-Ubuntu1804`，位置 `D:\Ubuntu虚拟机\LabMate-Ubuntu1804`，Linux / Ubuntu 64 位，内存 4096 MB，1 个处理器 × 2 核，虚拟磁盘最大 60 GB（分为多个文件），NAT 网络；挂载已校验的 ISO。
- 下一步由用户在 VMware 的典型创建向导中操作，先选“稍后安装操作系统”，在自定义硬件中挂载 ISO，创建完成后先反馈摘要截图，再进入 Ubuntu 安装。此处记录为操作指引，尚未确认实际创建成功。
- 用户随后已提供创建成功的配置截图；只读核对 VMX 确认 Ubuntu 64 位、4096 MB、2 个 vCPU（每插槽 2 核）、NAT，挂载 ISO 的实际路径正确且文件存在。虚拟机尚未确认启动或安装成功。
- 当前给用户的下一步：启动虚拟机，选择 English / Install Ubuntu、English (US) 键盘和 Minimal installation，暂不勾选安装期间下载更新与第三方软件；到 Installation type 页面反馈截图后继续核对虚拟磁盘。
- 在常见 VMware 登记位置未找到可据以确认的 Ubuntu 虚拟机记录；这不能证明其他磁盘没有已有虚拟机。
- 电脑旧 Qt 工程记录使用过 `D:/dependency/qt_6_7_2/6.9.2/msvc2022_64`，当前该路径下的 qmake 不存在，因此不能当作可用的现成编译环境。
- 配套出厂 rootfs 的 Qt 为 5.13.2，实际板端当前 SD 卡尚未检查。
- 厂商移植说明明确原 SDK 包含 Qt5.13.2，SDK 来自 PetaLinux2020.2 构建，下载位置为工具盘 B 盘的 `sdk/202002`。Qt5.14.2 移植教程的完整系统移植步骤不是本任务的前置必做项。
- 本地检查的 `zynq_petalinux.rar` 未发现 `sdk.sh`、qmake 或 environment-setup 文件。A 盘源码已齐不等于 ARM Qt SDK 也已经准备好。

## 本轮给用户的第一步

1. 在 Windows 打开 VMware Workstation，查看左侧“库/Library”的虚拟机列表。
2. 如果有名称含 Ubuntu 的虚拟机，选中它，查看中间的信息；先不修改虚拟机硬件设置。
3. 如果列表为空或只有主页，先停留在该页面。
4. 把 VMware 主窗口截图发回，保留左侧列表和中间信息。依据实际状态选择“启动已有 Ubuntu”或“新建虚拟机”的后续步骤。

本阶段不连接开发板，也不修改 SD 卡。后续实际板端路径、Qt 环境和已有进程需在板子空闲时另行核对。

## 后续实施依据

- 出厂源码：`work/vendor_factory_reference/QtDemo/mainUI/QMainUI`。
- 已核实的菜单与返回协议、具体修改点：[出厂桌面新增实验助手入口](labmate_factory_qt_entry_plan.md)。
- 现有 Python 状态输出：`D:\labmate_b\board_ui.py`；当前主入口仍是 `board_app.py`，完整的按钮控制服务尚未实现。
- 不在 Qt 主线程直接运行录音和 Vosk；子应用 stdout 保留给厂商桌面的显示/返回协议，后台日志单独处理。
