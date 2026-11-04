> 2026-10-30 后续更新：已有 V2 请使用 [仅更新记录功能步骤](labmate_ui_minimal_records_steps.md)。保存已改为仅保存识别结果；下文为此前方案的历史说明。

# 板载实验助手：更新真实语音版

2026-10-29。由用户手动操作，不接管电脑或 COM6。

**后续实机进展：** 用户已反馈真实版“目前功能比较正常”，并提供板载屏幕的收音、识别文字和解析拒绝原因照片。真实语音到 Qt 显示链路已获实机证据；照片中的当前句子未通过指令解析检查，不能据此声称该句正确理解或记录保存已完成。以下操作保留作为部署/复现步骤，文末“待验收”是此前准备阶段的历史状态。

## 当前已确认

板载 Qt 窗口、中文、开始按钮到 Python 模拟结果返回、关闭后恢复出厂桌面均已有用户照片/终端证据。板端 `/home/root/labmate_b_audio_test` 已存在语音模块、libvosk.so、模型 am/final.mdl，`import numpy` 成功。用户输出为 numpy.version 模块，不据此假设 NumPy 精确版本。

这次源码加入真实语音模式，需要重新交叉编译一次 Qt。当前 Windows `dist/armhf/labassistant` 仍是旧模拟程序，上传器会阻止将它作为真实版部署。

## 1. 更新 Ubuntu 工程

关闭 Ubuntu 中 Qt Creator 和仍在运行的电脑预览窗口。在 Ubuntu 文件管理器 Home 中，将现有 `labmate_ui` 改名为 `labmate_ui_demo`（已有同名备份则换一个未使用名字）。

在 Windows 复制整个 `D:\fpga amd xinlx\work\labmate_ui` 文件夹到 Ubuntu Home，最终路径仍为 `/home/labmat/labmate_ui`。至少应有 main.cpp、labassistant.pro、resources.qrc、backend.py、asr_adapter.py、asr_runtime/、tests/。不使用旧的模拟版 ZIP。

## 2. Ubuntu 中交叉编译

打开 Ubuntu 终端，依次执行：

```sh
source "$HOME/petalinux_sdk_2020_2/environment-setup-cortexa9t2hf-neon-xilinx-linux-gnueabi"
mkdir -p "$HOME/labmate_ui_build_arm_voice"
cd "$HOME/labmate_ui_build_arm_voice"
qmake "$HOME/labmate_ui/labassistant.pro"
make -j2
file labassistant
```

应无 error，并报告 ELF32 ARM，而不是 x86-64。此 ARM 文件不在 Ubuntu 中直接运行。

## 3. 取出新程序

Ubuntu 文件管理器 Ctrl+L 输入 `/home/labmat/labmate_ui_build_arm_voice`，复制 `labassistant`，粘贴到 Windows `D:\fpga amd xinlx\dist\armhf`，替换旧同名文件。

## 4. 在 Windows 上传

先在板载屏幕关闭正在运行的实验助手，等待串口出现 root 提示符；再断开占用 COM6 的串口工具。保持板卡通电，在 Windows PowerShell 执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\fpga amd xinlx\tools\upload_ui_serial.ps1" -PortName COM6 -RealAsr
```

必须看到 `__LM_UPLOAD_OK__` / `UPLOAD OK.` 后再继续。如果提示 old demo executable，说明取出的仍是旧文件或编译的是旧工程，应回到前两步核对，不跳过检查。

此次上传还会携带后台、适配器和单独的 Python 语音源码副本；大模型和动态库复用板上已有文件，不重新传输。已有同名测试文件会备份。不会覆盖出厂桌面或旧语音测试目录。

## 5. 板端启动

重新用串口工具连接 COM6，115200、8N1、无流控。在板端终端执行：

```sh
cd /home/root/labmate_ui_test
sh ./run_ui_voice.sh
```

这是新真实语音启动器。`run_ui_test.sh` 单独使用、且未设置语音环境时仍用于模拟模式。

启动阶段应显示加载模型、初始化麦克风，再显示“麦克风已就绪 · 真实识别”。首次打开会加载模型并进行原有音频预热，实机耗时待测；同一次打开中的后续识别复用模型和录音流，不在每次按开始时重新预热。助手打开后麦克风保持采集就绪，空闲音频只在有限内存中分句；点击开始后才选择本轮新语音送去识别，不保存录音文件。

## 6. 第一次实际语音验收

1. 等待就绪后点“开始识别”。
2. 等待“现在请说话”提示，说“记录电压三点三伏”。
3. 句末安静约 0.8 秒，等待识别完成。应显示实际文字和解析结果。
4. 点确认结束本轮。本阶段确认仅核对结果，不写实验记录，不调用仪表或摄像头。
5. 再开始一次，说“记录电流十毫安”，验证结果随语音变化。
6. 测试开始后取消，再重新开始；取消前的语音不应变成下一轮可确认的旧结果。
7. 点关闭助手，等待释放 arecord/aplay 并恢复出厂桌面。

单句保留原来 12 秒上限、0.8 秒句尾静音、0.01 能量门限、左声道、44100 Hz 双声道 S24_LE、ES8388 配置；使用原命令短语词表和 0.45 最低词置信度筛查。未通过检查时仍显示文字/原因，确认不可用。收到开始请求后 25 秒内无完整句子会提示重试。

若提示音频设备被占用，先停止之前的语音/播放测试，再重启；启动器不会擅自杀其他录音进程。若出现异常，保留屏幕错误文字，并在关闭窗口回到串口后查看：

```sh
cat /home/root/labmate_ui_test/run.log
```

## 实现与验证范围

源代码备份：`backups/labmate_ui_before_real_asr_20261029`。语音副本取自用户指定的 `labmate_b_board_20261015(1)/labmate_b_board_20261015`，所选原文件未修改，冻结文件哈希见 `work/labmate_ui/asr_runtime/baseline.json`。

适配器复用 ContinuousMicrophone 和 asr_cli.analyze，不调用 board_listen.run、asr_cli.process 或 TextApplication 的终端确认/实验分派链。单个工作线程持有模型和录音对象，取消令牌和轮次编号共同过滤迟到结果。界面支持真实模式标签、初始化与识别进度、拒绝结果显示及独立后台路径，之后 Python 更新可复用此 Qt 版本。

本机 20 项后台/适配器检查通过，覆盖模拟兼容、取消重试、旧音频过滤、初始化失败、关闭初始化中任务、资源所有权及确认不写记录。新 Python 文件与冻结语音源码通过 Python 3.7 语法检查；上传包本地打包/解包检查通过。测试注入了麦克风/Vosk替身，不能作为真实识别准确率或板端清理通过的证据。本机未编译新 Qt，也未连接串口部署新版本；还需用户完成上述编译、上传与实机验收。
