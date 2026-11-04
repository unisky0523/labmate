# DG4102 信号源控制：语音部分交接

日期：2026-11-03。交接对象：语音识别、意图解析、任务调度同学。

## 1. 目标和当前状态

语音 → 识别文字 → 解析动作及 SI 参数 → 板端控制接口 → 板卡 HOST2 USB → DG4102 执行 → JSON 结果 → 播报。

设备为 RIGOL DG4102，序列号 `DG4E184950519`，固件 `00.01.13`。电脑端通过 NI-VISA 已实际验证身份查询、CH2 扫频配置及参数回读：100 Hz→10 kHz、5 秒、1 Vpp、High-Z、线性、内部触发；输出保持关闭。**板端新代码、语音联合执行和实际电信号尚待验收。**

已有万用表/示波器读取入口继续保留。本接口控制信号源，不自动测量电路，不自动读取示波器，也未实现自动生成频响曲线。

## 2. 部署与 HOST2

部署包：`c_instrument/generated/labmate_dg4102_board.zip`。将整个独立文件夹放到板端 SD 卡。后面板 USB Device 接板卡物理 HOST2，在部署目录执行：

```sh
sh c_instrument/run_dg4102_board.sh --bind-host2
```

首次必须实际插在 HOST2，程序读取真实 Linux USB 路径和序列号，验证型号后保存到 `c_instrument/board_config/dg4102_host2.json`。后续不接受不同路径或序列号。软件不能凭空识别插口印字，此绑定不修改 FPGA/设备树。**板卡 HOST2 与信号源 CH2 独立，channel 由请求显式指定。**

板端采用已有示波器路线的用户态 libusb，包内含 PyUSB/PyVISA-py 和 typing 回退，无需 NI-VISA。CLI 启动器已设置离线依赖路径，建议首次语音联调用它。

## 3. 推荐：子进程调用

以下部署路径按实际调整：

```python
import json
import subprocess

completed = subprocess.run(
    ["sh", "c_instrument/run_dg4102_board.sh", "--channel", "2",
     "sweep", "--start-hz", "100", "--stop-hz", "10000",
     "--time-s", "5", "--amplitude-vpp", "1"],
    cwd="/mnt/sd/labmate_dg4102_board",
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    universal_newlines=True)
result = json.loads(completed.stdout)
success = (completed.returncode == 0 and
           result.get("status") == "complete" and result.get("valid") is True)
```

用参数数组，不用 `shell=True`；识别原文不得直接拼 shell 或 SCPI。stdout 为 JSON，stderr 留存诊断信息。返回码 0 为成功/计划生成，2 为失败。业务执行不传 `--dry-run`，必须判断 `status=complete`，防止把计划当成真实执行。

上述 sweep 动作仅配置，**会关闭选定输出，成功后仍关闭**。用户明确要求开始输出时，配置成功后再调用 `output on`。

## 4. 动作契约

| action | 必需参数 | 可选参数/默认值 | 行为 |
| --- | --- | --- | --- |
| `status` | 无 | `channel=1` | 查询状态，不改波形和输出 |
| `sine` | `frequency_hz`, `amplitude_vpp` | `channel=1`, `offset_v=0`, `load=highz` | 设置固定正弦，输出关闭 |
| `sweep` | `start_hz`, `stop_hz`, `time_s`, `amplitude_vpp` | `channel=1`, `offset_v=0`, `load=highz`, `spacing=lin`, `trigger=int` | 设置正弦扫频，输出关闭 |
| `output` | `state=on/off` | `channel=1` | 仅开关输出，保留波形/扫频模式 |
| `stop` | 无 | `channel=1` | 关闭输出并关闭扫频模式 |
| `trigger` | 无 | `channel=1` | 手动触发一次扫频，要求扫频 ON、触发源 MAN |

channel 仅整数 1、2，建议语音层总是显式指定。spacing 仅 `lin/log`，trigger 仅 `int/man/ext`，load 仅字符串 `highz/50`。内部触发 int 会重复扫频；man 用于手动单次；ext 等外部触发。

CLI 参数将下划线改成连字符：`start_hz` 对应 `--start-hz`。输出命令是 `output on`，不是 `output --state on`。`--channel`、`--out`、`--timeout-ms` 是全局选项，放在动作前。

**语义必须区分：**

- 暂停/关闭输出：`output off`；之后 `output on` 可恢复原模式。
- 停止扫频：`stop` 关闭扫频与输出；之后单独 `output on` 只打开普通波形，恢复扫频必须重新配置 sweep。
- 开始扫频输出：`sweep` → 判断成功 → `output on`；第一步失败不能继续开启输出。
- 单次扫频：`sweep` 配置 `trigger=man` → `output on` → `trigger`。触发成功不是等待扫频结束，接口未提供完成等待。
- 配置成功只能播报“扫频已配置，输出关闭”；输出开启成功后才能播报“输出已开启”。

## 5. 同进程 Python 接口

接口为 `c_instrument.dg4102_board.execute_host2(request, config_path=DEFAULT_CONFIG, request_id=None, timeout_ms=3000, output=None)`。

