# SA5041 板端部署与验收

## 无 cp210x 内核驱动时的用户态入口

2026-11-01 板上已确认 lsusb 可见 10c4:ea60，但不存在 cp210x 驱动、模块及 /dev/ttyUSB*。新版包增加 PyUSB + 板上已有 libusb 的直接通信入口；已在目标板上读取一次直流电压。原电脑 COM9 和板端串口后端保持不变。

将新版 labmate_sa5041_board.zip 解压到 SD 卡，进入含 c_instrument 的父目录后，确认万用表 USB Device 接板子 Host、仪器开机，运行：

    sh c_instrument/run_meter_board.sh --timeout-ms 3000

只查询当前模式，不切换万用表设置。请保留完整 JSON，核对 function、value、unit、display_unit、unit_scale_verified 和仪器面板。若失败，请保留 error_code 和 detail，不要手动创建设备节点。此路线不需要 pip；包内自带 PyUSB，系统仍须有 libusb-1.0.so.0。

适用：Zynq Linux PS 作为 USB Host，SA5041 通过 CP210x USB 转串口连接。用户态入口需要 Python 3.7、系统 libusb 和包内 PyUSB；**不需要 pyserial、VISA、OpenCV 或 OCR**。

## 当前验证边界

- Windows COM9 上已实测直流电压、电阻读取；电阻量程 `2k` 已正确转换为 Ohm。
- Python 3.7 语法解析检查和 49 项离线测试通过；板端实际运行记录见下节。
- 目标 Zynq 板通过 lsusb 看到 CP210x（10c4:ea60），虽然没有 /dev/ttyUSB*，用户态入口已完成一次实机读取。尚未完成面板对照、变化读数、拔插恢复和其他模式验收。
- 其他测量模式在代码中有映射，但没有全部实机验证。量程不明确的裸数值会返回无效，不会猜单位。

## 板端首次实测记录

- 2026-11-01 用户提供的板端串口截图：在 `/media/sd-mmcblk0p1/labmate_sa5041_board` 执行 `sh c_instrument/run_meter_board.sh`，返回 `transport: cp210x_usb`、`simulated: false`、`status: complete`、`valid: true`。
- 功能为 `VOLT:DC`；读取值 `0.0006 V`，量程查询前后均为 `2V`，`unit_scale_verified: true`。这证明板端 USB 通信及该模式的数据通路已运行；仍需与仪表面板读数比对，不能据此宣称所有模式或精度已验收。
- 截图中的 `identity_verified: false` 是当前程序未执行仪表身份查询，不等于模拟数据。板端系统时钟显示 2023-04-30，与实测日期不符；修正板端时间后才能依赖 `captured_at` 作为实验时间戳。
- 开机日志还提示 FAT 分区未正常卸载。当前读取已成功，但之后应在不运行采集时安全卸载/检查 SD 卡，避免结果文件损坏。

## 交给 A 的文件

生成的 `labmate_sa5041_board.zip` 中包含可运行所需源码和说明。也可以直接把整个 `c_instrument` 目录交给 A；视觉目录不需要带入此通信测试。

## 旧串口路径：仅当 /dev/ttyUSBx 已出现

用户态入口请按文首命令运行。以下步骤只适用于内核已提供 cp210x 驱动并出现 /dev/ttyUSBx 的情况；不要为了使用用户态入口安装驱动或 pyserial。仪表 USB Device 接板端 Host，不接 CH340 调试口。

1. 将 zip 解压到 SD 卡或板端目录，确保当前工作目录是包含 `c_instrument` 子目录的父目录。
2. 插入 SA5041 USB 线并开机，在板端串口执行：

```sh
sh c_instrument/board_check.sh
```

确认 `lsusb` 能看到 Silicon Labs CP210x（VID:PID `10c4:ea60`），并检查是否出现 `/dev/ttyUSB0` 等节点。若没有节点，回到文首用户态入口测试，不要手动创建设备节点。

3. 检查 Python 并安装唯一的 Python 依赖：

```sh
python3 --version
python3 -m pip install -r c_instrument/requirements-serial.txt
```

目标 Python 应为 3.7 或更新版本。若板端不能联网，A 需准备匹配架构和 Python 版本的 pyserial wheel；不要复制 Windows venv 或安装 Windows wheel。

4. 用实际节点读取。示例中的 `/dev/ttyUSB0` 必须按检查结果替换：

```sh
python3 -m c_instrument.sa5041 --port /dev/ttyUSB0
```

重复运行前不要让其他进程占用该串口。一次调用只查询当前功能，不会切换万用表量程或功能；通信失败时返回错误 JSON，不复用上次读数。

## 验收标准

- 用户态入口的 JSON 中 `transport` 为 `cp210x_usb`；旧串口路径为 `serial`；两者 `simulated` 均应为 `false`。
- `function` 与面板模式一致；直流电压或电阻的数值、显示倍率和换算结果与面板一致。
- 电阻处于 kΩ 档时，应同时看到 `display_unit: kOhm`、对应 `scale_to_base: 1000` 和换算后的顶层 `unit: Ohm`。内部量程检查不代替与面板实测对照。
- 改变输入后读数随之改变；关闭仪表或拔线后有限时间内失败；重连后可恢复。
- 把完整 JSON 和 `result_path` 发回，记录板卡镜像/内核版本、Python 版本、设备节点。

板端串口权限不足时先将错误和 `ls -l /dev/ttyUSB*` 结果交给 A；不要未经确认修改 udev 或系统权限。项目原串口日志和调试 COM 口不要与仪表节点混淆。

## B 调用

```python
from c_instrument.sa5041 import read_sa5041

result = read_sa5041("cp210x-usb", request_id="B-001")
```

调用方应串行化同一仪表请求，并检查每项的 `valid`、`unit_scale_verified`、`value`、`unit` 与 `error_code`。C 返回采集结果；B 负责最终实验记录。
