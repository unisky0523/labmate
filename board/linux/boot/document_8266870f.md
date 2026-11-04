# SPI 正式部署记录 — 2026-11-04

状态：部署完成，已实测重启后不打断 U-Boot，自动从 QSPI 启动脚本进入 eMMC 新版本 Linux。

## 当前自动启动结构

- QSPI 原 FSBL/U-Boot 保留；仅更新 /dev/mtd3（boot.scr，偏移 0xd20000，分区 0x20000）。
- 新 FPGA、内核、设备树存放在 eMMC 根分区 /boot/spi-20261104/。
- QSPI 脚本读取上述文件，加载 FPGA，通过已验证的 PS-PL post_config/SPI 时钟设置后 bootz 新内核。
- 根文件系统继续使用 /dev/mmcblk1p1；底层启动不依赖 SD 卡或 JTAG。
- /etc/rcS.d/S40labmate-spi 自动运行 /usr/local/lib/labmate-spi-init.py，按 compatible 找到 SPI，设 mode1/8bit，按 PS GPIO base+65 导出 READY 为输入。没有自动发送 SPI 数据。
- P1、P3 四只跳帽继续保持拔下。

## 重启后实际核验

- 内核：5.4.0-xilinx-v2020.2-spi-test-20261104。
- /dev/spidev1.0 存在，对应 labmate,esp32-image-link。
- 仅执行读取 ioctl，确认自动初始化后的 SPI mode=1。
- READY=/sys/class/gpio/gpio962/value，direction=in；初始化程序每次按实际 PS GPIO base 动态计算编号。
- /dev/video0、/dev/fb0 存在。未据此声称摄像头、显示和音频完整回归通过。
- FPGA、内核、设备树的 SHA256 与电脑端一致。
- 此轮没有重新发送图片；队友 C 已验证的发送程序保留在 SD 卡原目录。C 使用自己的协议，与初始 send_jpeg.py 不兼容，不要替换为初始发送器。
- 已验证软件重启自动启动；未执行物理断电再上电验证。

## 队友 C 的程序

原目录 /media/sd-mmcblk0p1/labmate_spi_cs_test_20261104/c_camera_link/ 保持不变，继续按 C 已跑通的命令运行。
本次仅配置底层设备开机就绪，不自动启动摄像头发送任务。该应用仍位于 SD 卡，运行它需要 SD 卡。

## 原版本备份与回退

板卡 eMMC：/home/root/spi_boot_backup_20261104/
SD 副本：/media/sd-mmcblk0p1/spi_boot_backup_20261104/
电脑端启动脚本完整分区：factory-boot-script-partition.bin（同本记录目录）。

备份包括 mtd0.bin（FSBL/U-Boot/原 FPGA）、mtd1.bin（环境）、mtd2.bin（原 image.ub）、mtd3.bin（原启动脚本）和 SHA256.json。
本次 mtd0、mtd1、mtd2 完全未变；写入后逐一读取 SHA256 确认。

如明确需要恢复原启动，在板卡运行以下命令；该命令会恢复 QSPI 原启动脚本并停用新增 SPI 初始化服务，随后手动重启：

```sh
sh /home/root/spi_boot_backup_20261104/rollback-factory.sh
sync
reboot
```

回退脚本已保存，未实际执行回退。原内核和原启动文件一直保留。

## 核验文件

- backup.log：原分区备份与 SHA256 核验。
- check_uboot.log：ext4load/fpga 支持、脚本头部及 CRC 核验。
- trial_boot.log：正式写入前从 RAM 试执行脚本进入新内核。
- install_init.log：初始化服务安装和手动验证。
- flash_boot_script.log：flashcp 写入并回读，原三个分区 SHA256 不变。
- autoboot.log：未手动干预的 QSPI→eMMC SPI 自动启动。
- final_check.log：自动启动后的 mode1、READY 输入、内核、文件 SHA256。

新 boot.scr SHA256：134690eefbcd3672ff805ea6aa7a83f00aa1433fed349abf767bee30229169b4。
写入后整个 mtd3 分区 SHA256：707e1cc28edfaa070de61253dc2bee8f5b227347870e69771d883a22c906f5f2。
原 mtd3 SHA256：0ab06ec02ee5b1866c45180085041eb0a839f53f0e6ab535ce83bb20e26bf323。

## 依据

部署使用的 ext4load、fpga loadb、source 均在本板 U-Boot 2020.01 中实际检查并运行。相关官方说明：
- https://docs.u-boot-project.org/en/stable/usage/filesystems/ext4.html
- https://docs.u-boot-project.org/en/v2023.04/usage/cmd/source.html
- https://xilinx-wiki.atlassian.net/wiki/spaces/A/pages/18841750/Solution+Zynq+PL+Programming
