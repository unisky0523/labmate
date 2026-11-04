# LabMate 小型关键词 CNN 训练计划

## 1. 当前数据量不够

当前模板目录大概只有每条命令 3～6 条录音。这个数量只适合 MFCC + DTW，不适合从零训练 CNN。

20～50 条/类也偏少，尤其是同一个人、同一个麦克风、同一天录制时，很容易过拟合。

## 2. 建议的数据规模

第一版原型：

```text
3 个说话人
× 2 个录制场次
× 每条命令 20～30 次
= 每条命令 120～180 条
```

另外需要：

```text
unknown：其他中文短句，至少 100～300 条
silence：静音和底噪，至少 100 条
```

如果只要求你们三个人使用，可以先用 3 人 × 2 场次 × 10 次/类，观察效果，但最终报告不能宣称多人泛化。

## 3. 数据格式

```text
16 kHz
单声道
16 bit PCM
每条 1.0～1.5 秒
```

目录：

```text
kws_data/
├── read/
├── record/
├── capture_image/
├── save_waveform/
├── status/
├── confirm_yes/
├── confirm_no/
├── unknown/
└── silence/
```

文件名建议包含说话人和场次：

```text
read/speaker1_session1_001.wav
read/speaker2_session1_001.wav
```

## 4. 防过拟合的关键

不要随机把同一段录音切成训练集和验证集，否则会虚高。

按说话人或场次划分：

```text
训练：speaker1/session1 + speaker2/session1
验证：speaker1/session2
测试：speaker3/session2
```

训练集才做增强：

```text
随机时间平移
随机音量变化
加入风扇/实验室底噪
SpecAugment 时间和频率遮挡
轻微语速或音高变化
```

模型侧：

```text
小模型
Dropout
权重衰减
EarlyStopping
标签平滑
类别权重
```

## 5. 推荐模型

输入：

```text
log-Mel 频谱
40 个 Mel 频带
约 100 帧
```

结构：

```text
Conv2D 16, 3x3
BatchNorm + ReLU + MaxPool
Conv2D 32, 3x3
BatchNorm + ReLU + MaxPool
Depthwise Conv
GlobalAveragePooling
Dropout
Dense 32
Softmax 9 类
```

类别：

```text
read
record
capture_image
save_waveform
status
confirm_yes
confirm_no
unknown
silence
```

目标参数量：

```text
30k～100k
```

导出：

```text
int8 TFLite
```

## 6. 训练环境

不要用板端 Python 3.7 训练。电脑上单独建一个 Python 3.10 环境。

```powershell
py -3.10 -m venv D:\kws_env
D:\kws_env\Scripts\activate
pip install tensorflow-cpu==2.15.0 tensorflow-model-optimization soundfile sounddevice numpy
```

训练流程：

```text
录音采集
-> 切分/补齐到 1 秒
-> 计算 log-Mel
-> 按说话人/场次划分
-> 训练小 CNN
-> 验证集 early stopping
-> 测试集评估
-> int8 TFLite 导出
```

## 7. 板端部署问题

TFLite Python 运行时在 ARMv7 + Python 3.7 上不一定有现成 wheel。

可行路线：

1. C++ TFLite Micro 或自定义 C 推理。
2. 训练后导出权重，用 NumPy/C 实现小型推理。
3. 用 Vitis HLS 把卷积层放到 PL。
4. 第一版继续用 MFCC + DTW，不让 CNN 阻塞主流程。

Vitis AI 不适合作为当前 Zynq-7010 的首选路线，重点应放在小模型和音频前端。

## 8. 当前建议

```text
现在：MFCC + DTW 做固定命令
同时：按协议收集 3 人 × 2 场次数据
之后：训练 30k～100k 参数的小 CNN
最终：固定命令走 CNN，数字报数继续走 Vosk
```

不要在现有 3～6 条/类模板上直接训练 CNN，也不要把同一条录音增强后同时放进训练集和测试集。
