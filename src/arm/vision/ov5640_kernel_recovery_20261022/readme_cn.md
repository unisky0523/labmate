# OV5640 / AXI IIC Busy 恢复测试内核构建包

日期：2026-10-22。目标：正点原子领航者 Zynq-7010。当前状态：输入文件已核对，补丁已检查可应用，脚本已做语法检查；尚未在 Linux SDK 中编译，也未上板验证。本包不是已编译的内核镜像。

## 依据与输入

使用板卡导出的 board_kernel_config_20261022.txt（148471 字节），而不是默认 defconfig。实测内核为 5.4.0-xilinx-v2020.2，GCC 9.2.0，SMP PREEMPT；CONFIG_I2C_XILINX=y，驱动内建。完整出厂源码 atk-zynq-linux-xlnx.tar.gz 来自本机配套资料。

厂家《领航者 ZYNQ 之编译出厂镜像文件》第 6、15 页要求在 Linux 主机中使用 2020.2 SDK 编译内核，7010 的设备树目标为 atk-navigator-7010.dtb。本包沿用此构建方式，使用独立输出目录和板卡实际配置。

补丁的范围：XIIC 控制器持续返回 EBUSY 且没有记录为正在执行的 tx_msg 时，调用已有 xiic_reinit() 恢复控制器，再检查 Busy 一次。不是完整上游驱动升级，不保证消除硬件干扰或从设备锁总线。

## 在 Linux 虚拟机执行

把本文件夹完整复制到 Linux 虚拟机主目录，文件夹名保持 ov5640_kernel_recovery_20261022。源码压缩包在 Linux 文件系统内解压，不能在 Windows 或共享 FAT 文件系统内直接构建。

打开虚拟机终端执行：

```sh
cd "$HOME/ov5640_kernel_recovery_20261022"
bash build_kernel.sh --check
bash build_kernel.sh
```

每条单独执行。脚本会寻找此前使用的 SDK：

1. $HOME/tools/xilinx-sdk/2020.2/environment-setup-cortexa9t2hf-neon-xilinx-linux-gnueabi
2. /opt/petalinux/2020.2/environment-setup-cortexa9t2hf-neon-xilinx-linux-gnueabi

如果安装在其他路径，通过 SDK_ENV 指定实际 environment-setup 文件。例如：

```sh
SDK_ENV=/实际SDK目录/environment-setup-cortexa9t2hf-neon-xilinx-linux-gnueabi bash build_kernel.sh
```

脚本会报告缺少的命令。Ubuntu 下所需构建依赖通常为 build-essential、bc、bison、flex、libssl-dev、libelf-dev、python3、perl、patch；SDK 本身必须已经安装。此处列的是依赖名称，不会自动安装软件或改虚拟机配置。

## 构建过程和产物

- 每次在 $HOME/labmate-kernel-build 下建立单独的 xiic-20261022.* 目录，WORK_DIR 会打印实际位置。
- 解压出厂源码、应用补丁、复制实际配置。
- 仅把内核版本后缀改为 -xilinx-v2020.2-af-test-20261022，关闭版本号自动追加；其他配置变化会记录并停止，便于核对编译环境和源码是否匹配。
- 使用 GCC 9.2.0 编译 zImage、7010 设备树和内核模块，默认并行 2 个任务。需要时可使用 JOBS=4 bash build_kernel.sh。
- 模块安装仅安装到构建目录内的 artifacts/modules-root，用于打包；不安装到虚拟机或板卡的 /lib/modules。

成功会显示 BUILD_COMPLETE=实际目录，artifacts 中包含：

- zImage-af-test：候选测试内核。
- atk-navigator-7010-af-test.dtb：由配套源码生成的候选设备树。
- modules-5.4.0-xilinx-v2020.2-af-test-20261022.tar.gz：匹配的模块树。
- kernel.config、Module.symvers、kernel-release.txt、config-changes.txt、SHA256SUMS。

build.log 在 WORK_DIR 内。失败时脚本显示失败行与日志路径；请返回末尾约 60 行。

## 下一步

先检查构建日志、配置差异与产物，再准备一次性启动测试。当前没有板卡 U-Boot 环境和启动文件布局的完整记录，所以本包不提供未经核对的烧写指令。运行脚本不会产生 BOOT.BIN、不格式化 SD、不烧写 QSPI/eMMC、不修改 U-Boot 环境。

当前 SD 卡用于传文件，只有 FAT 项目目录，不能把复制候选 zImage 解释成已经完成系统启动配置。原系统和已有 OCR 程序继续保留。不要运行 /opt/image/burn_qspi.sh。

修复后的对焦用户态程序仍在 SD 卡原 labmate_ov5640_af_test_20261021_v3 目录；版本标识为 20261022_manual。它补上了摄像头手册要求的 0x06 保持位置命令，但尚未上板验证，控制器 Busy 恢复也仍待测试。

## 来源

- 用户板卡导出配置：board_kernel_config_20261022.txt。
- 厂家编译说明：D:/FPGA/【正点原子】领航者ZYNQ之编译出厂镜像文件.pdf。
- AMD Linux I2C 驱动修复记录（包含总线忙时重新初始化的上游修复）：https://xilinx-wiki.atlassian.net/wiki/display/A/Linux%2BI2C%2BDriver
- AMD AXI IIC 软复位说明：https://docs.amd.com/r/en-US/pg090-axi-iic/Soft-Reset-Register-SOFTR

这里只采用与旧驱动适配的实验性恢复步骤；控制器复位后读到 Busy 清零，仍不能单独证明外部线路或摄像头已恢复，后续还必须验证芯片身份、固件读回和实际图片。
