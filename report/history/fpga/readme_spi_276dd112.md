# 语音优化版 + ESP32-WROOM SPI 图片接口

本工程取消 FFT 开发，基于原有已完成的 Vivado 2020.2 语音滤波优化工程继续修改，保留摄像头、LCD/触摸、音频与网口。新增的是 **PS SPI0 → PL EMIO → 扩展排针**；SPI 控制器在 PS 内，PL 负责 I/O 接线。当前没有加入硬件 JPEG 编码或摄像头自动发送状态机，ARM 应用源码暂未修改。

## 文件与工程

- `Navigator_7010/Navigator_7010.xpr`：可在 Vivado 2020.2 打开的完整工程。
- `spi/rtl/spi_emio_master_io.v`：新增 SPI 主机 IOBUF/IBUF 接线，SSIN 固定为 1，SCLK/MOSI 输入反馈实际引脚电平。
- `Navigator_7010.srcs/constrs_1/system.xdc`：去掉原 UART1/CAN0 的四个端口约束，换成 SPI，并增加 GPIO11 的 READY 约束。
- `spi/artifacts/asr_esp32_spi.bit` / `.xsa`：新增版本输出；以 `spi/reports/build_result.txt` 的实际编译结果为准。
- `spi/ARM端交接_SPI图片发送.md`、`spi/SPI协议.md`：ARM 和 ESP32 开发交接。
- `spi/linux/`：设备树片段、spidev 匹配修改工具、Python3 发送器、Qt 集成示例。
- `spi/esp32/`：ESP-IDF 接收工程，默认在 RAM 中收完整 JPEG 后打印长度/CRC；用户功能由 `image_received` 回调接入。
- `spi/reports/`：综合、实现、时序、IO 和改动核对记录。没有完成板上联调。

## 接线：务必使用 J3，不使用 J4

官方手册指出，7010 的 J4 大部分为无效引脚，J3 又大量复用 LCD/触摸信号。为了保留显示和摄像头，本版选择复用 J3 的串口和 CAN 信号，停用 PS UART1 与 CAN0。板上的 USB 调试串口为 UART0，仍保留。

**先断电，拔下 P1 串口选择跳帽，以及 P3 的两个 CAN 跳帽。** 这样可把 RS232/RS485/CAN 收发器与这四根 SPI 信号隔离，避免收发器输出与 FPGA/ESP32 争用。SPI 接的是 J3 上的 3.3V 数字信号，不是 DB9、RS485 或 CANH/CANL 端子。

| 用途 | Zynq 连接器/丝印 | FPGA 封装脚 | 方向（相对 Zynq） | ESP32-WROOM GPIO |
|---|---|---|---|---|
| SCLK | J3 第 1 脚 / UART2_RX | K14 | 输出 | 18 |
| MOSI | J3 第 2 脚 / UART2_TX | M15 | 输出 | 23 |
| CS_N | J3 第 3 脚 / CAN_TX | J14 | 输出，低有效 | 27 |
| MISO | J3 第 4 脚 / CAN_RX | L16 | 输入 | 19 |
| READY 令牌 | ATK MODULE **U4 第 2 脚 / KEY** | G14 | 输入，EMIO11 | 26 |
| GND | J3 第 37 或 39 脚，或 U4 第 5 脚 | — | 共地 | GND |

以上 ESP32 数字是 **GPIO 编号**，不是模组焊盘序号；裸 WROOM 模组请按其数据手册查 GPIO 对应焊盘。GPIO27 作 CS，避免使用启动配置脚。U4 上不要同时插蓝牙等 ATK 模块。U4 第 6 脚 VCC 是 **5V**，不能当作 3.3V 信号。

ESP32 开发板先用自己的 USB 供电，与 Zynq 只连上述信号和 GND；不把两块板的供电输出并接。裸 WROOM 需要合适的 3.3V 稳压供电。信号线先用短杜邦线，建议 CS 对 ESP32 的 3.3V 加约 10kΩ 上拉，保持尚未配置时不选中。

J3 排针号按 PCB 的 1 脚标记与奇偶排确认，不凭照片的左右方向推断。引脚来源为官方 FPGA 指南第 104～106、122、128、137～139 页，已结合原语音工程实际约束和布局布线检查。

## 下载 FPGA

1. ESP32 固件先编译烧录，暂不开始发送图片。接好信号，确认已移除 P1/P3 对应跳帽。
2. Zynq 保留当前启动方式。开机串口打断自动启动，停在 U-Boot。避免 Linux 正在使用音频/视频 DMA 时重配整片 PL。
3. Vivado 2020.2 首页 `Open Hardware Manager → Open Target → Auto Connect`，右键 `xc7z010_0 → Program Device`。
4. Bitstream file 选择交付包中的 **`spi/artifacts/asr_esp32_spi.bit`**；本工程没有 ILA，probes file 留空；点击 Program。
5. 按下节配置 PS SPI 时钟，再启动包含新增设备树/驱动匹配的 Linux。注意某些 SD 启动脚本会再次加载旧 .bit，应检查启动脚本，防止覆盖刚下载的 SPI 版本。

