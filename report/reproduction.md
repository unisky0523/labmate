# 编译、检查与部署复现

## 归档校验和源码准备

根目录的所有路径已按小写英文归档。`build/source_map.json` 逐文件记录来源、归档位置、原始恢复路径和 SHA256；源文件正文保持原始字节。原始工具可能依赖大小写敏感文件名，所以先恢复到交付目录之外的独立工作区。

```sh
python -B build/verify_package.py
python -B build/prepare.py --out /path/to/labmate_repro --component all
```

`prepare.py` 不覆盖内容不同的已有文件；再次运行相同副本是幂等的。可只选 `arm`、`fpga`、`linux`、`vision`、`board` 、`boot` 、`board_modules` 或 `skill`。以下所有 `/path/to/labmate_repro` 均替换为同一个实际路径，建议使用无空格英文路径。

## 本次离线检查

Python 需具备 NumPy。本次使用 Windows Python 3.14.4 / NumPy 2.5.3，复现脚本兼容常见 Python 3 环境；板端应用沿用原有 Python/Qt 环境。

```sh
python -B sim/run_checks.py --workspace /path/to/labmate_repro
```

脚本恢复 ARM 工作区，运行现有 Qt/ARM 181 项、DG4102 17 项、语音命令行 22 项检查。结果写入 `sim/results/`；需要保留本次交付日志时，增加 `--out /path/to/new_results`。检查使用模拟依赖与临时目录，不访问板卡和仪器。测试临时目录设置在外部工作区，避免受系统临时目录权限影响。

已有源码自身的测试入口仍可在恢复后的 `arm/` 中使用：

```sh
python -B -m unittest discover -s work/labmate_ui/tests -v
```

## Qt/ARM 交叉编译

使用原工程已采用的 PetaLinux 2020.2 Cortex-A9 hard-float SDK 与 Qt 5.13.2。SDK 安装器、操作系统和全套 Vivado 安装不随源码重复打包。设置已安装 SDK 的实际路径后执行：

```sh
export LABMATE_SDK_ENV=/home/labmat/petalinux_sdk_2020_2/environment-setup-cortexa9t2hf-neon-xilinx-linux-gnueabi
bash build/build_arm.sh /path/to/labmate_repro
```

脚本分别编译助手 `labassistant.pro` 和桌面 `QMainUI.pro`，输出到外部工作区 `arm/dist/armhf/labassistant` 与 `arm/work/desktop_entry_20261102/QMainApp`。交付的 `board/arm/bin/` 是已有二进制，本次整理没有重新交叉编译。

## FPGA 构建

使用 **Vivado 2020.2**，准备 `fpga` 工作区后运行：

```powershell
python -B build/build_fpga.py --workspace D:/labmate_repro --vivado D:/xilinx/vivado/2020.2/bin/vivado.bat
```

Linux 示例：

```sh
python3 -B build/build_fpga.py --workspace /path/to/labmate_repro --vivado /tools/xilinx/vivado/2020.2/bin/vivado
```

工具路径仅为示例，必须指向实际安装位置。脚本调用原 `spi/scripts/build_from_rtl.py`，沿用已交付的视频 IP 生成 RTL，在外部工作区运行综合和实现。新结果位于 `fpga/Navigator_7010/spi/artifacts/` 与 `spi/reports/`；归档原报告在 `build/reports/fpga/`。

GUI 入口为准备后的 `fpga/Navigator_7010/Navigator_7010.xpr`。需要从 HLS 源重新生成旧视频 IP 时，参照原 `spi/scripts/build.tcl` 及其工具依赖说明。本次没有重新执行耗时的完整综合实现，也没有进行 JTAG 下载。

## Linux 内核构建

在已用于 ARM 构建的 Ubuntu 18.04 x86_64/匹配 SDK 环境中，先准备 `linux` 工作区，再运行原离线构建脚本：

```sh
cd /path/to/labmate_repro/linux/linux_kit
bash build_spi.sh --check
bash build_spi.sh
```

原脚本使用 `/home/labmat/petalinux_sdk_2020_2`，其他安装位置请使用其支持的 `SDK_ENV` 环境变量。脚本包含完整源码解包、原板配置检查、spidev 匹配补丁、板级 DTS 合并、内核与模块构建、镜像和 DTB 校验。`source/` 与 `offline-host-tools/` 将按映射恢复；内核源码已换为去除编辑器缓存的 `.tar.xz`，配套脚本和 `INPUT_SHA256SUMS` 已更新并逐项校验。

现有构建产物已经放在 `board/linux/artifacts/`，可用于评审和比较；产物对应的内核版本、配置差异、模块匹配和 CRC 验证输出一并保留。完整构建仍须在匹配 Linux 工具链中执行，本次只复核已有文件及本地离线测试。


## 首次运行真实语音前获取模型

先按上文准备工作区，再运行：

```sh
python -B build/fetch_dependencies.py --workspace /path/to/labmate_repro
```

