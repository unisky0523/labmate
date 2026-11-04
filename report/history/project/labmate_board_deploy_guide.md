# LabMate B 板端部署指南

## 0. 核心原则

只把新代码放到一个独立目录：

```text
/home/root/labmate_b
```

不要修改：

```text
/boot
/etc
/lib
/lib/modules
/usr
现有厂商界面目录
现有 PL Bitstream 和设备树
```

不要执行：

```text
apt upgrade
apt dist-upgrade
opkg upgrade
pip install --upgrade numpy
pip install --upgrade opencv
删除或覆盖现有驱动、设备树、内核
```

部署目标是“增加一个应用目录”，不是重建 Linux。

## 1. 部署方式选择

优先级：

```text
1. PS Ethernet + SSH/SCP
2. U 盘拷贝
3. 串口传输小文件
```

大模型 `vosk-model-small-cn-0.22` 约 65 MB，不建议走串口。

## 2. 推荐方式：PS Ethernet + SSH/SCP

### 2.1 开发板接线

把网线插到开发板的 PS 网口，通常标着：

```text
PS_GE
```

不要插 PL 网口。PL 网口和 Linux 网络默认不是一回事。

### 2.2 开发板检查网络

在串口终端执行：

```bash
ip link show
```

确认有网口的 `LOWER_UP`：

```bash
eth0: <BROADCAST,MULTICAST,UP,LOWER_UP>
```

如果 `eth0` 是 DOWN，先尝试：

```bash
ip link set eth0 up
udhcpc -i eth0
ip addr show eth0
```

如果 `udhcpc` 不存在，再尝试：

```bash
dhclient eth0
```

如果 `eth0` 没有链路，检查网线是否插在 PS_GE，或者是否对应 `eth1`。

拿到地址后，例如：

```text
inet 192.168.1.50/24
```

### 2.3 检查 SSH 服务

在板端执行：

```bash
ps | grep sshd
```

如果没有 `sshd`，不要强行改系统，改用 U 盘方式。

如果已有 `sshd`，在 Windows PowerShell 测试：

```powershell
ssh root@192.168.1.50
```

### 2.4 Windows 生成干净部署包

不要直接上传整个 `D:\labmate_b`，因为里面包含 Windows 的 `.venv`、日志和测试数据。

先在工作区生成干净目录：

```powershell
cd 'D:\fpga amd xinlx'
powershell -ExecutionPolicy Bypass -File .\tools\package_labmate_board.ps1
```

脚本只复制板端需要的代码、模型和提示音频到：

```text
D:\fpga amd xinlx\dist\labmate_b_board
```

上传：

```powershell
scp -r D:\fpga amd xinlx\dist\labmate_b_board root@192.168.1.50:/home/root/labmate_b
```

上传后在板端确认：

```bash
ls -la /home/root/labmate_b
python3 --version
```

## 3. 备用方式：U 盘拷贝

在开发板串口终端：

```bash
mkdir -p /mnt/usb
mount /dev/sda1 /mnt/usb
ls /mnt/usb
cp -r /mnt/usb/labmate_b /home/root/labmate_b
umount /mnt/usb
```

如果 `/dev/sda1` 不存在，用 `dmesg | tail` 和 `ls /dev/sd*` 查看实际设备名。

U 盘方式只复制文件到 `/home/root/labmate_b`，不会改变 Linux 原有框架。

## 4. 串口方式

串口只适合传几个小文件，例如：

```text
board_app.py
board_audio.py
board_speaker.py
board_ui.py
board_sources.py
main.py
asr_cli.py
text_cli.py
```

不要在串口里传 65 MB 模型。模型必须用网络或 U 盘。

## 5. 部署后检查

进入目录：

```bash
cd /home/root/labmate_b
```

检查 Python：

```bash
python3 --version
```

检查音频设备：

```bash
arecord -l
aplay -l
```

测试录音，使用队友 A 已验证的 S24_LE 44.1 kHz 双声道路径：

