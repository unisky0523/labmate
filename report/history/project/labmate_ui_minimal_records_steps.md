# 保留原版语音，只更新保存和显示

> 2026-11-01 已正式部署并固定：[发布版与运行说明](../dist/labmate_ui_verified_20261101/README_CN.md)。板卡 20/20 文件一致，原两条历史记录保留，3.3 V 识别、保存、历史和时间通过验收。唯一语音源码修复是在持续采集里明确使用已验证的 msb-first 解码。用户要求暂缓“十毫安→十二安”的误识别，保持此版本。以下旧版对照、临时检测和恢复步骤仅供追溯。

> 当前下一步：原始采样检测已完成，当前解码将安静持续判为有声；低三字节倒序解释则出现清楚的安静/说话阶段差异，尚需实际识别验证。SD 卡只读扫描另报告文件系统错误，但原语音基线、ZIP 和模型通过校验，卡上可读取文件已备份。参见 [SD 与音频检查结论](labmate_sd_and_pcm_findings_20261101.md)。卡放回板卡后，使用其中的 [一次临时界面对照命令](labmate_ui_pcm_trial_serial_command.txt)，保持原源码和模型，继续使用新版界面；不再重复上传或采样检测。

> 最新：用户已完成原 Qt 对照，旧版也无法识别。新版从未被覆盖，退出旧窗口后运行 `sh ./run_ui_voice.sh` 即可回到新版。当前改查共用的音频运行状态，参见 [本轮结果](labmate_ui_board_version_check_20261101.md)，不再重复版本核对或原 Qt 对照。

> 已完成的版本核对：12 个语音源码和 3 个记录补丁文件全部匹配，启动路径正确。实际结果见 [板端核对结论](labmate_ui_board_version_check_20261101.md)。[原 Qt 对照命令](run_original_qt_serial_command.txt) 保留供追溯，用户已完成对照且反馈旧版同样失败，不再重复执行。

> 以下保留本轮已完成的核对步骤。“25 秒内未收到完整语音”发生在识别结果返回和保存之前；版本核对不能代替板端语音验收。当前按上面的最新结论继续，不重复上传或恢复。

关闭助手、等串口出现 root 提示符，再断开串口工具。在 Windows PowerShell 执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\fpga amd xinlx\tools\check_ui_voice_serial.ps1" -PortName COM6
```

此命令只读取文件，不替换程序、不恢复备份、不启动识别或录音。输出 `VOICE_MATCH 12/12` 表示板上 12 个语音源码与新增记录前版本逐字节相同；`RECORDS_MATCH 3/3` 表示后台、存储模块和启动脚本与本地当前补丁一致。不同的文件会单独输出 `DIFFERENT`，V1 备份也会比较内容，而不只依赖版本标记。输出保存在 `work/ui_voice_version_check_latest.log`。将输出返回后再决定需要更新的具体文件。

---

2026-10-30。本步骤取代此前重新编译、传整套语音和保存 WAV 的方案。现有 V2 ARM 界面继续使用。

## 这次收回的改动

- `asr_adapter.py` 已恢复到 `backups/labmate_ui_before_records_20261029` 的原文件；适配器及语音运行目录共 15 个文件通过逐字节 SHA256 核对。
- 保存模块只接收原识别器已经返回的文字、解析数值和确认时间，确认后写 JSON；取消不写。保存不再依赖原始音频、NumPy、wave 或 chunk。
- 不再额外拒绝原识别器已经接受的其他指令。有明确电压/电流的结果按数值展示；没有实际读数的指令按“语音指令”保存原话，不产生虚构仪表数值，也不调用仪表或摄像头。
- 新结果记录为 schema 3 的 `voice_result`，来源明确标为语音报数/语音指令，无原始录音证据。旧 schema 2 记录、原时间和模拟标记继续读取。
- 系统时间异常只标注和提醒，不再阻断原来的语音确认流程。
- 普通 `-RealAsr` 更新默认保留板上 `asr_adapter.py` 和整个 `asr_runtime`。只有明确的首次部署 `-InstallAsrRuntime` 才会重新安装本地语音副本。

## 一次更新

关闭板上助手，等 root 提示符出现，断开占用 COM6 的串口工具。在 Windows PowerShell 执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\fpga amd xinlx\tools\upload_ui_serial.ps1" -PortName COM6 -RealAsr -RecordsOnly -RestoreVoiceBaseline
```

该命令只传后台、存储模块、启动器和恢复工具这 4 个小文件，Qt 二进制、模型和数据目录不在包内。它会自动在板上寻找完整的、更新前 ASR V1 上传备份，从同一批备份恢复原语音文件；恢复前另存当前文件，不删除原备份。

找不到完整旧版备份或当前界面不是 V2 时，接收器会在替换程序文件之前停止。此时保留错误输出，不改参数或重新安装模型。如果提示 `VOICE_BASELINE_IDENTICAL`，表示当前语音文件已经与所选上传前备份相同，不能据此声称语音故障已修复。

看到 `UPLOAD OK` 后，重新连接串口并在板卡执行：

```sh
cd /home/root/labmate_ui_test
sh ./run_ui_voice.sh
```

按昨天的正常方式说话、核对、确认，再到历史页看内容和记录时间。此处是实际板端验收，本地测试不能代替。

## 本地验证

53 项检查通过：原语音文件精确匹配、原结果无录音即可保存、缺少所有音频库仍可保存、取消/重试/去重/历史显示，以及临时目录中的接收器和备份恢复测试。恢复失败回滚语音文件、缺少完整备份则不替换、保留现有界面与历史数据均有测试。

小更新包预打包约 12 KB、11 个串口分块；未连接串口、未上传或操作板卡。Python 3.7 语法检查通过。当前 Windows 沙箱下 Git Bash 无法启动，未据此声称本轮运行过 shell 解析器；启动脚本的原音频流程保留，仅移除新增音频依赖检查并增加记录路径配置。
