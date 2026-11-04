"""Read-only board diagnostic: same failed WAV, three decoding modes.

This does not call the application, change project files, or save records.
The phrase grammar is experimental, not a strict sentence constraint.
"""
import json
import time
from pathlib import Path

import numpy as np

from board_app import load_vosk_model, DEFAULT_MODEL
from asr_cli import read_audio_file, transcribe, GRAMMAR_JSON

path = Path("data/audio/asr_tests/asr_20230420_054354_819689_cd6f4d9d.wav")
audio = read_audio_file(path, 30)
print("FILE", path.name, flush=True)
print("AUDIO RMS/PEAK/DC", round(float(np.sqrt(np.mean(audio ** 2))), 5),
      round(float(np.max(np.abs(audio))), 5), round(float(np.mean(audio)), 5), flush=True)
model, error = load_vosk_model(DEFAULT_MODEL)
if model is None:
    raise RuntimeError(error)

phrases = ["读取 数据", "当前 状态", "查看 记录", "确认", "取消", "[unk]"]
digits = list("零一二三四五六七八九")
for quantity, unit in (("电压", "伏"), ("电流", "安")):
    for whole in digits:
        phrases.append("记录 %s %s %s" % (quantity, whole, unit))
        for decimal in digits:
            phrases.append("记录 %s %s 点 %s %s" % (quantity, whole, decimal, unit))

for name, grammar in (("NORMAL", None), ("WORDS", GRAMMAR_JSON),
                      ("PHRASES", json.dumps(phrases, ensure_ascii=False))):
    print("START", name, flush=True)
    started = time.perf_counter()
    result = transcribe(audio, model, grammar=grammar)
    print(name, "SECONDS", round(time.perf_counter() - started, 2), flush=True)
    print("TEXT", result["text"], flush=True)
    print("WORDS", [(word.get("word"), word.get("conf"))
                    for word in result["words"]], flush=True)
