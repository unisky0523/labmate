# 语音依赖

提交包保留 libvosk.so、libatomic 和板端依赖说明。预训练中文模型按固定版本与原模型逐文件 SHA256 获取：

```sh
python -B build/fetch_dependencies.py --workspace /path/to/labmate_repro
```

原项目完整模型仍保留在本地完整备份中，可使用 `--from-full` 离线复用。模型来源和哈希清单见 `data/dependencies/vosk_model_manifest.json`。首次真实语音运行前必须完成模型准备。