导入前须正确配置部署目录、vendor、typing 回退；不要意外导入旧目录的同名 c_instrument。首次建议使用 CLI 子进程方案。

```python
from c_instrument.dg4102_board import execute_host2

result = execute_host2(
    {"action": "sweep", "channel": 2, "start_hz": 100,
     "stop_hz": 10000, "time_s": 5, "amplitude_vpp": 1,
     "spacing": "lin", "trigger": "int", "load": "highz"},
    request_id="voice-001", output="c_instrument/runs")

if result.get("status") == "complete" and result.get("valid") is True:
    # Only when the user requested actual output.
    result = execute_host2(
        {"action": "output", "channel": 2, "state": "on"},
        request_id="voice-001-output", output="c_instrument/runs")
```

request_id 是独立关键字参数，不放动作字典。动作字典拒绝多余字段和任意 SCPI。CLI 自动生成 request_id，上层可关联到自己的主任务 ID。API 默认不写文件，传 output 才保存；CLI 默认保存到部署目录的 `c_instrument/runs`。

同部署目录的 CLI/API 使用文件锁，忙时返回 DEVICE_BUSY。语音层还须以设备任务队列保证“配置→开启”作为连续业务任务，不能在两步之间插入其他配置。不能用两份部署目录同时访问同一设备，也不要与 VISA 工具并发访问。

## 6. 单位和边界

统一传 Hz、秒、Vpp、V 偏置。例如十千赫→10000，五百毫伏峰峰值→0.5，一百毫秒→0.1。1 Vrms 不能直接当成 1 Vpp；不明确的幅度或通道应由语音层追问，不能猜。禁止 NaN/Inf。

本版开放正弦及正弦线性/对数扫频，不是全仪器功能。正弦频率 1 µHz～100 MHz，扫频时间 0.001～300 秒，幅度 0.02～10 Vpp，并受负载/偏置/频率附加限制。High-Z 时 `abs(offset)+amplitude/2 <= 5 V`，50 Ω 时 <=2.5 V。高于 10 MHz 仅开放 <=1 Vpp、零偏置。仪器仍有实际限制，每条设置后检查错误并最终回读。

High-Z/50 是负载标定设置，不是物理终端，须与实际接线匹配。通道耦合开启时拒绝配置，避免改变另一通道。

## 7. 结果和错误

关键成功字段结构示例（不是新增实测证据）：

```json
{
  "device_id": "rigol_dg4102",
  "status": "complete",
  "valid": true,
  "simulated": false,
  "identity_verified": true,
  "executed": true,
  "error_code": "",
  "electrical_output_verified": false,
  "state": {
    "output": "OFF", "sweep": "ON",
    "start_hz": 100.0, "stop_hz": 10000.0,
    "time_s": 5.0, "amplitude": 1.0, "amplitude_unit": "VPP"
  }
}
```

status 查询成功时 `executed:false`，只表示没有设置动作，不是失败。仅 `status=complete` 且 `valid=true` 可播报成功。state 是回读设置，evidence 保存命令和原始回复。`electrical_output_verified:false` 表示没有实际电输出测量证据。

| error_code | 处理 |
| --- | --- |
| CONFIG_INVALID | 参数缺失/越界/不支持，修正或追问 |
| HOST2_NOT_BOUND | 提示维护人员先初始化绑定 |
| HOST2_DEVICE_NOT_FOUND | 检查插口、开机、线缆、序列号 |
| DEVICE_BUSY | 等待当前任务完成后排队 |
| DEVICE_IDENTITY_MISMATCH | 设备不是 DG4102，禁止继续控制 |
| COUPLING_ACTIVE | 人工关闭通道耦合 |
| TRIGGER_NOT_READY | 修正手动扫频触发流程 |
| INSTRUMENT_ERROR | 保留 detail/evidence，检查仪器错误队列 |
| QUERY_TIMEOUT / QUERY_FAILED / WRITE_FAILED | 通信中断，状态可能不确定，不自动重复开启输出 |
| RESPONSE_INVALID / READBACK_MISMATCH | 回复或设置不符，不播报成功 |
| DEPENDENCY_MISSING / VISA_BACKEND_FAILED | 检查部署、vendor 和 libusb |
| IO_FAILED | 文件/设备操作失败，保留详情 |

失败时设置可能部分生效，不自动回滚，不应假设输出一定关闭。保存失败时 API 的 control_result 可保留动作结果，不能据此盲目重发。接口不会自动重试。不要超短超时强杀子进程后立刻重发命令。启动前预存的仪器错误也可能使动作被拒绝。

## 8. 联调验收

1. 板端 HOST2 绑定、status 身份查询通过。
2. CH2 输出 OFF 时配置扫频，回读参数与请求一致。
3. 接示波器并明确 output on，观察真实扫频；分别测试 output off/on 与 stop。
4. 语音解析“第二通道，从一百赫兹扫到十千赫兹，五秒，一伏峰峰值”，先核对解析 JSON，再真实执行。
5. 记录主任务 ID、各动作 request_id、JSON、实际面板/示波器观察和失败详情。保留原万用表和示波器功能。
