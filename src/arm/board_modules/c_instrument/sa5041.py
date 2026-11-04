"""SUIN SA5041: query its current measurement over the USB serial bridge."""

import argparse
import json
import math
from pathlib import Path
import sys
import uuid

from .reader import now, parse_value, save_result
from .reader import NUMBER
from .transport import InstrumentError, SerialTransport


# Base units identify physical quantities, not the scale of a bare READ? reply.
MODES = (
    ("dc_voltage", "直流电压", "V", ("VOLT", "VOLT:DC", "VOLTAGE", "VOLTAGE:DC")),
    ("ac_voltage", "交流电压", "V", ("VOLT:AC", "VOLTAGE:AC")),
    ("dc_current", "直流电流", "A", ("CURR", "CURR:DC", "CURRENT", "CURRENT:DC")),
    ("ac_current", "交流电流", "A", ("CURR:AC", "CURRENT:AC")),
    ("resistance", "电阻", "Ohm", ("RES", "RESISTANCE")),
    ("capacitance", "电容", "F", ("CAP", "CAPACITANCE")),
    ("frequency", "频率", "Hz", ("FREQ", "FREQUENCY")),
    ("diode", "二极管", "V", ("DIOD", "DIODE")),
    ("continuity", "通断", "Ohm", ("CONT", "CONTINUITY")),
    ("temperature", "温度", "degC", ("TC", "TCOUPLE", "TEMP", "TEMPERATURE")),
)
FUNCTION_MODES = {alias: (name, label, unit)
                  for name, label, unit, aliases in MODES for alias in aliases}

