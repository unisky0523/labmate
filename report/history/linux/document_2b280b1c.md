# SPI 内核离线编译包

使用之前编译 ARM Qt 程序的 Ubuntu 18.04 x86_64 虚拟机，解压后运行 `bash build_spi.sh`。脚本优先使用同一个 `/home/labmat/petalinux_sdk_2020_2` SDK，无需重新配置交叉编译器路径。

## 已包含的材料

- 厂家 Linux 5.4.0 源码，SHA256：`371ad957e55c2e37ff571ae16de4444d7ebd48c687d4df0266dc25b1671ea005`。
- 这块板 2026-10-22 导出的历史内核配置，SHA256：`f6825a71f3d5ce0e12780a67c9881605d3e43efe5e3ca55a9269c11afc533d9d`。
- 用户提供的 `ARM_SPI交接包_20261104.zip` 全部内容，保存在 `handoff/`，原始字节保留。12 项自带 SHA256 全部核对通过。
- `runtime/` 是原交付 Linux 文件和测试图片的可运行副本；文本换行统一为 LF，协议和发送逻辑保持原样。
- 新增的宿主机工具与开发库来自 Ubuntu 官方 bionic、bionic-updates、bionic-security 软件源，43 个 deb 约 11 MB，下载时按官方 Release/Packages 索引逐项验证 SHA256。索引来源与每个包的版本、下载路径和校验值见 `offline-host-tools/manifest.json`。

## 自动构建的内容

脚本在 Ubuntu 主目录下创建独立的构建目录，解压干净源码，保留厂家设备树中的摄像头、LCD、触摸、音频和网络节点，再合入用户提供的 SPI 片段。额外将 PS GPIO 的 EMIO 宽度设置为 XSA 对应的 12 位，并采用本工作区已记录的 eMMC 根分区 `mmcblk1p1`。

沿用板卡配置，启用 spidev，并增加 `labmate,esp32-image-link` 的明确驱动匹配。候选内核使用独立版本号 `5.4.0-xilinx-v2020.2-spi-test-20261104`，同时构建对应模块。

宿主机依赖通过 `dpkg-deb -x` 解压到用户缓存，供本次构建使用；不运行包安装脚本，也不替换 Ubuntu 系统中的包。它沿用之前 ARM 编译环境已有的 gcc/g++、make、Python3、Perl、dpkg-deb 等基础工具，不需要 sudo 或联网安装新增依赖。

构建成功时校验 ARM ELF/zImage/uImage 格式、uImage CRC、SPI/UART/CAN/GPIO 设备树属性和模块版本，并生成：

```text
output/spi_board_files_20261104.tar.gz
output/verification.txt
output/build.log
output/SHA256SUMS
```

结果压缩包包含 `zImage`、`uImage`、`system-spi.dtb`、匹配模块压缩包、原 FPGA bit/XSA、图片发送脚本和测试图。编译产物应先通过当前 U-Boot 启动链进行临时启动验证，再确定正式部署方式。

## XSA 与部署依据

XSA 内嵌的 bitstream 与单独交付的 `.bit` SHA256 完全相同：`fe6441ea9548626e3a02e8cc8a191c8bb75924bf7d6bc0726c7f5be48c0878fb`。

已直接核对 XSA 中 `ps7_init.c` 的 SPI 时钟初始化：SPI_CLK_CTRL 写入掩码 `0x3F33`、值 `0x601`；APER_CLK_CTRL 的 bit14 被启用。`boot/uboot_spi_clock.txt` 保留交付说明中的 U-Boot 临时命令。新 XSA 可供后续在 Vitis 2020.2 中生成 FSBL；本次 Ubuntu 内核构建不会自动生成或烧写 BOOT.BIN。

当前没有本轮实机导出的运行 DTB 和 U-Boot 环境，输出设备树是针对已知原工程基线的候选版本。根分区和 U-Boot 的 bootargs 在部署时仍要核对。编译流程不操作开发板。

ESP32 固件工程不在用户提供的 ARM 轻量包中，需要接收端提供。它不影响 Zynq 内核编译，但实际传图时必须运行匹配协议的 ESP32 接收固件。

## 检查状态

本机完成的准备检查另见 `VALIDATION.json`。未在 Ubuntu 实际执行构建时，不能将打包完成或脚本检查通过称为内核编译成功；未上板时也不能称为端到端传图成功。脚本只有实际编译和产物检查通过才输出 `BUILD_OK`。
