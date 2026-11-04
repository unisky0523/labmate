r"""LabMate B board entry for ATK-ZYNQ.

Run on the board with Python 3.7:

    python3 board_app.py --source mock
    python3 board_app.py --source json --reading-json data/from_c/reading.json
    python3 board_app.py --no-vosk

Press Enter to record. Type text commands directly. Type q to quit.
"""

import argparse
from pathlib import Path
import sys
import time
import types

import main as core
import board_audio
import board_mic
import board_speaker
import board_sources
import board_ui
from text_cli import TextApplication


ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = ROOT / "models" / "vosk-model-small-cn-0.22"


def load_vosk_model(model_path):
    try:
        from asr_backend import Model, SetLogLevel
    except Exception as error:
        return None, "无法加载 Vosk 后端：%s" % error
    if not (model_path / "am" / "final.mdl").is_file():
        return None, "找不到完整模型：%s" % model_path
    try:
        SetLogLevel(-1)
        return Model(str(model_path)), None
    except Exception as error:
        return None, "Vosk 动态库或模型加载失败：%s" % error


def build_asr_args(model_path, min_word_confidence, confirm_repeat=False, confirm_readback=False,
                   max_seconds=30, confirm_seconds=3.0,
                   audio_device=board_mic.DEFAULT_CAPTURE_DEVICE, device=2,
                   command_grammar=False):
    return types.SimpleNamespace(
        mode="run",
        model=Path(model_path),
        min_word_confidence=min_word_confidence,
        grammar_fallback=True,
        command_grammar=command_grammar,
        confirm_repeat=confirm_repeat,
        confirm_readback=confirm_readback,
        max_seconds=max_seconds,
        confirm_seconds=confirm_seconds,
        audio_device=audio_device,
        device=device,
    )


def notify_record(record, path, status, playback_device):
    consistency = record.get("source_consistency")
    status.update(
        state="record_saved",
        record_id=record.get("record_id"),
        record_path=str(path),
        source_consistency=consistency,
    )
    if isinstance(consistency, dict) and consistency.get("status") == "conflict":
        try:
            board_speaker.alert(playback_device)
        except Exception as error:
            status.update(speaker_error=str(error))


def write_action_request(action, command, input_context, status):
    stamp = core.now_iso()
    path = ROOT / "data" / "requests" / ("%s_%s.json" % (action, stamp.replace(":", "").replace("+", "_")))
    request = {"action": action, "command": command, "input_context": input_context,
               "created_at": stamp}
    core.write_json_atomically(path, request)
    status.update(last_action=action, last_action_request=str(path))
    print("[动作请求] %s" % path)


def main():
    parser = argparse.ArgumentParser(description="LabMate B board runner")
    parser.add_argument("--source", choices=("mock", "json", "scpi"), default="mock")
    parser.add_argument("--reading-json", type=Path)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--audio-device", default=board_mic.DEFAULT_CAPTURE_DEVICE)
    parser.add_argument("--playback-device", default=board_audio.DEFAULT_PLAYBACK_DEVICE)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--mic-channel", type=int, choices=(0, 1), default=0,
                        help="选择麦克风声道：0 左，1 右；不直接平均两路")
    parser.add_argument("--confirm-seconds", type=float, default=3.0)
    parser.add_argument("--min-word-confidence", type=float, default=0.45)
    parser.add_argument("--command-grammar", action="store_true",
                        help="只使用项目命令词表识别，减少通用识别耗时")
    parser.add_argument("--no-vosk", action="store_true")
    parser.add_argument("--confirm-repeat", action="store_true")
    parser.add_argument("--confirm-readback", action="store_true")
    parser.add_argument("--no-es8388-init", action="store_true")
    parser.add_argument("--beep-on-error", action="store_true")
    args = parser.parse_args()

    status = board_ui.StatusBus()
    status.update(state="idle", source=args.source, audio_device=args.audio_device,
                  playback_device=args.playback_device)

    try:
        core.set_reading_source(board_sources.create_source(args.source, args.reading_json))
    except board_sources.ReadingError as error:
        print("[数据源错误] %s" % error)
        return 1
    core.set_record_observer(
        lambda record, path: notify_record(record, path, status, args.playback_device)
    )

    model = None
    if not args.no_vosk:
        model, model_error = load_vosk_model(args.model)
        if model_error:
            print("[语音识别] %s" % model_error)
            status.update(asr_error=model_error)
    asr_args = build_asr_args(args.model, args.min_word_confidence,
                              args.confirm_repeat, args.confirm_readback,
                              max_seconds=args.seconds,
                              confirm_seconds=args.confirm_seconds,
                              audio_device=args.audio_device,
                              command_grammar=args.command_grammar)

    original_stdout = sys.stdout
    sys.stdout = board_ui.ConsoleTee(original_stdout, status)
    application = TextApplication(confirm_batches=True)
    application.set_action_handler(
        lambda action, command, context: write_action_request(action, command, context, status)
    )

    print("LabMate B 板端入口")
    print("数据源：%s；录音设备：%s" % (args.source, args.audio_device))
    print("识别模式：%s" % ("命令词表" if args.command_grammar else "通用中文"))
    print("按回车录音，直接输入文字命令；输入 q 退出。")
    if model is None:
        print("当前没有 Vosk 模型，仍可使用文字命令和手动报数流程。")

    try:
        while True:
            try:
                answer = input("LabMate[board]> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已退出；未确认操作不会保存。")
                break

            if answer.lower() == "q":
                break
            if answer.startswith("/"):
                application.handle_text(answer[1:])
                continue
            if answer:
                application.handle_text(answer)
                continue

            try:
                status.update(state="recording", asr_partial="", last_error=None)
                capture_started = time.monotonic()
                audio, metadata = board_mic.capture_16k_mono(
                    args.seconds,
                    device=args.audio_device,
                    configure_es8388=not args.no_es8388_init,
                    channel=args.mic_channel,
                    playback_device=args.playback_device,
                )
                capture_elapsed = time.monotonic() - capture_started
                status.update(capture_seconds=round(capture_elapsed, 3))
                print("[耗时] 录音与转换：%.2f 秒" % capture_elapsed)
                audio_path = None
                if model is not None:
                    from asr_cli import process as process_asr
                    from asr_cli import save_audio
                    audio_path = save_audio(audio)
                    status.update(state="recognizing", audio_path=str(audio_path))
                    result, exit_requested = process_asr(
                        audio, audio_path, metadata, model, asr_args,
                        application=application, ask_label=False,
                        on_partial=lambda text: status.update(asr_partial=text),
                    )
                    recognition_elapsed = time.monotonic() - capture_started - capture_elapsed
                    status.update(recognition_seconds=round(recognition_elapsed, 3))
                    print("[耗时] 识别与确认：%.2f 秒" % recognition_elapsed)
                    status.update(
                        state="idle",
                        asr_text=result.get("text", ""),
                        asr_command=result.get("command"),
                        asr_error=result.get("reason"),
                    )
                    if exit_requested:
                        break
                else:
                    from asr_cli import save_audio
                    audio_path = save_audio(audio)
                    status.update(state="idle", asr_error="Vosk 未加载，仅保存了录音。")
                    print("录音已保存：%s" % audio_path)
            except Exception as error:
                status.update(state="error", last_error=str(error))
                print("[本次未完成] %s: %s" % (type(error).__name__, error))
                if args.beep_on_error:
                    try:
                        board_speaker.alert(args.playback_device)
                    except Exception:
                        pass
            time.sleep(0.05)
    finally:
        sys.stdout = original_stdout
        status.update(state="stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
