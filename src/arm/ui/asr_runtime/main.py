r"""LabMate B 第一步：键盘命令、模拟读数、统一记录写入和查询。

运行：.\.venv\Scripts\python.exe main.py
本程序只使用 Python 标准库，不需要安装新依赖。
get_reading 的仪表读数仍为模拟数据；后续由 C 的接口替换。
text_cli.py 另支持人工输入记录；保留其来源，不冒充仪表采集。
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import math
import re
from pathlib import Path
from uuid import uuid4


PROJECT_DIR = Path(__file__).resolve().parent
RECORD_DIR = PROJECT_DIR / "data" / "records"
_READING_SOURCE = None
_RECORD_OBSERVER = None

# SI prefixes are case-sensitive: m (milli) and M (mega) must stay distinct.
METRIC_PREFIXES = (('', ''), ('毫', 'm'), ('微', 'u'), ('纳', 'n'),
                   ('皮', 'p'), ('千', 'k'), ('兆', 'M'))
MANUAL_UNITS = {quantity: {prefix + base for _, prefix in METRIC_PREFIXES}
                for quantity, base in (('voltage', 'V'), ('current', 'A'), ('frequency', 'Hz'))}


def set_reading_source(source):
    """Set the board reading source; it must expose read(request_id, simulate_failure=False)."""
    global _READING_SOURCE
    _READING_SOURCE = source


def set_record_observer(callback):
    """Register a callback(record, path) called after a record is written."""
    global _RECORD_OBSERVER
    _RECORD_OBSERVER = callback


def now_iso():
    """保存带本机时区的时间。"""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def get_reading(request_id, simulate_failure=False):
    """模拟 C 提供的接口，每次调用返回一条新的采集结果。"""
    if _READING_SOURCE is not None:
        return _READING_SOURCE.read(request_id, simulate_failure=simulate_failure)
    return {
        "request_id": request_id,
        "device_id": "mock_meter_01",
        "source": "mock",
        "is_simulated": True,
        "value": None if simulate_failure else 3.30,
        "raw_text": None if simulate_failure else "3.30 V",
        "unit": "V",
        "valid": not simulate_failure,
        "captured_at": now_iso(),
        "image_path": None,
        "error_code": "MOCK_READ_FAILED" if simulate_failure else None,
    }


def validate_reading(reading):
    """无效结果不能保存为正常记录。"""
    if reading.get("valid") is not True:
        raise ValueError(f"读数无效：{reading.get('error_code')}")
    if reading.get("record_kind") == "manual":
        if reading.get("source") not in {"manual_text", "manual_voice"} or reading.get("is_simulated") is not False:
            raise ValueError("人工输入记录的来源标记无效。")
        if reading.get("source") == "manual_voice" and not reading.get("audio_path"):
            raise ValueError("语音报数记录缺少原始录音路径。")
        measurements = reading.get("measurements")
        if not isinstance(measurements, list) or not 1 <= len(measurements) <= 3:
            raise ValueError("人工记录中没有数值。")
        seen = set()
        for item in measurements:
            if not isinstance(item, dict):
                raise ValueError('人工输入数值格式无效。')
            quantity = item.get("quantity")
            units = MANUAL_UNITS
            if quantity not in units or item.get("unit") not in units[quantity] or quantity in seen:
                raise ValueError("量名或单位无效，或同一量出现多次。")
            seen.add(quantity)
            if not isinstance(item.get("value"), str):
                raise ValueError("人工输入数值必须使用十进制字符串保存。")
            try:
                value = Decimal(item["value"])
            except (KeyError, InvalidOperation, TypeError, ValueError) as error:
                raise ValueError("人工输入数值无效。") from error
            if not value.is_finite():
                raise ValueError("人工输入不是有限数值。")
        return
    value = reading.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("读数缺少有效数值。")
    if not math.isfinite(value):
        raise ValueError("读数不是有限数值。")
    if not reading.get("unit"):
        raise ValueError("读数缺少单位。")


def write_json_atomically(path, document):
    """同目录临时文件写完后改名；失败时不保留半份正式文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".json.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8") as file:
            json.dump(document, file, ensure_ascii=False, indent=2, allow_nan=False)
        temporary_path.replace(path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def save_record(reading):
    """统一写入入口：先检查，再写文件，完成后才报告成功。"""
    validate_reading(reading)
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    record_id = uuid4().hex
    record = {
        **reading,
        "schema_version": 2,
        "record_id": record_id,
        "saved_at": now_iso(),
        "status": "active",
    }
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = RECORD_DIR / f"record_{stamp}_{record_id}.json"
    write_json_atomically(path, record)
    if _RECORD_OBSERVER is not None:
        try:
            _RECORD_OBSERVER(record, path)
        except Exception:
            pass
    return path


def get_last_record():
    """从文件查询，因此重启程序后仍能找到上一条记录。"""
    paths = sorted(RECORD_DIR.glob("record_*.json"))
    if not paths:
        return None
    path = paths[-1]
    return path, read_record(path)


def read_record(path):
    record = json.loads(path.read_text(encoding="utf-8"))
    record.setdefault("status", "active")  # 兼容旧版 JSON。
    record_id = record["record_id"]
    if not re.fullmatch(r"[0-9a-f]{32}", record_id):
        raise ValueError("记录编号格式无效。")
    events = []
    for event_path in (RECORD_DIR / "annotations").glob(f"event_*_{record_id}_*.json"):
        event = json.loads(event_path.read_text(encoding="utf-8"))
        if event.get("record_id") != record_id or event.get("status") not in {"abnormal", "void"}:
            raise ValueError(f"记录批注无效：{event_path.name}")
        events.append(event)
    record["annotations"] = sorted(events, key=lambda event: event["created_at"])
    if events:
        # 作废状态不会被后续异常标记意外恢复。
        record["status"] = "void" if any(e["status"] == "void" for e in events) else "abnormal"
    return record


def find_record(record_id):
    if not re.fullmatch(r"[0-9a-f]{32}", record_id):
        raise ValueError("记录编号格式无效。")
    paths = list(RECORD_DIR.glob(f"record_*_{record_id}.json"))
    if len(paths) != 1:
        raise ValueError("找不到指定记录，或记录编号重复。")
    return paths[0], read_record(paths[0])


def annotate_record(record_id, status, original_request, input_context=None):
    """追加审计批注；不修改或删除原始实验记录。"""
    if status not in {"abnormal", "void"}:
        raise ValueError("不支持的记录状态。")
    _, record = find_record(record_id)
    if record["status"] == "void":
        raise ValueError("该记录已作废；原始数据仍保留。")
    event = {
        "event_id": uuid4().hex, "record_id": record_id,
        "created_at": now_iso(), "status": status,
        "previous_status": record["status"], "reason": "用户反馈",
        "original_request": original_request,
        "input_context": input_context,
    }
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = RECORD_DIR / "annotations" / f"event_{stamp}_{record_id}_{event['event_id']}.json"
    write_json_atomically(path, event)
    return path


def acquire(command_id, simulate_failure=False, batch_id=None, sequence=None, input_context=None):
    """每次请求一个新读数。返回 (reading, saved_path)，失败则抛出异常。"""
    if command_id not in {"read", "record"}:
        raise ValueError(f"不支持的命令：{command_id}")
    reading = get_reading(uuid4().hex, simulate_failure)
    validate_reading(reading)
    if batch_id is not None:
        reading = {**reading, "batch_id": batch_id, "batch_index": sequence}
    if input_context is not None:
        reading = {**reading, "trigger": input_context}
    path = save_record(reading) if command_id == "record" else None
    return reading, path


def execute_command(command_id, simulate_failure=False):
    """后续语音模块输出 read/record 后，同样调用这里。"""
    print("[状态] 执行中")
    try:
        reading, path = acquire(command_id, simulate_failure)
        print(f"[模拟读数] {reading['value']:.2f} {reading['unit']}")
        if command_id == "record":
            print(f"[成功] 记录已保存：{path}")
        elif command_id == "read":
            print("[成功] 已读取模拟数据；未保存记录。")
        else:
            raise ValueError(f"不支持的命令：{command_id}")
        return True
    except (ValueError, TypeError, OSError) as error:
        print(f"[失败] {error}")
        return False
    finally:
        print("[状态] 待命")


def show_help():
    print("\nread   ：读取模拟数据，不保存")
    print("record ：重新读取模拟数据，并保存一条记录")
    print("last   ：查看最近保存的记录")
    print("fail   ：开发调试专用，让下一次采集失败；不是标记上一条异常")
    print("help   ：显示命令说明")
    print("exit   ：退出程序\n")


def main():
    print("LabMate B：应用流程测试")
    print("当前数据来源为 mock（模拟），尚未接入真实仪表或语音识别。")
    show_help()
    print("[状态] 待命")
    fail_next = False

    while True:
        try:
            command = input("LabMate> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n程序已退出。")
            return

        if command == "exit":
            print("程序已退出。")
            return
        elif command == "help":
            show_help()
        elif command == "fail":
            fail_next = True
            print("下一次 read 或 record 将返回无效读数。")
        elif command in ("read", "record"):
            simulate_failure = fail_next
            fail_next = False
            execute_command(command, simulate_failure)
        elif command == "last":
            try:
                result = get_last_record()
                if result is None:
                    print("尚无已保存记录。")
                else:
                    path, record = result
                    print(f"[最近记录] {path}")
                    print(json.dumps(record, ensure_ascii=False, indent=2))
            except (OSError, ValueError) as error:
                print(f"[查询失败] {error}")
        elif command:
            print("未知命令，请输入 help 查看说明。")


if __name__ == "__main__":
    main()
