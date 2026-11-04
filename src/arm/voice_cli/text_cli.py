r"""LabMate：先用文字验证操作逻辑，再接中文语音转文字。

运行：.\.venv\Scripts\python.exe text_cli.py
只使用标准库，放在新版 main.py 旁边。此文件不录音、不合成语音。
支持范围：电压/电流口述数值、读数/记录、次数/间隔、查询、异常/作废。
这是受限领域的规则解析器；不声称理解任意自然语言，无法完整解析就拒绝执行。
默认连续采集的启动间隔为一秒；采集超过间隔时按实际耗时，不补赶任务。
批次执行时用 Ctrl+C 中止并保留已完成记录；当前不会并行监听停止口令。
人工数值按十进制字符串保存，保留小数位；来源区分 manual_text/manual_voice。
asr_cli.py 可复用本模块并传入录音和识别信息；语音连续记录先核对次数。
"""

from decimal import Decimal, InvalidOperation
import json
import re
import time
import unicodedata
from uuid import uuid4

import main as core


DIGITS = {char: str(number) for number, char in enumerate("零一二三四五六七八九")}
DIGITS.update({"〇": "0", "○": "0", "两": "2"})
NUM = r"[+\-负正]?[0-9零〇○一二两三四五六七八九十百千]+(?:[.点][0-9零〇○一二两三四五六七八九]+)?"
UNIT = r"毫伏特|毫安培|毫伏|毫安|伏特|安培|mV|mA|V|A|伏|安|v|a"
UNITS = {"毫伏特": "mV", "毫伏": "mV", "mV": "mV", "伏特": "V", "伏": "V", "V": "V", "v": "V",
         "毫安培": "mA", "毫安": "mA", "mA": "mA", "安培": "A", "安": "A", "A": "A", "a": "A"}
QUANTITIES = {"电压": "voltage", "电流": "current"}
NAMES = {value: key for key, value in QUANTITIES.items()}
MAX_BATCH_COUNT = 100
MAX_INTERVAL_SECONDS = 60


def decimal_text(token):
    """将三点二六、3点26、负一点二、十二转为精确保留小数位的十进制文本。"""
    if not re.fullmatch(NUM, token):
        raise ValueError("数值格式不完整。")
    negative = token.startswith(("负", "-"))
    token = token.lstrip("+-负正")
    pieces = re.split(r"[.点]", token)
    if not token or len(pieces) > 2:
        raise ValueError("数值格式不完整。")
    integer = pieces[0]
    if any(char in "十百千" for char in integer):
        total, pending, last_unit, zero_since_unit = 0, None, 10000, False
        for index, char in enumerate(integer):
            if char in "十百千":
                unit = {"十": 10, "百": 100, "千": 1000}[char]
                if unit >= last_unit:
                    raise ValueError("中文整数单位顺序无效。")
                if pending is None:
                    if index == 0 and char == "十":
                        pending = 1
                    else:
                        raise ValueError("中文整数缺少数字。")
                if pending == 0:
                    raise ValueError("中文整数格式无效。")
                total += pending * unit
                last_unit, pending, zero_since_unit = unit, None, False
            else:
                digit = int(DIGITS.get(char, char))
                if pending not in (None, 0):
                    raise ValueError("中文整数格式有歧义，请用阿拉伯数字。")
                pending = digit
                if digit == 0:
                    zero_since_unit = True
        if pending and last_unit > 10 and not zero_since_unit:
            raise ValueError("一百二等说法有歧义，请说一百二十或一百零二。")
        result = str(total + (pending or 0))
    else:
        result = "".join(DIGITS.get(char, char) for char in integer)
    if len(pieces) == 2:
        fraction = "".join(DIGITS.get(char, char) for char in pieces[1])
        if not fraction.isascii() or not fraction.isdigit():
            raise ValueError("小数部分应逐位说出。")
        result += "." + fraction
    try:
        value = Decimal(("-" if negative else "") + result)
    except InvalidOperation as error:
        raise ValueError("数字无法解析。") from error
    if not value.is_finite():
        raise ValueError("数字必须是有限数。")
    return format(value, "f")


