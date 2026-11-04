# ARM 端交接：摄像头图片经 SPI 发送到 ESP32-WROOM

本次工程以 2020.2 原语音优化版为基础，不含 FFT，摄像头、LCD、音频和网口均保留。现有 ARM 应用未改动。新增硬件是 **PS SPI0 经 PL EMIO 引出**，没有新增 JPEG 编码器或图像算法；SPI 数据搬运由 Linux SPI 驱动执行，不是 PL DMA。

## 1. 数据路径与工作分工

`OV5640 → 原厂 PL 采集/帧缓存 → DDR → Linux V4L2 → ARM JPEG 编码 → spidev → SPI0 EMIO → ESP32-WROOM RAM`

FPGA 改动已经包含在工程中：启用 SPI0/CS0，EMIO GPIO 从 11 位扩至 12 位，新增最后一位 GPIO65 用于接收 READY 令牌，停用占用四个扩展脚的 PS UART1/CAN0。原有 GPIO54～64、AXI 地址、PL 中断连接、视频与音频模块保持一致。USB 调试控制台使用 UART0，不受这次改动影响。

ARM 端负责：让 Linux 枚举 SPI；从现有摄像头链路取得单帧；压缩成 JPEG；异步调用发送器；显示成功/失败。先用现成 JPEG 文件联调，再接摄像头。初期 320×240、JPEG 质量 60、按需发送，不承诺实时视频。

## 2. Linux 设备树和驱动

在当前板卡实际使用的 `system-user.dtsi` 中合入 `linux/esp32-spi.dtsi`。它依赖原设备树的 `spi0`、`uart1`、`can0` 标签，分别对应 e0006000、e0001000、e0008000。核对地址，不能按 `/dev/ttyPS1` 的编号猜 UART 控制器。不要改 UART0/e0000000 的控制台节点，也不要替换整棵原厂设备树。

内核需要 `CONFIG_SPI`、`CONFIG_SPI_CADENCE`、`CONFIG_SPI_SPIDEV`、`CONFIG_GPIO_SYSFS`。如果 spidev 是模块，安装与当前运行内核完全匹配的模块并加载。设备树使用真实兼容串 `labmate,esp32-image-link`，原版 spidev 不会自动匹配：

```sh
python3 add_spidev_match.py /path/to/matching/linux-source
# 用该内核的原配置及工具链重新编译、安装 spidev，或重新编译内核。
```

该脚本只在 `drivers/spi/spidev.c` 的 `spidev_dt_ids[]` 增加一条匹配，并保存源码备份。不能把任意版本编译的 .ko 复制到板卡。较新内核也可用其 `driver_override` 机制临时绑定；交付方案以增加明确匹配为准，不冒用其他芯片的 compatible。

设备树启动成功后 `/sys/bus/spi/devices/spiB.0` 和 `/dev/spidevB.0` 应出现。B 不保证是 0，因为系统可能已有 QSPI 控制器。发送器按 compatible 自动查找，不依赖固定编号。

EMIO11 对应 PS GPIO 控制器线偏移 **65 = 54 + 11**，不是固定 Linux 全局 GPIO65。发送器从 gpiochip 的 base 加 65 导出并设置输入。如果系统关闭 sysfs GPIO，需要打开该选项或将 GPIO 操作替换为当前系统的 libgpiod 接口。

## 3. PS 初始化同样需要匹配

仅改 .bit 不会执行 PS 的时钟初始化。新版 XSA 生成的 `ps7_init.c` 新增 SPI_CLK_CTRL：地址 `0xF8000158`，掩码 `0x3F33`，值 `0x601`，参考时钟约 166.667 MHz；SPI0 APB 时钟需置位 `APER_CLK_CTRL/0xF800012C` 的 bit14。

正式部署建议基于新 XSA 重建 FSBL，并结合现有 U-Boot/设备树生成匹配的启动文件；先用备用 SD 卡验证，再考虑持久更新。不要在已运行 Linux 时调用整套 `ps7_init`，它会重设 DDR/PLL。

如果保留出厂 FSBL 做临时 JTAG 联调，可在 **U-Boot 提示符、Linux 启动前**使用 README 的 SPI 局部时钟初始化命令，然后加载匹配设备树启动。该方法只用于这份 SPI0 配置；不是 Linux 中的 devmem 脚本。

## 4. 发送器

板卡已具备 Python3 时不需要额外 Python 包。复制 `send_jpeg.py`，root 下运行：