```bash
aplay -D default -t raw -f S24_LE -r 44100 -c 2 -d 16 /dev/zero &
arecord -D hw:0,1 -t raw -f S24_LE -r 44100 -c 2 -d 10 /tmp/mic_rate_test.raw
i2cset -f -y 0 0x10 0x0a 0x00 b
i2cset -f -y 0 0x10 0x03 0x09 b
i2cset -f -y 0 0x10 0x0d 0x03 b
ls -l /tmp/mic_rate_test.raw
aplay -D default -t raw -f S24_LE -r 44100 -c 2 /tmp/mic_rate_test.raw
```

`board_mic.py` 会自动执行同样的流程；`--no-es8388-init` 只用于排除寄存器初始化问题。

如果这一步失败，不要改 Python 代码，先检查 ES8388 和 ALSA 设备。

## 6. 运行板端应用

没有 Vosk 时先运行：

```bash
python3 board_app.py --no-vosk
```

操作：

```text
按回车：录音
直接输入：文字命令
q：退出
```

状态文件：

```text
data/state/latest_status.json
```

录音文件：

```text
data/audio/asr_tests/
```

## 7. Vosk 安全安装

优先使用项目自带的兜底后端：

```text
asr_backend.py
vosk_lite.py
libvosk.so
```

`libvosk.so` 来自官方 Vosk 0.3.45 ARMv7 wheel。它不需要在板端安装 `requests`、`tqdm`、`srt` 或 `websockets`，也不需要系统 Python 的 cffi 包。

只要 `vosk_lite.py` 和 `libvosk.so` 在 `/home/root/labmate_b` 下，运行：

```bash
cd /home/root/labmate_b
python3 board_app.py
```

如果官方包已经可用，`asr_backend.py` 仍会优先使用官方 `vosk`。

以下方式仅在需要使用官方 Python 包时采用：

原则：不要升级系统 Python，不要全局覆盖现有包。

如果拿到 ARMv7 + Python 3.7 的 Vosk wheel，可以使用局部目录：

```bash
cd /home/root/labmate_b
mkdir -p third_party
python3 -m pip install --no-deps --target third_party vosk-xxx-armv7.whl
```

运行时指定路径：

```bash
PYTHONPATH=/home/root/labmate_b/third_party python3 board_app.py
```

官方 wheel 备份在当前电脑的：

```text
D:\fpga amd xinlx\dist\wheels\vosk-0.3.45-py3-none-linux_armv7l.whl
```

如果找不到 ARMv7 + Python 3.7 wheel，就继续使用：

```bash
python3 board_app.py --no-vosk
```

不要为了 Vosk 升级板端 Python。

## 8. 扬声器告警

真实播报“数据异常”需要提示音频：

```text
data/audio/prompts/source_conflict.wav
```

没有该文件时，代码会使用双音蜂鸣告警：

```text
board_speaker.play_tone()
```

播放设备：

```text
default
```

## 9. 现有 RGB LCD 界面集成

目前只新增了状态桥：

```text
data/state/latest_status.json
```

现有界面需要读取这个 JSON，并把以下字段显示到“实验助手”页面：

```text
state
asr_text
asr_partial
asr_command
asr_error
last_console_line
record_path
source_consistency
```

修改现有界面前必须：

1. 找到现有界面的源码目录和启动脚本。
2. 备份原始界面文件。
3. 只增加新页面或新控件。
4. 不删除原有菜单、按钮、驱动加载和启动逻辑。
5. 用一个独立提交或独立目录保存界面修改。

在 UI 源码未确认前，只运行：

```bash
python3 board_app.py --no-vosk
```

这样不会影响原界面。

## 10. 回滚

如果应用有问题，删除应用目录即可：

```bash
rm -rf /home/root/labmate_b
```

不要删除：

```text
/etc
/lib
/usr
/boot
/lib/modules
厂商界面目录
```

删掉 `/home/root/labmate_b` 后，原有 Linux 和界面应保持原样。

## 11. 最终检查清单

```text
[ ] 只新增 /home/root/labmate_b
[ ] 没有执行 apt/opkg upgrade
[ ] 没有升级系统 Python
[ ] 没有覆盖 /boot、/etc、/lib
[ ] 没有替换 PL Bitstream
[ ] arecord 48 kHz 双声道测试通过
[ ] aplay 播放测试通过
[ ] python3 board_app.py --no-vosk 能启动
[ ] data/state/latest_status.json 能更新
[ ] 原界面仍能正常启动
[ ] 现有菜单和驱动没有被删除
```