def batch_parameters(count, interval="1"):
    count_value = Decimal(decimal_text(count))
    interval_value = Decimal(decimal_text(interval))
    if count_value != count_value.to_integral_value() or not 1 <= count_value <= MAX_BATCH_COUNT:
        raise ValueError(f"记录次数须为 1—{MAX_BATCH_COUNT} 的整数。")
    if not 0 <= interval_value <= MAX_INTERVAL_SECONDS:
        raise ValueError(f"间隔须为 0—{MAX_INTERVAL_SECONDS} 秒。")
    return {"intent": "record_device", "count": int(count_value), "interval": float(interval_value)}


def _parse_manual_items(body, allow_missing_unit):
    unit_pattern = rf"({UNIT})?" if allow_missing_unit else rf"({UNIT})"
    pattern = re.compile(rf"(电压|电流)(?:是|为|等于)?[:：]?({NUM}){unit_pattern}")
    items, position, seen = [], 0, set()
    for match in pattern.finditer(body):
        if not re.fullmatch(r"[，,、；;和及]*", body[position:match.start()]):
            raise ValueError("没有完整理解报数，请用“记录电压3.26V，电流1.14A”。")
        name, number, unit_text = match.groups()
        inferred = not unit_text
        unit = ("V" if name == "电压" else "A") if inferred else UNITS[unit_text]
        if name in seen:
            raise ValueError("同一量出现多个数值，请分别记录或重新说明。")
        if (name == "电压" and unit not in {"V", "mV"}) or (name == "电流" and unit not in {"A", "mA"}):
            raise ValueError(f"{name}与单位{unit}不匹配。")
        seen.add(name)
        items.append({"quantity": QUANTITIES[name], "value": decimal_text(number),
                      "unit": unit, "raw_value": number, "raw_unit": unit_text,
                      "unit_inferred": inferred})
        position = match.end()
    if not items or position != len(body):
        raise ValueError("数值、量名或单位不完整。请明确说电压/电流以及伏/安。")
    inferred_units = [item["quantity"] for item in items if item.get("unit_inferred")]
    return {"intent": "record_manual", "measurements": items,
            "inferred_units": inferred_units}


def parse_manual(body):
    try:
        return _parse_manual_items(body, allow_missing_unit=False)
    except ValueError:
        # Missing units are allowed only for the confirmation flow, never for
        # silent writes. The quantity still has to be explicit.
        return _parse_manual_items(body, allow_missing_unit=True)


def normalize_asr_text(text):
    """Apply only conservative domain corrections before command parsing."""
    text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).strip("。.!！").lower()
    text = re.sub(r"^帮助", "帮我", text)
    text = text.replace("季度", "记录")
    text = text.replace("记住", "记录")
    text = text.replace("更", "共")
    text = text.replace("服", "伏")
    text = re.sub(r"(?<=[0-9零〇○一二两三四五六七八九十百千])按", "安", text)
    return text