脚本获取官方 `vosk-model-small-cn-0.22`，逐文件核对本项目原模型的 14 项 SHA256；然后放入工作区的 `arm/assets/voice/models/`。模型来源见 [Vosk 官方模型列表](https://alphacephei.com/vosk/models)。若已有完整备份，可离线复用：

```sh
python -B build/fetch_dependencies.py --workspace /path/to/labmate_repro --from-full /path/to/full_labmate
```

也可用 `--model-archive /path/to/vosk-model-small-cn-0.22.zip` 指定已下载 ZIP。离线单元检查使用模拟依赖，不必先下载模型。完成模型准备后，按部署说明把 `arm/assets/voice/` 放入既定板端模型位置。

## 板端运行位置和依赖

既有部署采用以下路径，准备副本不等于已经安装到板卡：

| 板端位置 | 交付来源 |
| --- | --- |
| `/home/root/labmate_ui_test` | 准备后的 `arm/work/labmate_ui/`，配套现有 ARM 程序及启动脚本。 |
| `/home/root/labmate_b_audio_test` | 准备后的 `arm/assets/voice/`，包含模型、libvosk.so 和 libatomic。 |
| `/opt/qt5/QMainApp` | 准备后的桌面二进制；原桌面安装器负责校验和备份。 |
| SD 卡 `labmate_sa5041_board`、`labmate_sds1202x_board` | 准备后的 `arm/instruments/`，路径由 `instruments.json` 指定。 |
| `/home/root/labmate_ui_test/dg4102_driver` | 正式 UI 源码内的发生器模块与 vendor 依赖。 |
| `/boot/spi-20261104` | 已有 SPI 启动日志使用的 FPGA、内核和 DTB 位置。 |

板卡需已有 Qt/触屏环境、Python/NumPy、ALSA 工具、I2C 工具及匹配的内核模块。随包 ARM wheel 和原生库是补充依赖，不能将 Windows NumPy 直接复制到 ARM。`board/arm/settings/` 保存已有冻结版本的配置和模板；恢复配置前先备份当前板卡数据，按实际设备身份核对。

启动链为 `run_ui_desktop.sh -> run_ui_instruments.sh -> run_ui_voice.sh -> run_ui_test.sh`。从已安装桌面进入实验助手，或在板卡相应目录按原启动脚本运行。退出后按原桌面子进程逻辑返回桌面。

串口部署工具已收录在 `board/arm/tools/`，恢复后位于 `arm/tools/`。这些脚本针对已有板卡布局和指定更新模式；评审复现应先核对所选模块、备份路径及脚本帮助，不把普通应用更新和内核/启动更新混为同一步。较早版本的上传参数只证明当时范围，不代表它会自动部署后来新增的所有模块。

`board/linux/boot/` 包含曾实际使用的启动、备份和回退材料；其中既有写入脚本仅作归档。**本次整理没有运行刷写、重启、仪器控制或向他人发送文件的操作。**

## ASR 和 FFT 数据复现

```sh
python -B sim/analyze_asr.py data/asr_response_measurements.csv
python -B sim/analyze_asr.py data/asr_measurement_template.csv
```

第一条直接统计用户确认的十组手动实测，输出两组中位数及约 71.3% 的中位耗时降幅；第二条供后续追加复测使用，空表返回零个有效配对。已测数据标记 `measurement_method=manual`、`status=measured`，来源指向实测日志；后续记录按实际情况填写计时方法、识别状态和附件。

FFT 的原始参考工具使用方法见 `python sim/fft_reference.py --help`；输入输出向量在 `data/fft_vectors/`。软件参考只用于数值比较；真实 PL worker 接口、缩放/溢出及 DMA 规则详见文档索引中的 FFT 交接说明。


## 本轮补齐的 ESP32、网页与板端模块

本轮交接统一恢复为工作区的 `board_modules/`，可选 `--component board_modules`，也包含在 `--component all` 中。完整目录、构建和首次联调入口见 [ESP32 与网页说明](board_modules/readme.md)。

```sh
python -B build/prepare.py --out /path/to/labmate_repro --component board_modules
python -B sim/check_board_modules.py --workspace /path/to/labmate_repro --out /path/to/board_module_checks.json
cd /path/to/labmate_repro/board_modules
python3 -B tools/repack.py --verify
pio run -d c_camera_link/esp32 -e esp32dev_spi_emio
```

`src/web/camera_preview/index.html` 恢复到 `c_camera_link/esp32/web/index.html` 并嵌入固件。`board/esp32/` 的合并固件和 `board/arm/camera/` 的三个 ARM 程序同样自动恢复到原部署位置；同字节的 OCR 模型和依赖通过映射复用。

首次联调使用新 `c_camera_link/run_spi_emio_board.sh --spi-cs-high --preview --ten-fps --count 0`，该预设请求 4 MHz。现有设备树上限 4 MHz，队员的 `--max-fps` 请求 8 MHz，采用该模式前需同步配置并实测。旧内核交接的 `send_jpeg.py` 与本轮固件封包不兼容，保留作历史参考。

原 Qt 的仪器调用与新 `board_modules` 交接源码分别保留；本轮是材料合并，没有把新增模块自动部署到板卡或重写现有业务。OCR 仍需目标 SDK 重编译和板端验收，整机冷启动和最终固件现场复核仍待完成。


## FPGA 技能包复现

使用 `python -B build/prepare.py --out /path/to/labmate_repro --component skill` 恢复三个技能。参照 `skill/readme.md` 执行 XSim、报告审计和 PYNQ 离线快照检查；重新生成 FIR 系数/向量才需要 NumPy 与 SciPy。真实报告审计的预期退出码为 2，原因是约束覆盖需要人工复核。
