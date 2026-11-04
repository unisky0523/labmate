# LabMate 现有显示框架接入“实验助手”方案

## 1. 当前问题拆开看

### 1.1 FAT-fs FSINFO 警告

当前程序路径位于：

```text
/media/sd-mmcblk0p1/labmate_b board_20261015/
```

这是 FAT 分区。不要把应用、录音和日志直接放在 FAT 分区运行。

正确做法是先复制到 ext4 根文件系统：

```bash
mkdir -p /home/root/labmate_b
cp -r "/media/sd-mmcblk0p1/labmate_b board_20261015/." /home/root/labmate_b/
sync
cd /home/root/labmate_b
chmod 755 run_board.sh libvosk.so lib/libatomic.so.1
sh run_board.sh --confirm-readback
```

FAT-fs 警告本身不一定立刻阻止程序，但它说明该 FAT 分区的元数据异常。应用不要继续在这个分区写记录。

### 1.2 录音削波

日志：

```text
[识别文字] (空)
[未执行] 录音明显削波，请降低增益或离麦克风稍远。
```

这是输入增益过高，不是 Vosk 没装，也不是命令词表问题。

先检查 ALSA 控制：

```bash
amixer -c 0 scontrols
amixer -c 0 contents
```

如果板端有 `alsamixer`：

```bash
alsamixer -c 0
```

把 ADC/PGA 录音增益降低约 10 到 20 dB，再录一次。

不要先随意改 `i2cset` 的 ES8388 寄存器值。A 当前给出的三条寄存器配置先保持不变，先通过 ALSA 音量控制解决削波。

## 2. 目标架构

不要删除现有界面框架。新增一个页面：

```text
现有 RGB LCD 主界面
├── 原有页面和按钮
└── 新增页面：实验助手
```

页面负责：

```text
[开始录音]
[确认]
[取消]
[拍波形]
[保存波形]
[查看状态]
```

页面不直接写记录，也不直接操作音频库。它只通过本地接口控制后台服务。

```text
现有 UI 页面
    |
    | 命令文件 / Unix Socket
    v
assistant_service.py
    |
    +-- board_app / TextApplication
    +-- board_mic
    +-- asr_backend / Vosk
    +-- board_speaker
    +-- main.save_record
    |
    v
data/state/latest_status.json
```

## 3. 为什么不能直接把 board_app.py 当页面

当前 `board_app.py` 是命令行程序：

```text
按回车录音
输入文字命令
输入 q 退出
```

它依赖串口/终端的键盘输入。现有 RGB LCD 页面没有终端输入，所以需要增加一层服务协议。

第一版最简单的协议：

```text
data/ui_commands/
├── start_record.json
├── confirm.json
├── cancel.json
├── capture_image.json
└── save_waveform.json
```

服务轮询这些命令文件，处理完后删除或改名。状态持续写入：

```text
data/state/latest_status.json
```

字段：

```text
state
asr_text
asr_partial
asr_command
asr_error
record_path
last_action
last_action_request
updated_at
```

## 4. 现有界面接入方式

必须先确认现有界面框架，不能盲改。

### Qt

新增一个 `QWidget` 页面，加入现有 `QStackedWidget` 或菜单入口。

页面用 `QTimer` 每 100 到 200 ms 读取：

```text
latest_status.json
```

按钮点击时写命令文件，或用 `QProcess` 启动 `assistant_service.py`。

不要删除原有页面，不修改主窗口启动逻辑之外的必要注册代码。

### LVGL

新增一个 `lv_obj_t` 页面，加入原页面管理器。

用 `lv_timer` 轮询 `latest_status.json`。按钮事件写命令文件。

不要替换原有 `lv_scr_act()` 的页面结构，只增加新 screen。

### Framebuffer / 自绘 UI

在现有页面管理器中增加一个页面 ID。

沿用现有触摸/按键事件分发，新增按钮区域和状态文本区域。

不要重写 framebuffer 初始化、DRM、LCD 驱动。

## 5. 需要先确认的界面信息

在板端执行：

```bash
ps -ef | grep -Ei "qt|lvgl|gui|app|display|fb"
ls -l /etc/init.d
cat /etc/inittab
```

然后查找应用目录：

```bash
find /opt /home /usr/local -maxdepth 4 -type f 2>/dev/null | head -100
```

需要拿到：

```text
现有界面进程名
现有界面源码目录
启动脚本
UI 框架名称
```

没有这些信息，只能先把 `assistant_service.py` 和状态桥做好，不能安全地改现有页面。

## 6. 推荐实施顺序

1. 把应用复制到 `/home/root/labmate_b`，停止从 FAT 分区运行。
2. 用 `amixer` 降低录音增益，先消除削波。
3. 确认现有界面框架和源码位置。
4. 增加 `assistant_service.py`，提供命令文件和状态文件接口。
5. 在现有 UI 中增加“实验助手”页面。
6. 页面按钮接入开始录音、确认、取消、拍波形、保存波形。
7. 最后才考虑把服务加入开机启动，且单独写启动脚本，不覆盖原启动脚本。

## 7. 验收标准

```text
[ ] 应用从 /home/root/labmate_b 运行
[ ] 不再向 FAT 分区写录音和日志
[ ] 录音不再削波
[ ] 原界面仍能正常启动和切换
[ ] 新增“实验助手”页面可以进入
[ ] 页面能开始录音并显示识别文字
[ ] 页面能确认/取消操作
[ ] 页面能显示动作请求
[ ] 不需要电脑串口即可完成一次完整操作
```