def parse_command(original):
    text = normalize_asr_text(original)
    if not text:
        raise ValueError("请输入要执行的操作。")
    if text in {"确认", "确认保存", "确认记录", "确认执行", "确认标记", "确认作废",
                "是", "是的", "对", "对的", "好的", "好", "行", "可以", "可以执行",
                "执行", "没问题", "没错", "确定", "同意", "正确", "yes", "ok", "okay",
                "yep", "yeah", "sure"}:
        return {"intent": "confirm"}
    if text in {"取消", "取消操作", "不保存", "不要保存", "不要记录",
                "不行", "不可以", "不是", "不对", "不要", "错", "错误",
                "重说", "再说一遍", "重新说", "拒绝", "否", "no", "nope",
                "not", "wrong", "cancel"}:
        return {"intent": "cancel"}
    text = re.sub(r"^(?:请|麻烦)?(?:帮我|给我)?", "", text)
    text = re.sub(r"(?:吧|谢谢)$", "", text)
    # 仅转换明确等价的句式，不根据相似发音猜数字或单位。
    match = re.fullmatch(r"把(.+?)(?:记录下来|保存下来|记下来)", text)
    if match:
        text = "记录" + match[1]
    text = re.sub(r"^(记录|保存|记下)一下(?=电压|电流)", r"\1", text)
    aliases = {
        "read": "read", "读取数据": "read", "读一下数据": "read", "读取当前数据": "read",
        "读一下当前数据": "read", "读取仪表数据": "read",
        "last": "last", "查看记录": "last", "查看上一条记录": "last", "查看最近记录": "last",
        "看看上一条记录": "last", "查询上一条记录": "last", "查看上一条数据": "last",
        "查看最近一条记录": "last", "查询最近一条记录": "last",
        "help": "help", "帮助": "help", "显示帮助": "help",
        "exit": "exit", "退出": "exit", "退出程序": "exit",
    }
    if text in aliases:
        return {"intent": aliases[text]}
    if text in {"fail", "模拟失败"}:
        raise ValueError("这是开发调试命令。纠正已保存数据请说“上一条数据有问题”。")
    if text in {"停止记录", "停止", "暂停记录"}:
        return {"intent": "stop"}
    if re.fullmatch(r"(?:上一条|上条|刚才那条)(?:数据|记录)?(?:有?问题|不对|异常|有误|错了|不正确)", text) or text in {
            "标记上一条异常", "标记上一条数据异常", "标记上一条记录异常"}:
        return {"intent": "annotate", "status": "abnormal"}
    if re.fullmatch(r"(?:撤销|作废)(?:上一条|上条|刚才那条)(?:数据|记录)?", text):
        return {"intent": "annotate", "status": "void"}
    if (re.fullmatch(r"(?:调用|打开|用)?(?:摄像头)?(?:拍摄|拍|照|拍照)?(?:一下|一张|张)?(?:波形|屏幕|仪表|当前波形|照片)?", text)
            or re.fullmatch(r"看(?:一下)?(?:波形|屏幕|仪表)", text)):
        return {"intent": "capture_image"}
    if (re.fullmatch(r"(?:保存|存|记录|留下)(?:一下|当前)?波形", text)
            or re.fullmatch(r"把波形(?:保存|存)下来", text)):
        return {"intent": "save_waveform"}
    if re.fullmatch(r"(?:当前)?状态|系统状态|现在状态", text):
        return {"intent": "status"}
    match = re.fullmatch(r"(?:记录|保存|记下)(.*)", text)
    if match and any(name in match[1] for name in QUANTITIES):
        return parse_manual(match[1])
    match = re.fullmatch(rf"每(?:隔)?({NUM})秒(?:记录|采集并记录)(?:一次)?(?:数据)?[,，]?(?:一共|总共|共|连续)(?:记录)?({NUM})次", text)
    if match:
        return batch_parameters(match[2], match[1])
    match = re.fullmatch(rf"(?:连续)?(?:记录|采集并记录|测量并记录)({NUM})次(?:数据|读数)?", text)
    if not match:
        match = re.fullmatch(rf"(?:连续)?(?:记录|采集并记录)(?:数据|读数)({NUM})次", text)
    if match:
        return batch_parameters(match[1])
    if text in {"record", "记录", "记录数据", "记录一下数据", "记录一下当前数据", "记录一下", "保存数据", "记下数据", "记录当前数据", "保存当前数据", "重新记录一次", "重新测量并记录", "重新采集并记录"}:
        return batch_parameters("1")
    if text in {"连续记录", "连续记录数据"}:
        raise ValueError("请说明次数，例如“连续记录三次数据”。")
    raise ValueError("没有完整理解这句话，本次未执行。输入 help 查看支持的表达。")


def describe_record(record):
    if record.get("record_kind") == "manual":
        parts = []
        for item in record["measurements"]:
            unit = item["unit"] + ("（推断）" if item.get("unit_inferred") else "")
            parts.append(f"{NAMES[item['quantity']]} {item['value']} {unit}")
        return "，".join(parts)
    return record.get("raw_text") or f"{record.get('value')} {record.get('unit', '')}"


