# ESP32、网页与板端模块整理说明

本轮材料来自队员的 `labmate_board_modules_20261104.zip` 与配套 `README.md`，已合并到桌面标准工程。源文件按小写英文路径归档；构建前通过 `build/prepare.py --component board_modules` 恢复完整原始目录及大小写。195 个交接文件均有映射，其中原始清单覆盖 194 个负载文件。

## 放置位置

| 标准目录 | 内容 |
| --- | --- |
| `src/esp32/camera_link/platformio.ini`、`src/esp32/camera_link/src/main.cpp` | ESP32-D0WD-V3/WROOM 的 Arduino/PlatformIO 固件源码，SPI 接收、CRC、ACK、热点及 HTTP 服务。 |
| `src/web/camera_preview/index.html` | 固件内嵌的完整网页，实时画面、冻结、箭头/框选、撤销、清空及 PNG 保存；样式和脚本均在该 HTML 内。 |
| `src/arm/board_modules/` | 配套 V4L2/JPEG 采集、SPI 发送、自启、更新的仪器包装和 OCR 源码。 |
| `board/esp32/` | 已提供的合并固件 `spi-emio.bin` 和摘要清单，烧录偏移 0。 |
| `board/arm/camera/` | 三个静态 ELF32 ARM 采集/编码程序。 |
| `build/board_modules/` | 原固件合并与交接清单检查工具，运行前按映射恢复。 |
| `report/board_modules/` | 原交接文档、状态、接口、构建、部署和第三方许可。 |

模型、原生库及 vendor 文件与现有工程逐字节相同时复用一份，所有原路径仍由 `build/source_map.json` 恢复；没有删除交接清单中的内容。当前 Qt 应用沿用其既有配置，新交接模块作为独立 `board_modules/` 工作区保留，未将未联调的 OCR 或网页强行声明为已接入 Qt。

## 全面性结论

ESP32 和网页的构建、部署材料基本齐全：入口源码、固定平台/库版本、GPIO 配置、内嵌网页、合并固件、刷写工具、ARM 配套发送端、自动启动、协议/HTTP 接口、硬件接线和第三方声明均已提供。网页使用 ESP32 本地热点，连接 `LabMate-Camera` 后访问 `http://192.168.4.1`；示例热点密码见恢复后的部署文档。修改 HTML 后需重新构建及烧录固件。

当前缺口主要属于验收和外部环境：

- 交接说明记载约 28 ACK 帧/秒的历史反馈，未提供同版本完整原始现场日志；ACK 接收速率与浏览器显示帧率分开记录。
- 最终固件的整机冷启动、网络终端、多设备与异常恢复仍需实机复核。
- OCR 需匹配板卡 SDK 重编译 `smoke_infer` 并完成板端验收；交接包主动未带已知 GLIBC 不兼容的旧可执行文件。推理源码、模型、运行库、头文件和构建入口均已保留。
- DG4102 实际电输出、各仪器全部模式/量程仍缺充分实机证据。新交接的 SDS1202X 包装接口未实现原始采样点导出；现有 Qt 工程自己的波形/FFT ARM 接口另行保留。
- 队员文档记录了 117 项回归和浏览器/交叉编译检查，但相应测试脚本及原始日志未在本 ZIP 中交付。本轮将其标为“交接文档记载”，不冒充本轮重新执行的验证。

## 与现有 FPGA/Linux 材料的对接

新接线与现有 XDC 对应：K14/SCLK→ESP32 GPIO18，M15/MOSI→23，J14/CS→27，L16/MISO→19，G14/READY→26。SPI 为 mode1，READY 用交替 token；Linux 通过 compatible `labmate,esp32-image-link` 查找设备，并按 PS gpiochip base+65 找 READY。

**发送协议要配套。** 本轮固件采用 `LMJPEG01` 帧、`LMCK` 的 1024 字节 SPI 包和 `LMAK` 的 12 字节 ACK，单图上限 32768 字节。旧内核交接的 `send_jpeg.py` 使用 1056 字节数据事务及另一套头部/32 字节 ACK，不能直接与本轮固件配对。旧脚本作为来源保留；本轮运行入口统一选恢复后的 `board_modules/c_camera_link/run_spi_emio_board.sh`。

**频率配置待统一。** 当前交付 DTB/DTS 限频 4000000 Hz，队员的 `--max-fps` 预设请求 8000000 Hz。先按本工程的 4 MHz / 目标 10 fps 命令联调；请求频率、驱动回读和真实总线测量分别记录。若采用 8 MHz 模式，应先核对并同步设备树、内核产物和硬件实测，不直接把历史 28 ACK 帧/秒用于当前组合。

## 从标准目录复现

在工程根目录执行：

```sh
python -B build/prepare.py --out /path/to/labmate_repro --component board_modules
python -B sim/check_board_modules.py --workspace /path/to/labmate_repro --out /path/to/checks.json
cd /path/to/labmate_repro/board_modules
python3 -B tools/repack.py --verify
```

第二条验证会检查原交接清单、Python 3.7 语法、固件与内嵌网页、ARM ELF 和封包；有 Node.js 时同时检查网页 JavaScript 语法。它不访问板卡。

ESP32 构建在已安装 PlatformIO 及对应工具链的环境进行：

```sh
pio run -d c_camera_link/esp32 -e esp32dev_spi_emio
python3 tools/merge_firmware.py --build-dir c_camera_link/esp32/.pio/build/esp32dev_spi_emio --framework-dir /path/to/framework-arduinoespressif32 --output-dir c_camera_link/generated/firmware
```

合并工具需要 esptool 4.5.1。随包已有固件可直接用于后续人工烧录；本轮整理没有执行烧录。原 ARM 采集程序的构建入口为 `python3 c_camera_link/native/build.py --zig /path/to/zig`，版本 Zig 0.13.0。

在匹配板端内核、FPGA、接线和固件就绪后，首次预览命令为：

```sh
cd /path/to/labmate_repro/board_modules
chmod +x c_camera_link/native/*_armv7
sh c_camera_link/run_spi_emio_board.sh --spi-cs-high --preview --ten-fps --count 0
```

该预设请求 4 MHz、目标 10 fps，不是本轮测得的帧率。也可在工程根目录使用 `sh board/run_camera_preview.sh /path/to/labmate_repro`。自启应在最终 SD 路径确定后按原文档人工安装。

## 文档入口

- [原交接总说明](handoff_readme.md)
- [状态与验收边界](status.md)
- [硬件说明](hardware.md)
- [原部署说明](deploy.md)
- [原构建说明](build.md)
- [业务与 HTTP 接口](interfaces.md)
- [队员记载的交付检查](verification.md)
- [第三方组成](third_party/readme.md)

上述原文保持原始字节，原文内的大小写相对链接和命令按恢复后的 `board_modules/` 布局使用。本轮独立核验结果见 `sim/results/board_modules_checks.json`。
