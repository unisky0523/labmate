# 构建与依赖

以下为开发和部署所需工具，不是电脑端仪器验证流程。现有 ARM 采集程序和 SPI-EMIO 固件已经随包提供；修改对应源码后必须重新构建。

## ARM 原生采集

使用 Zig 0.13.0，目标 `arm-linux-musleabihf`、Cortex-A9、静态链接。执行：

```sh
python3 c_camera_link/native/build.py --zig /path/to/zig
```

生成 `camera_jpeg_stream_armv7`、`camera_stream_armv7`、`ppm_to_jpeg_armv7` 和构建清单。最终高帧率预览使用第一个，另外两个为保留的原生采集/编码内部兼容路径。JPEG 编码使用保留原始许可的 stb_image_write，固定提交 `1ee679ca2ef753a528db5ba6801e1067b40481b8`。

程序静态链接 musl，避免依赖目标系统的 glibc 版本。它仍依赖正确的板卡内核 V4L2 驱动及格式支持。

## ESP32

构建配置已固定 PlatformIO 平台 `espressif32@6.9.0`、板型 `esp32dev`、Arduino 框架及 ArduinoJson `6.21.5`。只提供最终环境 `esp32dev_spi_emio`：

```sh
pio run -d c_camera_link/esp32 -e esp32dev_spi_emio
```

开发者自行安装 PlatformIO 及其工具链。构建目录默认为 `c_camera_link/esp32/.pio/build/esp32dev_spi_emio`。可直接通过 PlatformIO 烧录，或合并为本包部署脚本使用的镜像：

```sh
python3 tools/merge_firmware.py --build-dir c_camera_link/esp32/.pio/build/esp32dev_spi_emio --framework-dir /path/to/framework-arduinoespressif32
```

合并工具需要 esptool 4.5.1，生成 `c_camera_link/firmware/spi-emio.bin` 及摘要清单，不会自动烧录。合并镜像包含 bootloader、分区表、boot_app0、应用，烧录偏移为 0，DIO/40MHz/4MB：

```sh
python3 -m c_camera_link.flash --port PORT --confirm-overwrite
```

PORT 替换为实际设备端口；若自动进入下载模式失败，按 ESP32 BOOT/EN 操作进入下载模式后重试。烧录会覆盖原 ESP32 应用。改变网页后必须重建并烧录，网页被嵌入固件，不是单独复制网页就能更新。

## 仪器依赖

离线 Python 依赖已展开在 `c_instrument/vendor`，版本记录于 `requirements-scope-board.txt`。系统必须提供 libusb-1.0 和可访问的 USB Host。纯 Python 依赖不包含 libusb 原生共享库，不包含内核驱动。

包内保留各 dependency 的 dist-info 元数据及许可证。ttyUSB 串口替代路线另需 pyserial==3.5；已采用的 CP210x 用户态路径不需要 pyserial。板端不需要 NI-VISA。

## OCR：必须匹配板卡 SDK 重编译

OCR 提供 PP-OCRv5 mobile det/rec 的 Paddle-Lite `.nb`、alphabet、ARMv7hf Paddle-Lite 运行库和 C++ 接口头文件。旧 smoke_infer 对工厂 rootfs 的 GLIBC 版本要求不匹配，**本包没有放入旧二进制**。

用板卡匹配的 ARMv7 hard-float C++ 编译器与 sysroot，创建本地 CMake toolchain 文件。不要只装最新通用交叉编译器就假定兼容。配置示例：

```sh
cmake -S c_vision_lite -B build/ocr \
  -DCMAKE_TOOLCHAIN_FILE=/path/to/board-toolchain.cmake \
  -DLITE_CXX_DIR="$PWD/c_vision_lite/runtime" \
  -DLITE_LIBRARY_DIR="$PWD/c_vision_lite/assets"
cmake --build build/ocr --target smoke_infer -j2
cp build/ocr/smoke_infer c_vision_lite/assets/smoke_infer
```

`BUILD_IMAGE_PROBE=OFF` 默认关闭独立图像探针，不需要为主推理程序引入 C++ OpenCV。板端 Python 前后处理仍需 numpy、cv2、pyclipper，版本应由板端 Python/ABI 与系统镜像决定，不能安装 Windows wheel。

在板端先检查：

```sh
python3 -c 'import numpy, cv2, pyclipper'
LD_LIBRARY_PATH="$PWD/c_vision_lite/assets${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ldd c_vision_lite/assets/smoke_infer
ldd c_vision_lite/assets/libpaddle_light_api_shared.so
```

所有依赖必须可解析，可能还需系统 libgomp；两个 ELF 均需确认 ARMv7hf、加载器与 GLIBC/GLIBCXX 版本兼容。不要替换板卡 libc 或动态加载器来绕过错误。若运行库本身不兼容，也需以同一 SDK 重建 Paddle-Lite。

最后用保存的原始照片验证定位、读数、单位、失败拒绝行为和内存占用，再接入业务层。当前配置只覆盖原先 Keysight 界面布局，不能直接视为所有仪表画面的通用识别。

## 重新打包

修改源码或构建输出后，先复核对应功能，再运行 `python3 tools/repack.py`。工具更新全文件 SHA256 清单，并在目录外生成 ZIP；不会访问硬件。不要把本地构建缓存、运行结果或实际仪器绑定一并提交。