def show_help():
    print("\n可输入：")
    print("  记录数据                         从模拟仪表获取并保存")
    print("  记录电压：3.26V，电流1.14A         人工报数，核对后保存")
    print("  记录电压三点二六伏，电流一点一四安   也支持中文数字")
    print("  帮我连续记录三次数据               默认启动间隔一秒")
    print("  每隔两秒记录一次，共三次            分别重新采集")
    print("  上一条数据有问题 / 撤销上一条记录    核对后标记，保留原始数据")
    print("  拍一下波形 / 调用摄像头拍摄波形     生成视觉采集请求")
    print("  保存波形                           生成波形保存请求")
    print("  当前状态                           查看应用状态")
    print("  确认 / 取消                        处理待核对操作")
    print("  读取数据 / 查看记录 / 帮助 / 退出程序")
    print("批次执行时按 Ctrl+C 中止；当前是文字测试，不监听语音。\n")


class TextApplication:
    def __init__(self, confirm_batches=False):
        self.pending = None
        self.last_acquisition_unsaved = False
        self.confirm_batches = confirm_batches
        self.action_handler = None

    def set_action_handler(self, handler):
        self.action_handler = handler

    def handle_text(self, original, input_context=None):
        command = parse_command(original)
        intent = command["intent"]
        pre_confirmed = bool(input_context and input_context.get("pre_confirmed"))
        if intent == "exit":
            self.pending = None
            print("已退出；未确认的操作不保存。")
            return True
        if intent == "cancel":
            print("已取消待确认操作。" if self.pending else "当前没有待确认操作。")
            self.pending = None
            return False
        if intent == "help":
            show_help()
            return False
        if intent == "confirm":
            self.confirm()
            return False
        if self.pending:
            print("有待确认操作，请先输入“确认”或“取消”；本次新指令未执行。")
            return False
        if intent in {"capture_image", "save_waveform"}:
            if self.action_handler is None:
                print("[动作未接入] 当前没有配置摄像头或波形保存接口。")
            else:
                self.action_handler(intent, command, input_context)
            return False
        if intent == "status":
            print(f"[状态] 待确认操作：{'有' if self.pending else '无'}；"
                  f"最近采集未保存：{'是' if self.last_acquisition_unsaved else '否'}")
            return False
        if intent == "record_manual":
            self.pending = {**command, "original_text": original, "input_at": core.now_iso(),
                            "input_context": input_context}
            print("[待核对] " + describe_record({"record_kind": "manual", **command}))
            if command.get("inferred_units"):
                print("[注意] 有测量值缺少语音单位，程序已按量名推断；确认前请核对显示的单位。")
            source_label = "人工语音报数" if input_context and input_context.get("source") == "voice" else "人工文字输入"
            print(f"来源：{source_label}。核对数字与单位，确认后保存，或取消。")
            if pre_confirmed:
                self.confirm()
        elif intent == "record_device":
            if self.confirm_batches and command["count"] > 1 and not pre_confirmed:
                self.pending = {**command, "input_context": input_context}
                print(f"[待核对] 采集并记录 {command['count']} 次，间隔 {command['interval']:g} 秒。")
                print("确认后开始；说错或听错请取消。")
            else:
                self.record_batch(command["count"], command["interval"], input_context)
        elif intent == "read":
            self.last_acquisition_unsaved = True
            reading, _ = core.acquire("read")
            print(f"[模拟读数] {describe_record(reading)}；未保存。")
        elif intent == "last":
            result = core.get_last_record()
            if result is None:
                print("尚无已保存记录。")
            else:
                path, record = result
                print(f"[最近记录] {path}")
                print(json.dumps(record, ensure_ascii=False, indent=2))
                self.last_acquisition_unsaved = False
        elif intent == "annotate":
            if self.last_acquisition_unsaved:
                print("最近一次采集没有保存，不能标记。若要处理更早记录，请先输入“查看记录”。")
                return False
            result = core.get_last_record()
            if result is None:
                print("尚无已保存记录，不能标记。")
                return False
            _, record = result
            if record["status"] == "void":
                print("最近记录已作废，原始数据保留。")
                return False
            self.pending = {**command, "record_id": record["record_id"], "original_text": original,
                            "input_context": input_context}
            action = "标记异常" if command["status"] == "abnormal" else "作废"
            print(f"[待核对] 将{action}：{describe_record(record)}")
            print(f"保存时间：{record['saved_at']}；编号：{record['record_id']}")
            print("输入“确认”后生效，或输入“取消”。原始数据保留。")
            if pre_confirmed:
                self.confirm()
        elif intent == "stop":
            print("当前没有执行中的批次。批次执行时请按 Ctrl+C 中止。")
        return False

    def confirm(self):
        if self.pending is None:
            print("没有待确认操作。")
            return
        pending = self.pending
        if pending["intent"] == "record_manual":
            context = pending.get("input_context") or {}
            is_voice = context.get("source") == "voice"
            reading = {
                "record_kind": "manual", "request_id": uuid4().hex,
                "device_id": None, "source": "manual_voice" if is_voice else "manual_text", "is_simulated": False,
                "measurements": pending["measurements"], "valid": True,
                "original_text": pending["original_text"], "input_at": pending["input_at"],
                "captured_at": None, "confirmed_at": core.now_iso(),
                "audio_path": context.get("audio_path"), "image_path": None, "error_code": None,
                "input_context": context or None,
            }
            path = core.save_record(reading)
            self.pending = None  # 已写入即清除，避免重复确认写入两次。
            self.last_acquisition_unsaved = False
            print(f"[人工记录已保存] {describe_record(reading)}\n{path}")
        elif pending["intent"] == "record_device":
            self.pending = None  # 部分执行或中止后，不允许再次确认而重复整个批次。
            self.record_batch(pending["count"], pending["interval"], pending.get("input_context"))
        else:
            # 确认的是预览时的具体编号，不重新选取“最近记录”。
            path = core.annotate_record(pending["record_id"], pending["status"], pending["original_text"], pending.get("input_context"))
            self.pending = None
            print(f"[已标记] {pending['status']}；原始数据保留。\n{path}")

    def record_batch(self, count, interval, input_context=None):
        batch_id = uuid4().hex
        attempted = succeeded = failed = 0
        print(f"将从模拟仪表采集 {count} 次；每次单独保存，启动间隔 {interval:g} 秒。")
        print("按 Ctrl+C 可中止，已保存的数据会保留。")
        try:
            for index in range(1, count + 1):
                started = time.monotonic()
                attempted += 1
                self.last_acquisition_unsaved = True
                try:
                    reading, path = core.acquire("record", batch_id=batch_id, sequence=index, input_context=input_context)
                    succeeded += 1
                    self.last_acquisition_unsaved = False
                    print(f"[{index}/{count}] 已保存 {describe_record(reading)}：{path.name}")
                except (ValueError, TypeError, OSError) as error:
                    failed += 1
                    print(f"[{index}/{count}] 失败，未保存：{error}")
                if index < count:
                    time.sleep(max(0, interval - (time.monotonic() - started)))
        except KeyboardInterrupt:
            print("\n批次已中止。")
        interrupted = attempted - succeeded - failed
        print(f"[批次结果] 请求 {count} 次，尝试 {attempted} 次，保存 {succeeded} 条，失败 {failed} 次。")
        if interrupted:
            print("中断发生于采集或写入期间，请用“查看记录”核对最后一条文件。")
        return {"requested": count, "attempted": attempted, "saved": succeeded, "failed": failed,
                "interrupted": interrupted, "batch_id": batch_id}


def main():
    print("LabMate：中文句子流程测试（键盘输入）")
    print("仪表采集仍为 mock；人工报数单独标注来源。尚未接入语音转文字或扬声器。")
    show_help()
    app = TextApplication()
    while True:
        try:
            sentence = input("LabMate> ")
            if app.handle_text(sentence):
                return
        except (EOFError, KeyboardInterrupt):
            print("\n已退出；未确认操作不保存。")
            return
        except (ValueError, TypeError, OSError, KeyError) as error:
            print(f"[未完成] {error}")


if __name__ == "__main__":
    main()
