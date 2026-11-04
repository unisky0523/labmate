> 2026-10-30 后续更新：已有 V2 请使用 [仅更新记录功能步骤](labmate_ui_minimal_records_steps.md)。保存已改为仅保存识别结果；下文为此前方案的历史说明。

# 板端后台未连接：缺少 wave 的修复

2026-10-30。用户实机输出：Python 3.7.6，record_store.py 导入 wave 时出现 `ModuleNotFoundError: No module named 'wave'`。此前语音适配器在准备 ASR 时才添加 asr_runtime 路径，而记录模块在这个步骤之前导入，因而找不到已有的兼容模块。

本地已修复：记录模块读取历史不再导入 WAV 库；run_ui_voice.sh 在启动后台前设置 PYTHONPATH，并提前在串口执行导入检查。45 项本地检查通过，包含系统 wave/chunk/audioop 缺失的复现场景。该修复的板端验收仍待用户完成。

## 板端即时恢复：不用重新编译或上传

关闭屏幕上的助手，回到 `root@ATK-ZYNQ:...#` 提示符。在板端串口依次执行：

```sh
cd /home/root/labmate_ui_test
cp asr_runtime/wave.py ./wave.py
cp asr_runtime/chunk.py ./chunk.py
python3 -c "import wave, chunk; print(wave.__file__); print(chunk.__file__)"
python3 -c "import backend, record_store, asr_adapter; print('IMPORT_OK')"
```

兼容文件已经包含在用户上传的包中。这里只把两个模块复制到测试程序目录，不修改系统 Python，不接触实验 JSON。应看到两个模块的文件位置和 IMPORT_OK。模块名是 `asr_adapter`，不要漏字母。

这两份文件会保留，因此关闭、重开后仍可使用。后续正常上传修正后的 Windows 启动脚本和记录模块，也会直接使用冻结源码中的兼容模块。

## 校时：区分 Windows 与板端两个终端

1. 找到 Windows PowerShell，提示符形如 `PS C:\...>`。在这个窗口执行：

```powershell
"date -u -s '{0}'" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss')
```

2. 这条 PowerShell 表达式会打印一行以 `date -u -s` 开头的 Linux 命令。只复制打印出来的那一行到板端串口（提示符 `root@ATK-ZYNQ:...#`）执行。
3. 板端再执行以下命令，核对日期和 UTC 时间：

```sh
date -u
```

PowerShell 表达式不能直接放进板端 Linux shell。`date -u` 本身只查看时间，不能校时。不要修改旧 JSON 中的历史时间。

## 重启与验收

导入检查和校时完成后，在板端执行：

```sh
cd /home/root/labmate_ui_test
sh ./run_ui_voice.sh
```

若本次只是复制两个模块即时恢复，旧启动器不会新增打印 Backend imports OK；上面的手动 IMPORT_OK 已用于导入验证。下一次上传修复后的新启动脚本，终端会额外打印 Backend imports OK 和 wave 的文件位置，再打开界面。

等待模型/麦克风准备完成，检查后台连接和旧记录展示；再口述具体电压或电流，确认保存后核对新记录。直接取消不应新增记录，关闭重开后数据应保留。

后续需要同步本地修复文件时，仍在 Windows 手动运行 `tools/upload_ui_serial.ps1 -PortName COM6 -RealAsr`，使用现有 V2 ARM 程序即可。先退出板上助手并断开串口工具，再执行上传。
