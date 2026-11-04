> 2026-10-30 后续更新：已有 V2 请使用 [仅更新记录功能步骤](labmate_ui_minimal_records_steps.md)。保存已改为仅保存识别结果；下文为此前方案的历史说明。

# 实验助手：历史数据与记录时间更新步骤

2026-10-30，源码版本 `LABMATE_UI_RECORDS_V2`。用户已完成 ARM 编译、上传和界面启动；历史和保存仍待板端验收。随后发现板端精简 Python 缺少 wave，兼容修复和即时恢复步骤见 `docs/labmate_ui_wave_fix_steps.md`。已有 Ubuntu、Qt 和 SDK 继续使用。

## 界面变化

新增“历史记录”页签，每页四条，支持刷新、上一页和下一页。列表包含数据内容、单位、记录时间、来源和状态。点选一条，查看原始话语、采集/报数时间、确认时间、原始保存时间、记录编号和批注。

已知旧记录按北京时间显示的示例：

| 数据内容 | 记录时间 | 来源 | 状态 |
| --- | --- | --- | --- |
| 电压 3.3 V | 2023-04-16 11:29:49 | 模拟数据 | 正常 |

它是此前已经保存的模拟记录，不是本次生成的数据。两个旧目录中的同一编号只显示一条。详情中保留原始保存时间 `2023-04-16T03:29:49.157+00:00`，不会改成今天。

只能显示已经写入文件的记录。旧 GUI 的确认没有保存文件，那部分结果无法自动补回。新版本口述具体数值后点“确认保存”，才会新增 JSON 和对应 WAV，并刷新历史。

## 1. 把完整工程复制到 Ubuntu

关闭 Ubuntu 中 Qt Creator 和预览窗口。在文件管理器中，把旧 `/home/labmat/labmate_ui` 重命名为一个未使用的备份名称。

把 Windows `D:\fpga amd xinlx\work\labmate_ui` 整个文件夹复制到 Ubuntu `/home/labmat`。也可解压 Windows `dist/labmate_ui_records_v2_20261030.zip`，取其中的 `labmate_ui` 文件夹。

新目录应有 `main.cpp`、`labassistant.pro`、`resources.qrc`、`backend.py`、`asr_adapter.py`、`record_store.py`、`asr_runtime/` 和 `tests/`。不能只替换 main.cpp 或只复制后台。

## 2. 在已有 SDK 中交叉编译

Ubuntu 新终端依次执行：

```sh
source "$HOME/petalinux_sdk_2020_2/environment-setup-cortexa9t2hf-neon-xilinx-linux-gnueabi"
mkdir -p "$HOME/labmate_ui_build_arm_records"
cd "$HOME/labmate_ui_build_arm_records"
qmake "$HOME/labmate_ui/labassistant.pro"
make -j2
file labassistant
```

应无编译错误，`file` 报告 ELF32 ARM。将 `/home/labmat/labmate_ui_build_arm_records/labassistant` 复制回 Windows，替换：

```text
D:\fpga amd xinlx\dist\armhf\labassistant
```

用户已复制回本次 ARM 二进制（1548088 字节）。后续改动 C++ 或内嵌资源时仍按本节重新编译；此次 wave 兼容修复使用外置 Python 和启动脚本，不需要重新编译 Qt。上传器会检查 V2 标记，阻止旧程序与新后台混用。

## 3. 手动上传

板载屏幕先关闭助手，等待串口出现 root 提示符；再断开占用 COM6 的串口工具。保持板卡通电，在 Windows PowerShell 手动执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\fpga amd xinlx\tools\upload_ui_serial.ps1" -PortName COM6 -RealAsr
```

看到 `__LM_UPLOAD_OK__` / `UPLOAD OK.` 后再继续。上传包含记录存储、后台和启动脚本；模型和库复用板上已有资源。

仅做本地打包检查时可以添加 `-PrepareOnly`，它不会打开串口。这个模式下旧二进制只发警告，便于检查文件包；不表示旧二进制可以实际部署。

## 4. 先校时，再写新记录

用串口工具重新连接 COM6（115200，8N1，无流控），先不要启动助手。此前板卡时间停在 2023 年。

在 Windows PowerShell 执行以下表达式。它只按电脑当前时间打印一条命令，不连接板卡：

```powershell
"date -u -s '{0}'" -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss')
```

立即将输出的整条 `date -u -s '...'` 命令复制到板端串口执行，再执行：

```sh
date -u
```

核对日期与 UTC 时间和电脑一致。界面显示时转换为北京时间。不要把文档里的固定时间当成当前时间，也不要修改旧 JSON。

当前没有自动校时或 `-SyncClock` 参数。板卡掉电重启后若再次回到 2023 年，需重新校时。程序会拒绝年份早于 2026 的新保存，但这不能代替核对实际时钟。校时前已录音的本轮需取消后重录。

## 5. 启动与验收

板端执行：

```sh
cd /home/root/labmate_ui_test
sh ./run_ui_voice.sh
```

依次检查：

1. 切到“历史记录”，旧 3.3 V 记录只出现一条，来源为“模拟数据”，日期仍在 2023 年；点选能看详情。
2. 等麦克风就绪，切回“语音识别”，点击开始，等待说话提示，说“记录电压三点三伏”。
3. 核对文字和数值后点“确认保存”。保存中按钮禁用；出现实际保存成功提示后，历史页应增加当前时间的新记录，来源为“语音报数”。
4. 再说“记录电流十毫安”，确认后应有电流和 mA 单位。
5. 新一轮识别后直接取消，历史总条数不增加。
6. 关闭助手再启动，新旧记录均仍可查看。超过四条后检查翻页。

保存失败会保留本轮结果，先看错误并刷新历史；重试同一轮按操作编号恢复，避免“已写入但回复失败”造成重复。尚未确认时直接取消不保存；已经提交保存时不能再取消，关闭会等待该次保存完成。

“记录数据”等没有具体数值的仪表采集命令会明确提示尚未接入，不会生成假记录。模型初始化或识别期间可以查看历史。

## 文件与排查

新 JSON：`/home/root/labmate_ui_test/data/records/record_*.json`。

新 WAV：`/home/root/labmate_ui_test/data/audio/gui_records/asr_gui_*.wav`。

旧目录只读：`/home/root/labmate_b_audio_test/data/records` 和 `/media/sd-mmcblk0p1/labmate_b_board_20261015/data/records`。

关闭助手回到串口后查看错误日志：

```sh
cat /home/root/labmate_ui_test/run.log
```

修改前备份：`D:\fpga amd xinlx\backups\labmate_ui_before_history_20261030_214039`。

2026-10-30：Windows Python 3.14.4 / NumPy 2.5.3 下，43 项后台/文件测试全部通过，无跳过。18 个 Python 文件通过 Python 3.7 语法解析；13 个冻结文件及对应原文件哈希均未改变；PowerShell、shell 语法、资源文件、接收白名单和 `-PrepareOnly` 检查通过。

wave 兼容修复后增至 45 项本地测试，均通过；缺少系统 wave/chunk/audioop 的场景使用导入限制器复现，并校验本地兼容 WAV 的 PCM 内容。本地检查不能替代该修复的板端运行及历史/保存验收。所有串口更新和板端命令仍由用户手动执行。
