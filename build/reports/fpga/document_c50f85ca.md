# SPI 版本验证结果（2026-11-04）

- 基线：D:/a20b_1102/Navigator_7010，原始语音优化且保留摄像头的版本；未使用 FFT 或删摄像头工程。
- 变更：启用 PS SPI0 EMIO、GPIO 追加 EMIO11、停用 PS UART1/CAN0、新增 SPI I/O 接线。AXI 地址完全一致；原有 component 中仅 PS 配置发生变化。
- 音频 RTL、滤波系数逐字节一致，BYPASS=0；摄像头、显示、网络 IP 配置和连接保留。原视频读写缓存 64 个 HDL/初始化文件与基线逐字节一致。
- 使用 Vivado 2020.2，复用未改动的视频生成 RTL，实际完成综合、优化、增量布局、布线、后布线优化与 write_bitstream。原 HLS 再生成在 v_frmbuf_rd 分析阶段停留，未用其未完成输出替换基线 RTL。
- 最终 LUT 12418/17600（70.56%，比原版多4）；FF 21261/35200（60.40%）；BRAM 12.5/60；DSP 7/80；占用 Slice 4392/4400（99.82%）。新增 SPI 并未显著增加 PL 算力消耗。
- 已约束内部路径 setup slack=+0.135 ns、hold slack=+0.029 ns。原工程已有的无效 HDMI 约束、缓冲/BRAM 管线等警告保留；没有通过降低 DRC 严重性或新增 false path 来通过检查。
- SPI 引脚、电平及 SSIN 常量在最终设计中复核；板外信号时序及线缆影响仍需实测。此次不承诺高帧率视频。
- Python 发送包与实际 ESP32 C 解析核心互测 79 项：多块、尾块、64 KiB 边界、乱序、越界、CRC 和 ACK 错误；逐字节重组一致。C 核心经 MinGW 原生及 ARM Linux 编译器检查通过，均启用 -Wall -Wextra -Werror。
- ESP-IDF 完整固件尚未构建；没有对实际板卡下载、改写启动介质或完成端到端传图。Linux 仍需合入设备树、匹配 spidev 并配置 PS SPI 时钟。

详细依据：source_audit.json、utilization.rpt、timing.rpt、drc.rpt、io.rpt、构建日志。

## 复现协议测试

安装本机 C 编译器和 Python3，在工程 spi 目录下：

```sh
gcc -shared -O2 -std=c11 -Wall -Wextra -Werror -o tests/image_protocol.dll esp32/main/image_protocol.c
python tests/test_protocol.py tests/image_protocol.dll
```

Windows 使用 MinGW；Linux 可把输出名改成 .so。提供的 tests/test_320x240.jpg 为生成的彩条测试图，可用于真实链路首轮验证。

- 最终 ZIP 实际解压到 D:/spi_verify1104 后使用 Vivado 打开成功；检查 701 项工程文件，缺失 0 项。SPI0=EMIO，UART0 保留，UART1/CAN0 禁用，GPIO宽度12；摄像头/LCD/语音模块均存在。
