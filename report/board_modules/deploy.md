# 板端部署

以下命令在板卡 Linux shell 中执行。串口软件是输入 shell 命令的窗口；不是在 Windows PowerShell 中运行板端命令。

## 放置目录

将整个 `labmate_board_modules_20261104` 放到 SD 卡，例如 `/media/sd-mmcblk0p1/labmate_board_modules_20261104`。保留目录层级。进入该目录：

```sh
cd /media/sd-mmcblk0p1/labmate_board_modules_20261104
chmod +x c_camera_link/native/camera_jpeg_stream_armv7
chmod +x c_camera_link/native/camera_stream_armv7
chmod +x c_camera_link/native/ppm_to_jpeg_armv7
```

若所在文件系统禁止执行，需要改用允许执行的挂载点或调整挂载设置。仪器运行器会自动设置自身 vendor 路径，不需要安装 NI-VISA。

## 万用表

```sh
sh c_instrument/run_meter_board.sh
```

仪器处于期望测量模式后再调用。只有 `valid=true` 才能记录为有效数据。未识别的倍率返回 `UNIT_SCALE_UNRESOLVED`；不要用原始数字直接冒充基础单位读数。

## 示波器

```sh
sh c_instrument/run_scope_board.sh --list
```

将枚举出的示波器完整地址作为参数，不把其他 USB 仪器的地址交给示波器：

```sh
SCOPE_RESOURCE='在这里填写枚举出的示波器完整USB资源地址'
sh c_instrument/run_scope_board.sh --resource "$SCOPE_RESOURCE" --channels 1 --measure PKPK FREQ RMS MEAN MAX MIN
sh c_instrument/run_scope_board.sh --resource "$SCOPE_RESOURCE" --screenshot
```

多台 USB 仪器同时连接时必须明确选择资源。截图按真实格式保存为 BMP 或仪器返回的受支持图片格式，不会伪装成 JPEG。不改变示波器当前 RUN/STOP 状态。

## DG4102 与 HOST2

首次把 DG4102 接到物理 HOST2：

```sh
sh c_instrument/run_dg4102_board.sh --list
export LABMATE_DG4102_SERIAL='填写刚才列出的DG4102实际序列号'
sh c_instrument/run_dg4102_board.sh --bind-host2
sh c_instrument/run_dg4102_board.sh --channel 2 status
```

绑定保存在 `c_instrument/board_config/dg4102_host2.json`。后续启动可以不设置环境变量，直接使用已保存的绑定；若设置了环境变量，其值必须与绑定一致。更换信号源或物理插口须重新绑定，不把旧绑定发布到代码仓库。

```sh
sh c_instrument/run_dg4102_board.sh --channel 2 sweep --start-hz 100 --stop-hz 10000 --time-s 5 --amplitude-vpp 1
```

此命令仅配置扫频并保持该通道输出关闭。确认结果成功且确实需要输出后：

```sh
sh c_instrument/run_dg4102_board.sh --channel 2 output on
sh c_instrument/run_dg4102_board.sh --channel 2 output off
sh c_instrument/run_dg4102_board.sh --channel 2 stop
```

`output off` 保留扫频模式；`stop` 关闭输出并关闭扫频。之后单独 `output on` 不能恢复被 stop 关闭的扫频模式。

## 摄像头与网页

ESP32 已烧录本包 `spi-emio.bin`、FPGA 与设备树配置正确并接线供电后：

```sh
sh c_camera_link/run_spi_emio_board.sh --spi-cs-high --preview --max-fps --count 0
```

手机或电脑连接 Wi-Fi `LabMate-Camera`，演示密码 `LabMate-2026`，浏览器访问 `http://192.168.4.1`。这使用 Wi-Fi，不是蓝牙，也不是公网网站。网页支持现场画面、冻结、框选、箭头、撤销、清空及保存图片；标注按冻结画面使用。正式演示可在 ESP32 源码中修改热点名称和密码后重新构建烧录。

预览使用原生采集，不安装 opencv-python。`--max-fps` 默认 320 像素宽、JPEG quality50、请求 SPI8MHz、无固定帧率上限。不要同时启动旧预览进程。中断导致令牌不同步时，先停止发送，再将板端与 ESP32 一起重新初始化，不盲目重试残余事务。

确定最终 SD 目录后安装自启：

```sh
sh c_camera_link/autostart_board.sh install
sh c_camera_link/autostart_board.sh start
sh c_camera_link/autostart_board.sh status
```

安装前先停止手动预览。管理命令还有 `stop`、`disable`，运行状态与日志在 `/tmp/labmate_camera_service`。安装会记录当前路径；若之前安装的是旧目录，先从旧目录执行 `disable` 后再安装新目录，避免两个启动入口。首次必须做一次整机断电再上电验收。

## Paddle-Lite OCR

OCR 尚未完成板端验收，先阅读 [构建说明](BUILD.md)。匹配板卡系统重编译 `smoke_infer` 并确认 Python 的 numpy、cv2、pyclipper 及共享库依赖全部可用后：

```sh
sh c_vision_lite/run_ocr_board.sh --image /path/to/instrument_photo.jpg --out runs/ocr --request-id task-001
```

推荐读取已保存的图片；原生预览运行时不要再用 OpenCV 打开同一相机。默认解析配置面向原先 Keysight 测量/游标面板，不是 SDS1202X 通用 OCR，也不保证能读清低像素远距离照片。