# Only these range-query paths are documented in the supplied SA5041 manual.
RANGE_QUERIES = {
    "dc_voltage": ":SENSe:VOLTage:DC:RANGe?",
    "ac_voltage": ":SENSe:VOLTage:AC:RANGe?",
    "dc_current": ":SENSe:CURRent:DC:RANGe?",
    "ac_current": ":SENSe:CURRent:AC:RANGe?",
    "resistance": ":SENSe:RESistance:RANGe?",
}
PREFIXES = {"": 1.0, "p": 1e-12, "n": 1e-9, "u": 1e-6,
            "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}


def parse_unit_value(raw, base_unit):
    """Return a base-unit value only when the reply explicitly carries a unit."""
    cleaned = strip_reply_padding(raw).replace("\u03a9", "Ohm")
    cleaned = cleaned.replace("\u00b5", "u").replace("\u03bc", "u")
    cleaned = cleaned.replace("\u00b0C", "degC")
    match = NUMBER.fullmatch(cleaned)
    if not match:
        raise InstrumentError("VALUE_PARSE_FAILED", "Expected a numeric reading and optional unit")
    value, _ = parse_value(match.group(1), {"unit": base_unit})
    suffix = match.group(2)
    if not suffix:
        return value, None, None
    prefixes = {"": 1.0} if base_unit == "degC" else PREFIXES
    for prefix, multiplier in prefixes.items():
        if suffix == prefix + base_unit:
            converted = value * multiplier
            if not math.isfinite(converted) or abs(converted) >= 9e37:
                raise InstrumentError("VALUE_INVALID", "Converted value is out of bounds")
            return converted, suffix, multiplier
    raise InstrumentError("UNIT_MISMATCH", "Reply unit does not match the current function")


def inspect_range(raw, base_unit):
    cleaned = strip_reply_padding(raw)
    match = NUMBER.fullmatch(cleaned)
    # This device abbreviates resistance ranges as "2k", omitting Ohm.
    if match and base_unit == "Ohm" and match.group(2) in PREFIXES and match.group(2):
        cleaned += base_unit
    value, explicit_unit, multiplier = parse_unit_value(cleaned, base_unit)
    if value <= 0:
        raise InstrumentError("RANGE_INVALID", "Range reply must be a positive upper limit")
    return {"upper": value, "unit": base_unit,
            "display_unit": explicit_unit, "scale_to_base": multiplier,
            "unit_source": "range_reply" if explicit_unit else "manual_range_parameter_unit"}


def strip_reply_padding(raw):
    # The real CP210x capture includes leading NUL bytes. Only trim outer
    # padding; embedded NULs remain invalid instead of silently joining digits.
    return raw.strip("\x00 \t\r\n")


def normalize_function(raw):
    return strip_reply_padding(raw).strip('"').upper()


def acquire(transport, request_id=None):
    result = {
        "request_id": request_id or str(uuid.uuid4()),
        "device_id": "suin_sa5041", "device_id_source": "configured",
        "source": "scpi", "transport": "serial", "simulated": False,
        "identity_verified": False,
        "value": None, "unit": "", "valid": False, "status": "failed",
        "captured_at": now(), "image_path": "", "error_code": "",
        "measurements": [], "evidence": [],
    }

    def query(command):
        started = now()
        try:
            raw = transport.query(command)
        except InstrumentError as exc:
            result["evidence"].append({"query": command, "requested_at": started,
                                       "received_at": now(), "error_code": exc.code,
                                       "detail": str(exc)})
            raise
        result["evidence"].append({"query": command, "raw_text": raw,
                                   "requested_at": started, "received_at": now()})
        return raw

    try:
        function = normalize_function(query(":FUNCtion?"))
        result["function"] = function
        mode = FUNCTION_MODES.get(function)
        if mode is None:
            raise InstrumentError("FUNCTION_UNKNOWN", "Unrecognized function response: " + function)
        name, label, base_unit = mode
        row = {
            "measurement_id": name, "label": label, "channel": "",
            "label_source": "function_response", "value": None, "unit": "",
            "base_unit": base_unit, "unit_source": "unresolved",
            "unit_scale_verified": False,
            "validation_status": "pending_display_check",
            "valid": False, "error_code": "",
            "raw_text": "", "captured_at": now(),
        }
        result["measurements"].append(row)
        row["raw_text"] = query(":READ?")
        row["captured_at"] = result["evidence"][-1]["received_at"]
        value, display_unit, multiplier = parse_unit_value(row["raw_text"], base_unit)
        row["raw_numeric_value"] = parse_value(
            NUMBER.fullmatch(strip_reply_padding(row["raw_text"])).group(1),
            {"unit": base_unit})[0]
        after = normalize_function(query(":FUNCtion?"))
        if FUNCTION_MODES.get(after) != mode:
            raise InstrumentError("FUNCTION_CHANGED", "Measurement function changed during acquisition")
        if display_unit is None:
            range_query = RANGE_QUERIES.get(name)
            if range_query:
                row["range_query"] = range_query
                try:
                    row["range"] = inspect_range(query(range_query), base_unit)
                except InstrumentError as exc:
                    row["range_error_code"] = exc.code
                    row["range_error_detail"] = str(exc)
            range_before = row.get("range", {})
            if not range_before.get("display_unit"):
                raise InstrumentError(
                    "UNIT_SCALE_UNRESOLVED",
                    "READ? omitted its unit and range query supplied no explicit display scale")
            # Acquire a fresh reading bracketed by range replies. The earlier
            # reading predates the first range query and cannot use its scale.
            row["raw_text"] = query(":READ?")
            row["captured_at"] = result["evidence"][-1]["received_at"]
            value, reading_unit, reading_scale = parse_unit_value(row["raw_text"], base_unit)
            row["raw_numeric_value"] = parse_value(
                NUMBER.fullmatch(strip_reply_padding(row["raw_text"])).group(1),
                {"unit": base_unit})[0]
            range_after = inspect_range(query(range_query), base_unit)
            row["range_after"] = range_after
            final_function = normalize_function(query(":FUNCtion?"))
            if FUNCTION_MODES.get(final_function) != mode:
                raise InstrumentError("FUNCTION_CHANGED", "Function changed during range acquisition")
            if range_before != range_after:
                raise InstrumentError("RANGE_CHANGED", "Range changed during acquisition; retry")
            display_unit = range_before["display_unit"]
            multiplier = range_before["scale_to_base"]
            if reading_unit is not None:
                display_unit, multiplier = reading_unit, reading_scale
            else:
                value *= multiplier
            if not math.isfinite(value) or abs(value) >= 9e37:
                raise InstrumentError("VALUE_INVALID", "Converted value is out of bounds")
            row["unit_source"] = "reading_reply" if reading_unit else "range_reply_display_scale"
            row["validation_status"] = "range_bracket_checked_display_convention"
        row.update(value=value, unit=base_unit, valid=True, display_unit=display_unit,
                   display_value=row["raw_numeric_value"],
                   scale_to_base=multiplier, unit_scale_verified=True)
        if row["unit_source"] == "unresolved":
            row.update(unit_source="reading_reply", validation_status="explicit_unit_reply")
        result["unit_scale_verified"] = row["unit_scale_verified"]
        result.update(value=value, unit=base_unit, valid=True, status="complete")
    except InstrumentError as exc:
        result.update(error_code=exc.code, detail=str(exc))
        for row in result["measurements"]:
            row.update(value=None, valid=False, error_code=exc.code)
    result.setdefault("unit_scale_verified", False)
    result.update(valid_count=sum(row["valid"] for row in result["measurements"]),
                  total_count=len(result["measurements"]), completed_at=now())
    return result


def read_sa5041(port, request_id=None, output=None, timeout_ms=3000):
    """One B request, one connection; caller must serialize access to the port."""
    result = None
    try:
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
            raise InstrumentError("CONFIG_INVALID", "timeout_ms must be a positive integer")
        if port == "cp210x-usb":
            from .cp210x_usb import Cp210xTransport
            connection = Cp210xTransport(timeout_ms)
        else:
            connection = SerialTransport(port, baudrate=9600, timeout_ms=timeout_ms)
        try:
            result = acquire(connection, request_id)
        finally:
            connection.close()
    except InstrumentError as exc:
        result = {"request_id": request_id or str(uuid.uuid4()),
                  "device_id": "suin_sa5041", "source": "scpi", "transport": "serial",
                  "simulated": False, "value": None, "unit": "", "valid": False,
                  "status": "failed", "captured_at": now(), "image_path": "",
                  "error_code": exc.code, "detail": str(exc), "measurements": []}
    result["port"] = port
    if port == "cp210x-usb":
        result["transport"] = "cp210x_usb"
    if output is not None:
        save_result(result, output)
    return result


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="/dev/ttyUSBx, or cp210x-usb without kernel driver")
    parser.add_argument("--request-id")
    parser.add_argument("--timeout-ms", type=int, default=3000)
    parser.add_argument("--out", type=Path, default=Path("c_instrument/runs"))
    args = parser.parse_args()
    result = read_sa5041(args.port, args.request_id, args.out, args.timeout_ms)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
