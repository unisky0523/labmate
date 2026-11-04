# DG4102 板端 HOST2 部署

## 交付范围

交付包：`generated/labmate_dg4102_board.zip`。解压后包含独立的 `labmate_dg4102_board/c_instrument`，不覆盖原万用表、示波器或摄像头目录。已实现源码、离线依赖、HOST2 绑定与自动测试；尚待真实板端验收，没有远程修改板子系统。

板端使用用户态 libusb + 随包 PyUSB / PyVISA-py，与之前示波器路线一致。不需要 NI-VISA、联网 pip 或 usbtmc 内核模块。板子须有 Python 3.7+ 和 libusb-1.0.so.0。仅忽略 PyVISA-py 明确返回的“不支持 clear”，其他 USB 错误仍中止操作。

## 复制和首次绑定

1. 信号源后面板 USB Device 接板卡物理 **HOST2**，信号源开机。不要接信号源前面板 U 盘口。
2. 将 ZIP 解压后的整个 `labmate_dg4102_board` 文件夹复制到 SD 卡根目录。
3. SD 卡装回板子启动，在 Linux 串口终端进入此目录。以下假设 SD 卡挂载在 `/mnt/sd`，以实际挂载位置为准。

```sh
cd /mnt/sd/labmate_dg4102_board
sh c_instrument/run_dg4102_board.sh --list
sh c_instrument/run_dg4102_board.sh --bind-host2
```

绑定只查询状态，不改变波形或输出。成功应显示 `valid:true`、`identity_verified:true`、序列号 `DG4E184950519`。

配置保存在 `c_instrument/board_config/dg4102_host2.json`，记录真实 Linux USB 路径与序列号。**软件不能凭板上印字判断哪个 Linux 路径叫 HOST2；首次绑定时必须已插在物理 HOST2 上。** 此步骤把实际接线路径登记为 HOST2，不修改 FPGA 引脚、设备树或 USB 控制器。

之后每次控制都核对路径和序列号，不依赖不稳定的 USB 设备地址或 `/dev/usbtmc0` 编号。换插口/hub 或控制器枚举改变后如路径变化，须接回 HOST2 再绑定。

## 实测步骤

USB **HOST2** 是板端插口，信号源 **CH2** 是模拟输出通道，两者独立。下面控制信号源 CH2：

```sh
sh c_instrument/run_dg4102_board.sh --channel 2 status
sh c_instrument/run_dg4102_board.sh --channel 2 sweep --start-hz 100 --stop-hz 10000 --time-s 5 --amplitude-vpp 1
```

配置会先关闭选定输出，成功后仍为 OFF。把 CH2 接高阻示波器输入后开启：

```sh
sh c_instrument/run_dg4102_board.sh --channel 2 output on
```

此时应重复执行 100 Hz→10 kHz、5 秒、1 Vpp、零偏置、High-Z、正弦线性扫频。仅关闭输出、保留扫频模式：

```sh
sh c_instrument/run_dg4102_board.sh --channel 2 output off
```

再用 `output on` 恢复。若要关闭输出并退出扫频：

```sh
sh c_instrument/run_dg4102_board.sh --channel 2 stop
```

`stop` 后 `output on` 仅打开普通输出，重新扫频要再次发 `sweep` 配置。固定正弦配置示例：

```sh
sh c_instrument/run_dg4102_board.sh --channel 2 sine --frequency-hz 1000 --amplitude-vpp 1
```

更多参数用 `sh c_instrument/run_dg4102_board.sh --help`。全局参数放在动作前。CLI 默认保存完整 JSON 到部署目录的 `c_instrument/runs`。同部署目录 CLI 与 Python 接口共用文件锁，并发请求返回 `DEVICE_BUSY`。

## 排查与验收边界

- `--list` 为空：检查接线和电源，运行 `sh c_instrument/scope_board_check.sh` 检查 USB/libusb。
- `HOST2_NOT_BOUND`：先运行 `--bind-host2`。
- `HOST2_DEVICE_NOT_FOUND`：检查实际插口、路径及序列号，不要手工创建设备节点。
- `INSTRUMENT_ERROR` / `QUERY_TIMEOUT`：保留完整 JSON，检查面板和输出状态，不连续盲目重试。预存仪器错误可能导致动作执行前被拒绝。
- `COUPLING_ACTIVE`：人工关闭通道耦合，避免连带影响另一通道。

验收顺序：绑定 → 状态查询 → 输出 OFF 时配置并回读 → 示波器观察实际扫频 → 分别验证 output off/on 和 stop。`electrical_output_verified:false` 表示程序没有测量实际电信号，不能把参数回读当作波形验收。
