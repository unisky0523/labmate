# 语音与业务层接口

本包不含语音识别、意图解析或任意 SCPI 执行服务。调用方把识别结果转换为白名单动作及明确的 SI 参数，再调用以下入口。

## 推荐：板端子进程

使用参数数组和固定部署目录，不能把识别原文直接拼接到 shell。示例：

```python
import json
import subprocess

process = subprocess.run(
    ['sh', 'c_instrument/run_scope_board.sh',
     '--resource', scope_resource, '--channels', '1',
     '--measure', 'PKPK', 'FREQ'],
    cwd=project_directory,
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    universal_newlines=True)
result = json.loads(process.stdout)
success = process.returncode == 0 and result.get('valid') is True
```

仪器 CLI 的 stdout 为 JSON，stderr 保留诊断信息；失败退出码通常为 2。摄像头连续预览输出多条结果，不能用同一方式把全部 stdout 解析成单个 JSON。

| 业务意图 | 板端入口 |
| --- | --- |
| 读取万用表 | `sh c_instrument/run_meter_board.sh --request-id task-001` |
| 读取示波器参数 | `sh c_instrument/run_scope_board.sh --resource ADDRESS --channels 1 2 --measure PKPK FREQ RMS` |
| 保存仪器屏幕 | `sh c_instrument/run_scope_board.sh --resource ADDRESS --screenshot` |
| 信号源动作 | `sh c_instrument/run_dg4102_board.sh --channel 2 ACTION ...` |
| 管理现场预览 | `sh c_camera_link/autostart_board.sh start/stop/status`，每次只传其中一个动作 |
| 读取已保存照片的 OCR | `sh c_vision_lite/run_ocr_board.sh --image PHOTO --request-id task-001`；待板端验收 |

仪器截图目前没有独立的 `request_id` 参数透传结果字段，业务层应把截图结果与自己的任务 ID 一起保存。CLI 默认写入 `c_instrument/runs`；OCR 默认由启动器写入 `runs/ocr`，可用 `--out` 更改。现场网页保存图片是浏览器下载，不自动成为板端实验记录。

## 同进程 Python

仪器代码目录、`c_instrument/vendor` 必须先加入 sys.path；精简 Python 缺少 typing 时再把 `c_instrument/compat_py37` 追加在系统路径后。优先使用上面的启动器以免导入其他目录中的旧模块。

```python
from c_instrument.sa5041 import read_sa5041
from c_instrument.sds1202x import read_scope, capture_screen
from c_instrument.dg4102_board import execute_host2

meter = read_sa5041('cp210x-usb', request_id='task-001')
scope = read_scope(scope_resource, channels=(1,), parameters=('PKPK', 'FREQ'),
                   backend='@py', request_id='task-002')
screen = capture_screen(scope_resource, backend='@py', output='runs/screens')
generator = execute_host2({'action': 'status', 'channel': 2}, request_id='task-003')
```

上述同步接口可能抛出依赖或通信异常，调用方需要捕获并保存 detail。读取 API 不传 output 默认不落盘；截图必定落盘。DG4102 包装器返回结构化失败，并通过文件锁拒绝同一部署目录下的并发动作。

OCR 同进程接口为 `LiteOcr(directory)` 与 `read_image(image, config, output, engine, request_id)`，位于 `c_vision_lite.board_reader`。`directory` 指向包含模型、alphabet、共享库及重新编译的 smoke_infer 的 `c_vision_lite/assets`。后端适配临时修改共用解析函数，必须串行执行，不能跨线程同时处理多个 OCR 请求。

## DG4102 动作白名单

| action | 参数 | 行为 |
| --- | --- | --- |
| `status` | `channel` | 只查询 |
| `sine` | `frequency_hz`, `amplitude_vpp` | 配置固定正弦，所选输出关闭 |
| `sweep` | `start_hz`, `stop_hz`, `time_s`, `amplitude_vpp` | 配置正弦扫频，所选输出关闭 |
| `output` | `state=on/off` | 仅开关输出，保留模式 |
| `stop` | 无额外参数 | 输出关闭并关闭扫频 |
| `trigger` | 无额外参数 | 已开启扫频、MAN 触发源时触发一次，不代表扫频已结束 |

channel 为整数 1/2，默认 1，语音层建议显式指定。sine/sweep 可选 `offset_v=0`、`load=highz/50`；sweep 可选 `spacing=lin/log`、`trigger=int/man/ext`，默认 lin/int。CLI 使用连字符参数，如 `--start-hz`；全局 `--channel` 放在动作前。

统一输入 Hz、秒、Vpp、V 偏置。不得把 Vrms 当作 Vpp，也不能把字符串中的 k/m 前缀丢掉。默认只开放源码校验范围内的正弦/扫频功能，不是全仪器控制接口。

“开始扫频”需要先 sweep 配置成功，再执行 output on；第一步失败不得继续。两步需在语音层按同一设备任务队列连续调度，避免中间插入其他配置。一次失败可能已有部分设置生效，不盲目自动重发开启输出。

## 成功与失败

数据只在 `valid=true` 时作为有效测量。对仪器控制，还须 `status=complete`，不能把 `--dry-run` 产生的计划当作真实执行。DG4102 status 的 `executed=false` 表示没有执行设置动作；`electrical_output_verified=false` 表示未测量实际电输出，均不应误报成物理信号已确认。

保留 request_id、原始 evidence、unit、error_code 和 detail。常见失败包括 `QUERY_TIMEOUT`、`UNIT_SCALE_UNRESOLVED`、`RESOURCE_REQUIRED`、`DEVICE_IDENTITY_MISMATCH`、`HOST2_NOT_BOUND`、`HOST2_DEVICE_NOT_FOUND`、`DEVICE_BUSY`、`READBACK_MISMATCH`。不要只播报 value，也不要在失败时用 0 替代缺失数据。

示波器参数支持 PKPK、AMPL、MAX、MIN、MEAN、RMS、TOP、BASE、CMEAN、CRMS、FREQ、PER、RISE、FALL、PWID、NWID。保存屏幕与记录原始波形采样点是不同业务；后者本包未实现。

## ESP32 网页 HTTP 接口

这些接口位于 ESP32 的 `http://192.168.4.1`，只供同一热点内客户端使用。板端通过 SPI 发送图片，不会因此自动拥有到热点的 IP 连接。

| 方法与路径 | 结果 |
| --- | --- |
| GET `/api/state` | 当前 sequence、revision、冻结状态及标注等 JSON |
| GET `/api/frame` | 当前显示帧的 JPEG；可用 sequence/revision 限定版本，版本变化返回 409 |
| GET `/api/snapshot` | 4 字节小端 metadata 长度 + UTF-8 JSON + JPEG；同版本请求可省略 JPEG，见 jpeg_bytes |
| POST `/api/freeze` | 冻结最新帧；没有图片返回 409 |
| POST `/api/live` | 恢复实时预览并清除标注 |
| POST `/api/annotations` | 提交 `{revision, annotations}`，仅接受冻结状态且 revision 匹配；成功后 revision 增加 |

annotations 最多 24 个图形，每个为 `{kind: "arrow"或"box", x1, y1, x2, y2}`，坐标为 0～1 的有限数值。请求体上限 4096 字节。冻结/标注状态由该 ESP32 上的所有客户端共享。单独 GET frame 不把标注绘制进 JPEG；网页保存功能在浏览器端合成画面与标注。
