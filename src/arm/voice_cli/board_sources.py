"""Reading sources that can be plugged into main.set_reading_source()."""

from datetime import datetime
import json
from pathlib import Path


class ReadingError(RuntimeError):
    pass


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class MockSource:
    def read(self, request_id, simulate_failure=False):
        return {
            "request_id": request_id,
            "device_id": "mock_meter_01",
            "source": "mock",
            "source_type": "mock",
            "source_role": "primary",
            "is_simulated": True,
            "value": None if simulate_failure else 3.30,
            "raw_text": None if simulate_failure else "3.30 V",
            "unit": "V",
            "valid": not simulate_failure,
            "captured_at": now_iso(),
            "image_path": None,
            "error_code": "MOCK_READ_FAILED" if simulate_failure else None,
        }


class JsonFileSource:
    """Read a C-provided reading file.

    The file may contain one JSON object. Missing source metadata is filled in
    without changing the measured value or unit.
    """

    def __init__(self, path, default_source="vision"):
        self.path = Path(path)
        self.default_source = default_source

    def read(self, request_id, simulate_failure=False):
        if simulate_failure:
            raise ReadingError("模拟失败：没有提供新读数。")
        if not self.path.is_file():
            raise ReadingError("读数文件不存在：%s" % self.path)
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ReadingError("读数文件无效：%s" % error)
        if not isinstance(document, dict):
            raise ReadingError("读数文件必须是 JSON 对象。")
        reading = dict(document)
        reading.setdefault("request_id", request_id)
        reading.setdefault("source", self.default_source)
        reading.setdefault("source_type", self.default_source)
        reading.setdefault("source_role", "primary")
        reading.setdefault("captured_at", now_iso())
        reading.setdefault("valid", True)
        reading.setdefault("is_simulated", False)
        reading.setdefault("image_path", None)
        reading.setdefault("error_code", None)
        self._add_source_consistency(reading)
        return reading

    @staticmethod
    def _number(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _add_source_consistency(reading):
        sources = reading.get("sources")
        if not isinstance(sources, list) or len(sources) < 2:
            return
        valid_sources = []
        for item in sources:
            if not isinstance(item, dict) or item.get("valid") is False:
                continue
            value = JsonFileSource._number(item.get("value"))
            if value is None:
                continue
            valid_sources.append((item, value))
        if len(valid_sources) < 2:
            return
        primary = next((pair for pair in valid_sources if pair[0].get("source_role") == "primary"), valid_sources[0])
        secondary = next((pair for pair in valid_sources if pair is not primary), None)
        if secondary is None:
            return
        primary_item, primary_value = primary
        secondary_item, secondary_value = secondary
        primary_unit = primary_item.get("unit")
        secondary_unit = secondary_item.get("unit")
        if not primary_unit or primary_unit != secondary_unit:
            reading["source_consistency"] = {
                "status": "invalid",
                "reason": "source units are missing or different",
                "primary_unit": primary_unit,
                "secondary_unit": secondary_unit,
            }
            return
        difference = abs(primary_value - secondary_value)
        tolerance = reading.get("crosscheck_tolerance", reading.get("source_tolerance", 0.02))
        try:
            tolerance = abs(float(tolerance))
        except (TypeError, ValueError):
            tolerance = 0.02
        status = "matched" if difference <= tolerance else "conflict"
        reading["source_consistency"] = {
            "status": status,
            "difference": difference,
            "tolerance": tolerance,
            "primary_source": primary_item.get("source_type"),
            "secondary_source": secondary_item.get("source_type"),
        }
        if status == "conflict":
            reading["source_consistency"]["message"] = "接口读数与视觉读数差值过大"


class ScpiSource:
    def read(self, request_id, simulate_failure=False):
        raise ReadingError("SCPI 适配器尚未接入；请提供仪器通信实现。")


def create_source(name, path=None):
    name = (name or "mock").lower()
    if name == "mock":
        return MockSource()
    if name == "json":
        if not path:
            raise ReadingError("json 数据源需要 --reading-json 路径。")
        return JsonFileSource(path)
    if name == "scpi":
        return ScpiSource()
    raise ReadingError("不支持的数据源：%s" % name)
