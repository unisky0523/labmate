# 硬件与系统前提

## 板端

当前适配对象为 Zynq-7010、ARMv7 hard-float Cortex-A9 Linux、Python 3.7。仪器通信使用系统 libusb-1.0 与用户态 PyUSB/PyVISA-py；精简 Python 需包含 ctypes、threading、fcntl 等标准模块。包内 typing 回退仅用于精简 Python 缺失标准 typing 时。

相机为 OV5640。原生采集程序面向已有板卡驱动的 `/dev/video0` 与 `/dev/v4l-subdev0`，使用 RGB24、多平面 V4L2、800×480；不是适配任意 USB 摄像头的通用程序。显示屏或其他采集进程不可同时独占相机。

FPGA bitstream、EMIO 约束、GPIO 路由、spidev 设备树与相机驱动由硬件同学提供，本包不生成这些文件。SPI 设备节点由设备树 compatible `labmate,esp32-image-link` 自动发现，现有系统曾使用 `/dev/spidev1.0`；编号可能随设备树改变。

## SPI 连接

实际 ESP32 为 ESP32-D0WD-V3/WROOM 系列，构建板型 `esp32dev`，不是 ESP32-S3。

| 信号 | Zynq 板卡位置 / 封装标号 | ESP32 GPIO |
| --- | --- | --- |
| SCLK | J3-1 / K14 | 18 |
| MOSI | J3-2 / M15 | 23 |
| CS | J3-3 / J14 | 27 |
| MISO | J3-4 / L16 | 19 |
| READY | U4-2 / KEY / G14 | 26 |
| GND | 板卡 GND | GND |

上述为已对接工程的映射，换板或改约束时以该板原理图和实际约束为准。G14 为 FPGA 封装标号，不能当作 ESP32 GPIO14。硬件同学要求的 P1/P3 跳帽状态需要保持一致。两板用 3.3V 逻辑、共地，ESP32 可独立 USB 供电。

协议为 SPI mode 1、1024 字节事务、READY 翻转令牌、帧 CRC32 和 ACK；READY 必须连接。PS GPIO 偏移为 65，现有系统曾显示为 base897 + 65 = gpio962，程序按 gpiochip 自动计算，不能把 962 当作跨系统固定值。

该硬件配置需要运行参数 `--spi-cs-high`。它与 ESP32 从机端实际 CS 波形的关系由已有硬件工程决定，不要直接照搬到其他 SPI 接口。

## 仪器与连接

| 仪器 | 通信路径 |
| --- | --- |
| SUIN SA5041 | 仪器 USB Device → 板卡 USB Host；CP210x，VID/PID 10c4:ea60，9600/8N1 |
| SIGLENT SDS1202X | 仪器 USB Device → 板卡 USB Host；USBTMC/PyVISA-py |
| RIGOL DG4102 | 仪器 USB Device → 板卡物理 HOST2；USBTMC/PyVISA-py，首次绑定真实 USB 路径和序列号 |

HOST2 是板卡物理插口，CH2 是信号源通道，两者没有自动对应关系。软件不能辨认插口上的印字，首次绑定必须由操作者实际插在 HOST2。

CP210x 用户态入口不会强行卸载内核串口驱动；若内核驱动已占用设备，先按系统实际情况选择 ttyUSB 串口路线，并安装 pyserial 3.5。不要让两个进程同时访问一台仪器。
