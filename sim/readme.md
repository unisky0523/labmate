# 仿真、离线验证与参考结果

当前提供的是已有 ARM 离线检查及 FPGA 历史综合实现报告。所收输入没有专用音频前端 RTL testbench，本目录不宣称完成本次 RTL 仿真。

在根目录运行：

```sh
python -B sim/run_checks.py --workspace /path/to/labmate_repro --out /path/to/new_results
python -B sim/analyze_asr.py data/asr_response_measurements.csv
```

本次已运行的 220 项检查日志位于 `results/`。提交副本只保留最终通过日志；最初的环境排查记录保存在完整备份。历史的 FPGA 构建报告见 `build/reports/fpga/`，软件 FFT 参考见 `fft_reference.py` 与 `data/fft_vectors/`。

ESP32 专用解析器测试依赖本次不纳入的 MCU 源码，因此未收录也未执行，不计入本次通过项数。
