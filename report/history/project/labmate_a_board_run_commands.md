# LabMate A 端上板运行指令

## 1. 进入程序目录

```bash
cd /home/root/labmate_b
```

## 2. 给运行文件权限

```bash
chmod 755 run_board.sh libvosk.so lib/libatomic.so.1
```

## 3. 首次验证音频通路

以下命令只做一次，用于确认 ES8388 录音和播放正常。

### 3.1 启动后台静音播放

```bash
aplay -D default -t raw -f S24_LE -r 44100 -c 2 -d 16 /dev/zero &
```

### 3.2 启动录音

```bash
arecord -D hw:0,1 -t raw -f S24_LE -r 44100 -c 2 -d 10 /tmp/mic_rate_test.raw &
```

### 3.3 配置 ES8388 寄存器

```bash
i2cset -f -y 0 0x10 0x0a 0x00 b
```

```bash
i2cset -f -y 0 0x10 0x03 0x09 b
```

```bash
i2cset -f -y 0 0x10 0x0d 0x03 b
```

### 3.4 等待后台任务结束

```bash
wait
```

### 3.5 检查录音文件

```bash
ls -l /tmp/mic_rate_test.raw
```

预期：

```text
/tmp/mic_rate_test.raw 存在且大小不为 0
```

### 3.6 回放录音

```bash
aplay -D default -t raw -f S24_LE -r 44100 -c 2 /tmp/mic_rate_test.raw
```

预期：

```text
扬声器能听到刚才录到的声音
```

## 4. 正式运行实验助手

```bash
sh run_board.sh --confirm-readback
```

`run_board.sh` 会自动把 `lib/` 加入库搜索路径，用来加载随包提供的 ARMv7 `libatomic.so.1`。

运行后：

1. 按回车开始录音。
2. 说命令，例如：

```text
拍一下波形
```

3. 系统显示并回读识别文字。
4. 再按回车，说：

```text
可以
```

5. 说“可以/好的/是的/确认/行”时执行；说“不行/不可以/不是/取消/重说”时取消。

## 5. 如果 Vosk 加载失败

先不加载语音识别，只测试流程：

```bash
sh run_board.sh --no-vosk
```

## 6. 如果 ES8388 初始化失败

关闭程序里的 ES8388 寄存器初始化再测试：

```bash
sh run_board.sh --no-vosk --no-es8388-init
```

## 7. 退出程序

在程序提示符下输入：

```text
q
```

## 8. 说明

`board_app.py` 运行时会自动执行录音、静音保活、`i2cset` 和 16 kHz 单声道转换，因此正式运行时不需要再手动输入第 3 节音频测试命令。

状态文件位置：

```text
/home/root/labmate_b/data/state/latest_status.json
```

录音文件位置：

```text
/home/root/labmate_b/data/audio/asr_tests/
```
