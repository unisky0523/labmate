"""Read one request. Supports Python 3.7+ and does not import OCR libraries."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import sys
import uuid

from .transport import InstrumentError, SimulatedTransport, VisaTransport, list_resources


CN_TZ = timezone(timedelta(hours=8))
NUMBER = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([A-Za-z%\u00b0\u03a9\u00b5\u03bc]*)\s*$")


def now():
    return datetime.now(CN_TZ).isoformat(timespec="milliseconds")


def load_config(path):
    try:
        with Path(path).open(encoding="utf-8-sig") as stream:
            config = json.load(stream)
    except (OSError, ValueError) as exc:
        raise InstrumentError("CONFIG_INVALID", str(exc)) from exc
    if not isinstance(config, dict):
        raise InstrumentError("CONFIG_INVALID", "Config must be a JSON object")
    return config


def validate_config(config, simulate=False):
    if config.get("demo_only") and not simulate:
        raise InstrumentError("CONFIG_DEMO_ONLY", "Use a real device config, not the simulation fixture")
    if not simulate and not config.get("expected_idn_pattern"):
        raise InstrumentError("CONFIG_INVALID", "Configure expected_idn_pattern from the real *IDN? reply")
    try:
        re.compile(config.get("expected_idn_pattern", ".+"))
    except (re.error, TypeError) as exc:
        raise InstrumentError("CONFIG_INVALID", "Invalid identity pattern") from exc
    rows = config.get("measurements")
    if not isinstance(rows, list) or not rows:
        raise InstrumentError("CONFIG_INVALID", "Configure at least one measurement")
    ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise InstrumentError("CONFIG_INVALID", "Measurement must be an object")
        for key in ("id", "label", "query", "unit"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise InstrumentError("CONFIG_INVALID", "Each measurement needs id, label, query and unit")
        if row["id"] in ids:
            raise InstrumentError("CONFIG_INVALID", "Duplicate measurement id")
        ids.add(row["id"])
        if not re.fullmatch(r"[^;\r\n?]+\?(?:[ \t]+[^;\r\n?]+)?", row["query"].strip()):
            raise InstrumentError("CONFIG_INVALID", "Use a single documented measurement query")
        for key in ("min_value", "max_value", "invalid_abs_ge"):
            if key in row and (isinstance(row[key], bool) or not isinstance(row[key], (int, float))
                               or not math.isfinite(row[key])):
                raise InstrumentError("CONFIG_INVALID", "Measurement limits must be finite numbers")
        if row.get("invalid_abs_ge", 9e37) <= 0:
            raise InstrumentError("CONFIG_INVALID", "invalid_abs_ge must be positive")
        if "min_value" in row and "max_value" in row and row["min_value"] > row["max_value"]:
            raise InstrumentError("CONFIG_INVALID", "min_value must not exceed max_value")


def parse_value(raw, spec):
    """Require a complete scalar reply; do not extract a number from arbitrary text."""
    match = NUMBER.fullmatch(raw)
    if not match:
        raise InstrumentError("VALUE_PARSE_FAILED", "Expected one numeric value, optionally followed by its unit")
    value = float(match.group(1))
    unit = spec["unit"]
    if match.group(2) and match.group(2) != unit:
        raise InstrumentError("UNIT_MISMATCH", "Reply unit differs from the configured unit")
    if not math.isfinite(value) or abs(value) >= spec.get("invalid_abs_ge", 9e37):
        raise InstrumentError("VALUE_INVALID", "Non-finite value or instrument invalid-value sentinel")
    if "min_value" in spec and value < spec["min_value"]:
        raise InstrumentError("VALUE_OUT_OF_RANGE", "Value is below the configured limit")
    if "max_value" in spec and value > spec["max_value"]:
        raise InstrumentError("VALUE_OUT_OF_RANGE", "Value is above the configured limit")
    return value, unit


def acquire(config, transport, request_id=None, simulated=False):
    validate_config(config, simulate=simulated)
    payload = {
        "request_id": request_id or str(uuid.uuid4()),
        "device_id": config.get("device_id", ""),
        "source": "simulated_scpi" if simulated else "scpi",
        "transport": "simulation" if simulated else "visa",
        "simulated": simulated,
        "value": None, "unit": "", "valid": False,
        "status": "failed", "captured_at": now(), "image_path": "",
        "error_code": "", "identity": "", "measurements": [],
    }
    try:
        identity = transport.query("*IDN?")
        payload["identity"] = identity
        if not identity.strip() or not re.search(config.get("expected_idn_pattern", ".+"), identity):
            raise InstrumentError("DEVICE_IDENTITY_MISMATCH", "Identity does not match this configuration")
    except InstrumentError as exc:
        payload.update(error_code=exc.code, detail=str(exc), completed_at=now())
        return payload

    io_failed = False
    for spec in config["measurements"]:
        row = {
            "measurement_id": spec["id"], "label": spec["label"],
            "channel": spec.get("channel", ""), "label_source": "config",
            "query": spec["query"], "value": None, "unit": spec["unit"],
            "unit_source": "config", "valid": False, "error_code": "",
            "raw_text": "", "captured_at": now(),
        }
        if io_failed:
            row["error_code"] = "SKIPPED_AFTER_IO_ERROR"
        else:
            try:
                row["raw_text"] = transport.query(spec["query"])
            except InstrumentError as exc:
                row.update(error_code=exc.code, detail=str(exc))
                io_failed = True
            else:
                try:
                    parser = getattr(transport, "parse_reply", None)
                    row["value"], row["unit"] = (parser(spec["query"], row["raw_text"], spec)
                                                if parser else parse_value(row["raw_text"], spec))
                    row["valid"] = True
                    scalar = NUMBER.fullmatch(row["raw_text"])
                    if parser or (scalar and scalar.group(2)):
                        row["unit_source"] = "response"
                except InstrumentError as exc:
                    row.update(error_code=exc.code, detail=str(exc))
        payload["measurements"].append(row)
    count = sum(row["valid"] for row in payload["measurements"])
    payload["valid_count"] = count
    payload["total_count"] = len(payload["measurements"])
    payload["valid"] = count == payload["total_count"]
    payload["status"] = "complete" if payload["valid"] else "partial" if count else "failed"
    payload["error_code"] = "" if payload["valid"] else "PARTIAL_READ" if count else "NO_VALID_MEASUREMENTS"
    if len(payload["measurements"]) == 1 and count:
        payload["value"] = payload["measurements"][0]["value"]
        payload["unit"] = payload["measurements"][0]["unit"]
    payload["completed_at"] = now()
    return payload


def save_result(payload, output):
    # Keep request IDs out of filesystem paths; B may supply arbitrary strings.
    directory = Path(output) / (datetime.now(CN_TZ).strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "reading.json"
    payload["result_path"] = str(path.resolve())
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return path


def read_instrument(config_path, resource=None, backend="@py", timeout_ms=3000,
                    request_id=None, output=None, simulate=False):
    """B may call this once per request. Does not write B's final experiment log."""
    config = load_config(config_path)
    validate_config(config, simulate)
    if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
        raise InstrumentError("CONFIG_INVALID", "timeout_ms must be a positive integer")
    if not simulate and not resource:
        raise InstrumentError("RESOURCE_REQUIRED", "Select the actual VISA resource")
    transport = (SimulatedTransport(config.get("simulation_responses", {})) if simulate else
                 VisaTransport(resource, backend, timeout_ms,
                               config.get("read_termination", "\n"),
                               config.get("write_termination", "\n")))
    try:
        payload = acquire(config, transport, request_id, simulate)
        payload["resource"] = "simulation" if simulate else resource
    finally:
        transport.close()
    if output is not None:
        save_result(payload, output)
    return payload


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "identify", "read"))
    parser.add_argument("--resource")
    parser.add_argument("--backend", default="@py", help="@py or an installed vendor VISA backend")
    parser.add_argument("--timeout-ms", type=int, default=3000)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path, default=Path("c_instrument/runs"))
    parser.add_argument("--request-id")
    parser.add_argument("--simulate", action="store_true")
    args = parser.parse_args()
    try:
        if args.timeout_ms <= 0:
            raise InstrumentError("CONFIG_INVALID", "timeout-ms must be positive")
        if args.simulate and args.action != "read":
            raise InstrumentError("CONFIG_INVALID", "Simulation is available only for read")
        if args.action == "list":
            result = {"resources": list_resources(args.backend), "simulated": False}
        elif args.action == "identify":
            if not args.resource:
                raise InstrumentError("RESOURCE_REQUIRED", "Pass --resource from list output")
            config = load_config(args.config) if args.config else {}
            connection = VisaTransport(args.resource, args.backend, args.timeout_ms,
                                       config.get("read_termination", "\n"),
                                       config.get("write_termination", "\n"))
            try:
                result = {"resource": args.resource, "identity": connection.query("*IDN?"), "simulated": False}
            finally:
                connection.close()
        else:
            config = args.config or Path(__file__).parent / "configs" / "simulation.json"
            result = read_instrument(config, args.resource, args.backend, args.timeout_ms,
                                     args.request_id, args.out, args.simulate)
    except (InstrumentError, OSError) as exc:
        result = {"request_id": args.request_id or str(uuid.uuid4()), "valid": False,
                  "status": "failed", "source": "simulated_scpi" if args.simulate else "scpi",
                  "simulated": args.simulate, "captured_at": now(),
                  "error_code": getattr(exc, "code", "FILE_IO_FAILED"),
                  "detail": str(exc), "measurements": []}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 2 if result.get("status") in ("partial", "failed") else 0


if __name__ == "__main__":
    sys.exit(main())
