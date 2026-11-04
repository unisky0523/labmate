#!/usr/bin/env python3
"""LabMate JSON-lines backend: unchanged ASR, confirmed result records and history.

LABMATE_ASR_ROOT selects the frozen board recognition sources. With no root,
desktop simulation remains available. Only the owner loop writes protocol JSON;
one persistent worker owns the Vosk model, microphone and all ASR operations.
"""

import argparse
from collections import OrderedDict
import json
import math
import os
import queue
import signal
import sys
import threading


MAX_LINE = 65536
PROTOCOL = 1


def reject_constant(value):
    raise ValueError("Invalid JSON constant: " + value)


class Backend:
    def __init__(self, output, delay=1.5, fail_demo=False, recognizer=None,
                 record_store=None, store_error=None, command_executor=None):
        self.output = output
        self.delay = delay
        self.fail_demo = fail_demo
        self.events = queue.Queue(maxsize=128)
        self.state = "idle"
        self.operation_id = None
        self.cancel_event = None
        self.confirmation_event = None
        self.result = None
        self.seen = OrderedDict()
        self.recognizer = recognizer
        self.mode = "asr" if recognizer is not None else "demo"
        self.shutdown = threading.Event()
        self.jobs = queue.Queue(maxsize=4)
        self.real_worker = None
        self.record_store = record_store
        self.store_error = store_error
        self.command_executor = command_executor
        self.io_jobs = queue.Queue(maxsize=8)
        self.io_worker = None
        self.exit_requested = False
        self.exit_request_id = None
        self.history_edit_id = None
        if recognizer is not None:
            self.state = "initializing"

    def emit(self, event, request_id=None, operation_id=None, **fields):
        payload = dict(protocol=PROTOCOL, event=event, request_id=request_id,
                       operation_id=operation_id, state=self.state, mode=self.mode)
        payload.update(fields)
        self.output.write(json.dumps(payload, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")) + "\n")
        self.output.flush()

    def error(self, request_id, code, message):
        self.emit("error", request_id, self.operation_id,
                  code=code, message=message)

    def read_requests(self, source):
        try:
            while True:
                line = source.readline(MAX_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_LINE:
                    # Drain one oversized frame without retaining it in memory.
                    while line and not line.endswith("\n"):
                        line = source.readline(MAX_LINE + 1)
                    self.events.put(("invalid", "请求过长。"))
                    continue
                try:
                    request = json.loads(line, parse_constant=reject_constant)
                except (ValueError, RecursionError):
                    self.events.put(("invalid", "请求不是有效的 JSON。"))
                    continue
                self.events.put(("request", request))
        finally:
            self.events.put(("eof", None))

    def demo_worker(self, operation_id, cancelled):
        try:
            if cancelled.wait(self.delay):
                return
            if self.fail_demo:
                raise RuntimeError("测试用的后台识别失败；未执行任何操作。")
            result = {
                "text": "记录电压三点三伏",
                "summary": "模拟理解：记录电压 3.3 V，等待确认。",
                "command": {"intent": "record_manual", "measurements": [
                    {"quantity": "voltage", "value": "3.3", "unit": "V"}]},
                "simulated": True,
            }
            self.events.put(("result", (operation_id, cancelled, result)))
        except Exception as error:
            self.events.put(("worker_error", (operation_id, cancelled, str(error))))

    def clear_operation(self):
        self.stop_confirmation()
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.operation_id = None
        self.cancel_event = None
        self.result = None
        self.state = "idle"

    def stop_confirmation(self):
        if self.confirmation_event is not None:
            self.confirmation_event.set()
            self.confirmation_event = None

    def arm_confirmation(self):
        if self.mode != 'asr' or not hasattr(self.recognizer, 'recognize_confirmation'):
            return
        self.stop_confirmation()
        token = threading.Event()
        self.confirmation_event = token
        try:
            self.jobs.put_nowait(('confirmation', self.operation_id, token))
        except queue.Full:
            self.stop_confirmation()
            self.emit('confirmation_progress', self.operation_id, self.operation_id,
                      message='语音确认暂不可用，请点击“确认保存”。')

    def record_loop(self):
        """Disk operations cannot block ASR cancellation or the protocol owner."""
        while True:
            job = self.io_jobs.get()
            if job is None:
                return
            kind, request_id, operation_id, value = job
            if self.shutdown.is_set() and kind == "history":
                continue
            try:
                if self.record_store is None:
                    raise RuntimeError(self.store_error or "记录存储未配置，无法读取或保存记录。")
                if kind == "history":
                    result = self.record_store.list_page(value[0], value[1])
                elif kind == 'history_edit':
                    result = self.record_store.clear_records(**value)
                elif kind == 'annotation_preview':
                    result = self.record_store.prepare_annotation(value)
                elif kind == "instrument_preview":
                    result = self.command_executor.preview(value[0], operation_id, value[1])
                elif (value.get('command') or {}).get('intent') == 'annotate':
                    result = self.record_store.apply_annotation(value, operation_id)
                elif self.command_executor is not None and self.command_executor.handles(value):
                    result = self.command_executor.save(value, operation_id)
                else:
                    result = self.record_store.save_result(value, operation_id)
                error = None
            except Exception as failure:
                result, error = None, str(failure)[:512]
            # During shutdown no consumer remains; never hang joining a worker
            # whose completion queue is full. A submitted save still completes.
            while not self.shutdown.is_set():
                try:
                    self.events.put(("io_done", (kind, request_id, operation_id, result, error)), timeout=0.1)
                    break
                except queue.Full:
                    continue
            job = value = result = None

    def recognize_loop(self):
        """Sole owner of hardware/model. Even cancelled jobs close safely."""
        def initialization(message):
            self.events.put(("initialization", message))
        try:
            self.recognizer.prepare(self.shutdown, initialization)
            if self.shutdown.is_set():
                return
            self.events.put(("prepared", None))
            while not self.shutdown.is_set():
                try:
                    kind, operation_id, cancelled = self.jobs.get(timeout=0.1)
                except queue.Empty:
                    continue
                if cancelled.is_set():
                    continue
                def progress(message, op=operation_id, token=cancelled, job=kind):
                    event = 'confirmation_progress' if job == 'confirmation' else 'progress'
                    self.events.put((event, (op, token, message)))
                try:
                    if kind == 'calibration':
                        value = self.recognizer.calibrate(cancelled, progress)
                    elif kind == 'confirmation':
                        value = self.recognizer.recognize_confirmation(cancelled, progress)
                    else:
                        value = self.recognizer.recognize(cancelled, progress)
                    if value is not None and not cancelled.is_set():
                        event = 'voice_confirm' if kind == 'confirmation' else 'calibration_done' if kind == 'calibration' else 'result'
                        self.events.put((event, (operation_id, cancelled, value)))
                    value = None
                except Exception as error:
                    event = 'confirmation_error' if kind == 'confirmation' else 'worker_error'
                    self.events.put((event, (operation_id, cancelled, str(error))))
        except Exception as error:
            self.events.put(("prepare_error", str(error)))
        finally:
            try:
                self.recognizer.close()
            except Exception as error:
                # Diagnostics never share the protocol stream.
                print("Microphone cleanup: " + str(error), file=sys.stderr, flush=True)

    def handle_request(self, request):
        if not isinstance(request, dict):
            self.error(None, "invalid_request", "请求必须是 JSON 对象。")
            return True
        request_id = request.get("id")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 64:
            self.error(None, "invalid_id", "请求 id 必须是 1—64 个字符的字符串。")
            return True
        if type(request.get("protocol")) is not int or request["protocol"] != PROTOCOL:
            self.error(request_id, "protocol_mismatch", "通信协议版本不匹配。")
            return True
        if request_id in self.seen or request_id == self.operation_id:
            self.error(request_id, "duplicate_request", "请求编号重复，未重复执行。")
            return True
        self.seen[request_id] = None
        if len(self.seen) > 256:
            self.seen.popitem(last=False)

        action = request.get("action")
        if action == "quit":
            if self.state == "saving":
                self.exit_requested = True
                self.exit_request_id = request_id
                return True
            old_operation = self.operation_id
            self.clear_operation()
            self.state = "stopped"
            self.emit("stopped", request_id, old_operation, message="后台已退出。")
            return False
        if action == "status":
            self.emit("state", request_id, self.operation_id,
                      message="后台通信正常。", result=self.result)
            return True
        if self.exit_requested:
            self.error(request_id, "stopping", "正在完成保存并退出，请稍候。")
            return True
        if action in ('delete_record', 'clear_history'):
            if self.state != 'idle' or self.history_edit_id is not None:
                self.error(request_id, 'history_edit_busy', '请先完成当前识别、确认或保存，再清除历史记录。')
                return True
            if action == 'delete_record':
                record_id = request.get('record_id')
                if not isinstance(record_id, str) or len(record_id) != 32:
                    self.error(request_id, 'invalid_record_id', '记录编号无效。')
                    return True
                value = dict(record_id=record_id)
            else:
                revision = request.get('revision')
                if not isinstance(revision, str) or len(revision) != 64:
                    self.error(request_id, 'invalid_revision', '请刷新历史后重新确认清除。')
                    return True
                value = dict(revision=revision)
            try:
                self.io_jobs.put_nowait(('history_edit', request_id, None, value))
                self.history_edit_id = request_id
            except queue.Full:
                self.error(request_id, 'history_busy', '记录队列繁忙，请稍后重试。')
            return True
        if action == "history":
            page, size = request.get("page", 0), request.get("size", 4)
            if type(page) is not int or page < 0 or type(size) is not int or not 1 <= size <= 6:
                self.error(request_id, "invalid_page", "历史页码必须非负，每页显示 1—6 条。")
                return True
            try:
                self.io_jobs.put_nowait(("history", request_id, None, (page, size)))
            except queue.Full:
                self.error(request_id, "history_busy", "历史记录正在读取，请稍后刷新。")
            return True
        if action in ("start", "calibrate"):
            if self.state != "idle" or self.history_edit_id is not None:
                self.error(request_id, "busy", "本轮尚未结束，请先确认或取消。")
                return True
            if action == 'calibrate' and (self.mode != 'asr' or not hasattr(self.recognizer, 'calibrate')):
                self.error(request_id, 'calibration_unavailable', '当前后端不支持真实语音检测。')
                return True
            self.operation_id = request_id
            self.cancel_event = threading.Event()
            self.state = "running"
            if self.mode == "asr":
                try:
                    self.jobs.put_nowait(('calibration' if action=='calibrate' else 'command', request_id, self.cancel_event))
                except queue.Full:
                    self.clear_operation()
                    self.error(request_id, "busy", "上一轮识别正在收尾，请稍后重试。")
                    return True
                self.emit("state", request_id, request_id,
                          message="开始请求已接收，等待麦克风接收本轮语音。")
            else:
                self.emit("state", request_id, request_id,
                          message="Python 已收到开始请求，正在模拟识别。")
                worker = threading.Thread(target=self.demo_worker,
                                          args=(request_id, self.cancel_event), daemon=True)
                worker.start()
            return True
        if action not in ("confirm", "cancel"):
            self.error(request_id, "unknown_action", "不支持这个指令。")
            return True
        if not self.operation_id or request.get("target") != self.operation_id:
            self.error(request_id, "wrong_target", "本轮编号不匹配，未确认或取消其他轮次。")
            return True
        if self.state == "saving":
            self.error(request_id, "save_in_progress", "已经开始保存，请等待完成；不能重复确认或取消已提交的保存。")
            return True
        if action == "confirm" and self.state != "pending":
            self.error(request_id, "not_pending", "识别结果尚未就绪，不能确认。")
            return True

        if action == "confirm" and self.mode == "asr":
            value = dict(self.result)
            try:
                self.io_jobs.put_nowait(("save", request_id, self.operation_id, value))
            except queue.Full:
                self.error(request_id, "save_busy", "记录队列繁忙，结果已保留，请稍后再次确认。")
                return True
            self.state = "saving"
            self.stop_confirmation()
            instrument = self.command_executor is not None and self.command_executor.handles(value)
            command = value.get('command') or {}
            batch_message = ('正在连续记录 %d 次，间隔 %g 秒；每次保存两台仪表结果，请等待本批完成。' %
                             (command['count'], command.get('interval', 1))) if (
                                 instrument and command.get('intent') == 'record_device' and command.get('count', 1) > 1) else None
            self.emit("state", request_id, self.operation_id,
                      message=batch_message or ('正在执行 DG4102 操作并回读状态，请稍候。' if command.get('intent') == 'generator_control'
                                              else "正在采集仪器结果并保存，请稍候。" if instrument else "正在保存识别结果和记录时间，请稍候。"))
            return True

        old_operation = self.operation_id
        self.clear_operation()
        if action == "confirm":
            self.emit("confirmed", request_id, old_operation,
                      effect="demo_only",
                      message="本轮模拟识别已确认，未写入真实实验记录。")
        else:
            self.emit("cancelled", request_id, old_operation,
                      message="Python 已取消本轮；迟到的识别结果将被丢弃。")
        return True

    def run(self, source):
        threading.Thread(target=self.read_requests, args=(source,), daemon=True).start()
        self.io_worker = threading.Thread(target=self.record_loop, name="records-io")
        self.io_worker.start()
        if self.mode == "asr":
            self.emit("progress", message="正在准备真实语音后端，请稍候。")
            self.real_worker = threading.Thread(target=self.recognize_loop, name="asr-owner")
            self.real_worker.start()
        else:
            self.emit("ready", message="Python 后台已连接；当前使用模拟识别。")
        try:
            while True:
                kind, payload = self.events.get()
                if kind == "eof":
                    if self.state == "saving":
                        self.exit_requested = True
                    else:
                        return
                if kind == "invalid":
                    self.error(None, "invalid_json", payload)
                elif kind == "request":
                    if not self.handle_request(payload):
                        return
                elif kind == "initialization":
                    self.emit("progress", message=payload)
                elif kind == "prepared":
                    self.state = "idle"
                    self.emit("ready", message=getattr(self.recognizer, 'ready_message', '真实语音已就绪。点击开始后说话，句末停顿约 0.8 秒。'))
                elif kind == "prepare_error":
                    self.state = "failed"
                    self.emit("fatal", code="initialization_failed", message=payload)
                    return
                elif kind == "io_done":
                    job, request_id, operation_id, value, error = payload
                    if job == 'history_edit':
                        self.history_edit_id = None
                        if error is not None:
                            self.error(request_id, 'history_edit_failed', '清除未完成：' + error)
                        else:
                            self.emit('history_cleared', request_id,
                                      message='已清除 %d 条历史记录。' % value['cleared'], **value)
                        continue
                    if job == "history":
                        if error is not None:
                            self.error(request_id, "history_failed", "历史读取失败：" + error)
                        else:
                            self.emit("history", request_id, **value)
                        continue
                    if job in ("instrument_preview", 'annotation_preview'):
                        if operation_id != self.operation_id or self.state != "running" or self.cancel_event.is_set():
                            continue
                        if error is not None:
                            self.clear_operation()
                            self.emit("error", request_id, operation_id,
                                      code="preview_failed", message=error)
                        elif value is not None:
                            self.result = value
                            self.state = "pending"
                            self.emit("result", operation_id, operation_id,
                                      message="请核对目标数据，确认后执行；取消不修改。" if job == 'annotation_preview'
                                      else "仪器读数已返回，请核对后确认保存或取消。", **value)
                            self.arm_confirmation()
                        continue
                    if operation_id != self.operation_id or self.state != "saving":
                        continue
                    if error is not None:
                        self.state = "pending"
                        self.error(request_id, "save_failed", "保存未完成，结果已保留，可重试或取消：" + error)
                        self.arm_confirmation()
                    else:
                        updated = (self.result.get('command') or {}).get('intent') == 'annotate'
                        generator = (self.result.get('command') or {}).get('intent') == 'generator_control'
                        self.clear_operation()
                        self.emit("confirmed", request_id, operation_id,
                                  effect="record_updated" if updated else "record_saved",
                                  record=value, message="目标记录已更新，可在历史记录中查看。" if updated
                                  else value['content'] if generator else "语音记录已保存，可在历史记录中查看。")
                    if self.exit_requested:
                        self.clear_operation()
                        self.state = "stopped"
                        self.emit("stopped", self.exit_request_id, operation_id, message="后台已退出。")
                        return
                elif kind in ('voice_confirm', 'confirmation_progress', 'confirmation_error'):
                    operation_id, token, value = payload
                    if (self.state != 'pending' or operation_id != self.operation_id
                            or token is not self.confirmation_event or token.is_set()):
                        continue
                    if kind == 'voice_confirm':
                        self.stop_confirmation()
                        self.emit('voice_confirm', operation_id, operation_id,
                                  text=value['text'], message='听到“确认”，正在提交当前结果。')
                    elif kind == 'confirmation_error':
                        self.stop_confirmation()
                        self.emit('confirmation_progress', operation_id, operation_id,
                                  message='语音确认暂不可用，请点击“确认保存”：' + value)
                    else:
                        self.emit('confirmation_progress', operation_id, operation_id, message=value)
                elif kind == "progress":
                    operation_id, cancelled, value = payload
                    if operation_id == self.operation_id and cancelled is self.cancel_event and not cancelled.is_set():
                        self.emit("progress", operation_id, operation_id, message=value)
                elif kind in ("result", "worker_error", 'calibration_done'):
                    operation_id, cancelled, value = payload
                    # Both token identity and id are checked: cancelled work
                    # cannot alter a subsequent operation, even if it finishes late.
                    if (operation_id != self.operation_id or
                            cancelled is not self.cancel_event or cancelled.is_set()):
                        continue
                    if kind == 'calibration_done':
                        try:
                            self.recognizer.apply_calibration(value)
                        except Exception as failure:
                            self.clear_operation()
                            self.emit('error', operation_id, operation_id, code='calibration_failed', message=str(failure))
                            continue
                        self.clear_operation()
                        self.emit('calibration_result', operation_id, operation_id, **value)
                    elif kind == "result":
                        # Audio arrays must never reach JSON, including rejected
                        # results and status replies. They live only for this turn.
                        value.pop("_capture", None)
                        value = {key: item for key, item in value.items() if not key.startswith("_")}
                        command = value.get("command")
                        if self.mode == "asr" and (value.get("reason") or not isinstance(command, dict)):
                            self.clear_operation()
                            self.emit("rejected", operation_id, operation_id,
                                      message=value.get("reason") or "无法解析实验指令，请重说。", **value)
                            continue
                        if command.get('intent') == 'annotate' and self.mode == 'asr':
                            try:
                                self.io_jobs.put_nowait(('annotation_preview', operation_id, operation_id, value))
                            except queue.Full:
                                self.clear_operation()
                                self.emit('error', operation_id, operation_id, code='history_busy',
                                          message='记录队列繁忙，请稍后重试。')
                            continue
                        if self.command_executor is not None and self.command_executor.handles(value):
                            try:
                                value['summary'] = self.command_executor.describe(value)
                                if self.command_executor.needs_preview(value):
                                    self.io_jobs.put_nowait(('instrument_preview', operation_id, operation_id,
                                                              (value, cancelled)))
                                    self.emit('progress', operation_id, operation_id,
                                              message='正在通过 HOST4 获取采样并提交 FFT 分析，请稍候。' if command['intent'] == 'fft_analyze'
                                              else '正在回读信号发生器状态，不改变输出。' if command['intent'] == 'generator_control'
                                              else '正在读取万用表和示波器，取消不写入实验历史。')
                                    continue
                            except (ValueError, queue.Full) as failure:
                                self.clear_operation()
                                self.emit('rejected', operation_id, operation_id,
                                          message=str(failure), **value)
                                continue
                        self.result = value
                        self.state = "pending"
                        self.emit("result", operation_id, operation_id,
                                  message="识别结果已返回，请核对后确认或取消。",
                                  **value)
                        self.arm_confirmation()
                    else:
                        self.clear_operation()
                        self.emit("error", operation_id, operation_id,
                                  code="recognition_failed", message=value)
        finally:
            self.clear_operation()
            self.shutdown.set()
            # Drain submitted saves before releasing memory/exiting. History
            # jobs still in the queue are discarded after shutdown is set.
            self.io_jobs.put(None)
            self.io_worker.join()
            if self.real_worker is not None:
                # The owner terminates arecord/aplay and joins their reader.
                self.real_worker.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-delay", type=float, default=1.5)
    parser.add_argument("--demo-error", action="store_true",
                        help="Inject a worker error for integration checks")
    args = parser.parse_args()
    if not math.isfinite(args.demo_delay) or not 0 <= args.demo_delay <= 10:
        parser.error("--demo-delay must be between 0 and 10 seconds")
    recognizer = None
    if os.environ.get("LABMATE_ASR_ROOT"):
        from asr_adapter import BoardRecognizer
        recognizer = BoardRecognizer(os.environ["LABMATE_ASR_ROOT"])
    from pathlib import Path
    from record_store import RecordStore
    store, store_error = None, None
    try:
        runtime = os.environ.get("LABMATE_RECORD_RUNTIME") or os.environ.get("LABMATE_ASR_ROOT") or str(Path(__file__).parent / "asr_runtime")
        directory = os.environ.get("LABMATE_RECORD_DIR") or str(Path.home() / ".local/share/labmate/records")
        history = os.environ.get("LABMATE_HISTORY_DIRS", "").split(os.pathsep)
        store = RecordStore(runtime, directory, history)
    except Exception as error:
        store_error = str(error)
    executor = None
    if os.environ.get('LABMATE_INSTRUMENT_CONFIG'):
        try:
            from command_executor import CommandExecutor
            executor = CommandExecutor.from_file(os.environ['LABMATE_INSTRUMENT_CONFIG'], store)
        except Exception as error:
            # A configured real-instrument installation must fail explicitly,
            # rather than falling back to archiving only the command text.
            backend = Backend(sys.stdout, recognizer=recognizer, record_store=store)
            backend.state = 'failed'
            backend.emit('fatal', code='instrument_configuration_failed', message=str(error))
            return 2
    backend = Backend(sys.stdout, args.demo_delay, args.demo_error, recognizer, store, store_error,
                      command_executor=executor)
    def stop_on_signal(signum, frame):
        backend.events.put(("eof", None))
    signal.signal(signal.SIGTERM, stop_on_signal)
    signal.signal(signal.SIGINT, stop_on_signal)
    try:
        backend.run(sys.stdin)
    except (BrokenPipeError, KeyboardInterrupt):
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