```sh
sh check_board.sh
python3 send_jpeg.py /path/to/test.jpg
# 如果希望显式指定：
python3 send_jpeg.py /path/to/test.jpg --spi /dev/spidev1.0 --ready-value /sys/class/gpio/gpioN/value --hz 2000000
```

GPIO N 必须按实际 PS gpiochip base+65 得到。图片需为完整 JPEG，包含 FF D8/FF D9，最大 65536 字节。发送器设置 mode1、8bit、MSB first、CS 低有效，请求 2 MHz；166.667 MHz 参考时钟下实际通常为约 1.302 MHz。可在联调后试请求 4 MHz，实际约 2.604 MHz。真实速度以示波器/逻辑分析仪为准。

每 1024 字节图片组成一个 1056 字节传输；随后一个 32 字节 POLL 获取确认。GPIO 每准备好一个 SPI 事务就翻转一次，发送端按 1、0、1、0 的顺序等令牌，避免漏掉很窄的 READY 脉冲。每个正常数据包有两个事务，因此完成后下一次调用仍从令牌 1 开始。如果中断在半个包，先复位 ESP32 再重试；示例无复杂断点续传/自动重传。

`qt_send_example.cpp` 是现有 Qt 程序取得 QImage 后可调用的集成示例，做 320×240 缩放和 JPEG 编码并运行发送器；请放到工作线程，一次只允许一个发送任务。示例不是摄像头驱动，不假定 V4L2 输出的原始像素格式；需要在采集处按实际 fourcc/stride 转为 QImage。原厂摄像头若正由预览程序独占，需要由同一采集线程分享帧，不能同时开两个采集者。

## 5. ESP32 固件和协议

ESP-IDF 工程在 `esp32/`，目标为原版 `esp32`，建议 ESP-IDF 5.x。SPI3 从机 GPIO18/23/19/27、READY GPIO26，DMA，mode1。GPIO27 作 CS，避开 GPIO5/12 等启动配置引脚。标准 WROOM 不依赖 PSRAM；示例仅分配 64 KiB 图片缓存和两个约 1 KiB DMA 缓存，没有 Wi-Fi/显示模块。

完整图片通过 `image_received(jpeg,size)` 回调交给下一模块；默认仅在串口打印长度和 CRC。**默认固件不会自动显示图片、发送 Wi-Fi 或保存 Flash。** 对回调的消费须同步完成或复制到自己的缓存，下一帧会覆盖原图片。Wi-Fi 等功能接入后要重新评估剩余堆内存和吞吐。

详细字段见 `SPI协议.md`。发送端只在收到 ESP32 的完整帧 CRC 成功确认后报告 delivered；CRC 错误会停止，不伪装成功。

## 6. 联调顺序与验收

1. 接线前断电，拔 P1 串口选择跳帽、P3 两个 CAN 跳帽；U4 不插其他模块；ESP32 独立 USB 供电并共地。
2. ESP32 编译烧录完成；Zynq 暂停在 U-Boot，经 JTAG 下载新增 .bit，按需配置 SPI 时钟，再用匹配的设备树启动 Linux。
3. 确认原有触摸界面、语音输入/播报、摄像头采集仍可用。
4. 发送 10～30 KiB 测试 JPEG。两端 CRC、长度一致，SPI mode1/CS/令牌实测正确。
5. 再接摄像头单帧；记录采集、JPEG 编码、SPI 发送各自耗时。

工程和协议主机测试不等于板上验证。当前缺少实际运行的 dtb/image.ub、内核配置和 ESP-IDF 环境，交付包含设备树片段、驱动匹配修改工具与接收源码，不能声称已经替换了板卡 Linux 或完成端到端实测。

## 7. 参考

- 正点原子《领航者 ZYNQ 之 FPGA 开发指南 V3.4》第 106、122、128、137～139 页：引脚、串口/CAN 跳帽、ATK MODULE、J3/J4。
- 正点原子《领航者 ZYNQ 之嵌入式 Linux 开发指南 V3.3》第 1117～1118 页：SPI 使能和设备树从设备。
- [ESP32 SPI slave 官方说明](https://docs.espressif.com/projects/esp-idf/en/v5.0/esp32/api-reference/peripherals/spi_slave.html)：GPIO 握手、DMA 对齐和 mode1/3 限制。
- [Linux v5.4 spidev 源码](https://github.com/torvalds/linux/blob/v5.4/drivers/spi/spidev.c)：设备匹配与 ioctl 接口。