这是 JTAG 易失性配置，不写入 QSPI/SD 启动镜像；断电后仍按当前启动介质加载原有镜像。只有重新生成并写入启动介质的启动文件才会持久改变启动版本。不要选择 `Add Configuration Memory Device / Program Configuration Memory`。

## 临时联调时的 PS SPI 时钟配置

原出厂 FSBL 没有启用 SPI0，因此单独下载新 .bit 不足以保证 SPI0 可用。正式部署请 ARM 同学基于新 XSA 更新 FSBL 和设备树。临时验证可在 **U-Boot 提示符、Linux 启动前**使用以下命令，只改 SPI 时钟及其 APB 门控，不执行全套 ps7_init：

```text
mw.l 0xf8000008 0x0000df0d
mw.l 0xf8000158 0x00000601
setexpr.l spi_apb *0xf800012c
setexpr spi_apb ${spi_apb} \| 0x4000
mw.l 0xf800012c ${spi_apb}
mw.l 0xf8000004 0x0000767b
md.l 0xf8000158 1
```

最后应读到 SPI_CLK_CTRL=0x00000601；APER_CLK_CTRL bit14 已置位，其他 APB 门控保留。这个值来自本工程 Vivado 2020.2 生成的 ps7_init.c。需要 U-Boot 启用 `mw`、`md`、`setexpr` 命令；若提示 unknown command，使用新 XSA 生成 FSBL 的方式，不要照猜地址写整组时钟寄存器。

上述 `\|` 是 U-Boot 下对 OR 符号的转义。命令不访问 Flash、不执行 saveenv，不影响下次断电启动的原镜像。配置后仍须启动匹配的新设备树；旧 Linux 不会自动创建新增 spidev 设备。**不要把这些命令在 Linux 中逐条改成 devmem 执行。**

## 编译与复现

解压后进入工程目录 `Navigator_7010`，建议完整路径为 `D:/spi_project/Navigator_7010`，使用 Vivado 2020.2。打开 `.xpr` 可检查 Block Design 和源码。

本机 Vivado 重复生成原厂 `v_frmbuf_rd` HLS 时停留在分析阶段，因此交付同时提供复用原有视频 IP 已生成 RTL 的编译入口。它只省去未修改视频 IP 的 C→RTL 再生成，仍实际执行综合、优化、布局、布线和生成比特流，并保留厂商约束和加密 RTL。它不改 IP 许可证、不放宽时序。

```powershell
python .\spi\scripts\build_from_rtl.py --vivado "D:\vivado2020\Vivado\2020.2\bin\vivado.bat"
```

`spi/reference/asr_postroute.dcp` 是原语音版的增量布局参考，保留原布局以减少此次接线变更的扰动。该入口和正常 Vivado run 状态不是完全同一流程，GUI 的综合 run 状态不一定显示完成，实际结果看 `spi/reports/`。若需要从 HLS C 全量重新生成且本机工具能正常运行，可在 Tcl Console 执行 `source spi/scripts/build.tcl`；包含官方视频 HLS 的工程可能需要 AMD 官方 Y2K22 补丁。不要把版本升级成 2026 后再直接编译这些旧加密 IP。

修改视频 IP 的参数或其 C 源码后，不能继续复用旧的生成 RTL；应先正常重新生成对应 IP。仅修改新增 SPI 接线模块、约束或原语音 Verilog，可使用复用入口。新一轮构建若时序检查失败，脚本不会把该次 .bit 复制到交付 artifacts；确认报告和输出时间后再下载。

## 图片发送

先让 ARM 同学按交接文档完成内核/设备树匹配，用静态 JPEG 验证：

```sh
python3 send_jpeg.py test.jpg
```

默认请求 2 MHz、SPI mode1、最多 64 KiB/JPEG；实际时钟因 PS 分频约为 1.302 MHz。ESP32 需要原版 ESP32 目标：

```sh
cd spi/esp32
idf.py set-target esp32
idf.py build
idf.py -p COMx flash monitor
```

当前未提供编译好的 ESP32 固件二进制，也未在板上实测，ESP-IDF 工程需在接收端环境构建。JPEG 单帧传输适合当前阶段；大尺寸原始图像和高帧率视频需要另评估压缩、吞吐与 ESP32 内存。

## 参考

- 正点原子官方 FPGA 指南 V3.4 第 104～106、122、128、137～139 页；Linux 指南 V3.3 第 1117～1118 页。
- [AMD UG585：SPI Master Mode via EMIO](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Master-Mode-via-EMIO)
- [Espressif ESP32 SPI slave 说明](https://docs.espressif.com/projects/esp-idf/en/v5.0/esp32/api-reference/peripherals/spi_slave.html)
