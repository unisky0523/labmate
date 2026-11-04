# 测试输入、模型与证据

| 路径 | 内容和使用说明 |
| --- | --- |
| `logs/asr_response_log.md` | 十组团队手动实测日志，按用户澄清更正数据性质，原始测量数值不变。 |
| `asr_response_measurements.csv` | 同一组手动实测的英文列名副本，`kind=measurement`、`measurement_method=manual`。 |
| `asr_measurement_statistics.json` | 直接从实测 CSV 计算的统计：中位数 5.595 s / 1.605 s，中位耗时降低约 71.3%。 |
| `asr_measurement_template.csv` | 供后续追加复测的空表，未填行状态为 `pending`。 |
| `asr_samples/` | 已有历史录音和原始采样，供对照调试；不额外声称属于本次手动测量。 |
| `fft_vectors/` | HOST4 实际取点、合成输入和软件参考输出，保留各目录元数据。 |
| `models/voice/` | libvosk.so、libatomic 和板端依赖说明；预训练中文模型按 `dependencies/vosk_model_manifest.json` 自动获取并校验。 |
| `models/vision/` | 原摄像头/OCR 工程字表和模型，由准备脚本恢复原位置。 |
| `dependencies/arm/` | 已有 ARM wheel、libatomic deb 等依赖。 |
| `dependencies/linux/` | 原 Linux 离线构建包的主机 deb 和来源/校验记录。 |
| `logs/development/` | 原 ARM、仪器、桌面、语音、FFT、扫频和 Linux 部署核验记录。 |
| `logs/accepted_sweep/` | 已冻结扫频版本的清单和核验材料。 |

ASR CSV 的 `status=measured` 表示用户已报告的手动计时；不将它伪装成自动化识别状态记录。两组有效手动计时直接纳入配对统计。后续复测也可记录 `correct`、`incorrect`、`timeout`，其中正确配对参与耗时统计，其他状态另列数量。原日志附件在 `report/history/asr_response_log_original.md` 保留原始字节，旧的数据标签以用户本次确认和当前实测日志为准。

原附件的 60 fps 录像、预热和统一版本等内容是后续复测方案，不作为本批手动测量已经执行的条件。已有测试夹具随各模块源码保留，用户个人实验历史未整体当作测试夹具打包。
