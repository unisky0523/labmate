"""Read SIGLENT SDS1202X scalar measurements through USBTMC/VISA."""

import argparse
from datetime import datetime
import glob
import json
import os
from pathlib import Path
import re
import sys
import uuid

from .reader import CN_TZ, NUMBER, acquire, now, parse_value, save_result
from .transport import InstrumentError, VisaTransport, resource_manager
from .usbtmc_linux import UsbtmcTransport


PARAMETERS = {
    "PKPK": ("峰峰值", "V"), "AMPL": ("幅值", "V"),
    "MAX": ("最大值", "V"), "MIN": ("最小值", "V"),
    "MEAN": ("平均值", "V"), "RMS": ("有效值", "V"),
    "TOP": ("顶端值", "V"), "BASE": ("底端值", "V"),
    "CMEAN": ("周期平均值", "V"), "CRMS": ("周期有效值", "V"),
    "FREQ": ("频率", "Hz"), "PER": ("周期", "s"),
    "RISE": ("上升时间", "s"), "FALL": ("下降时间", "s"),
    "PWID": ("正脉宽", "s"), "NWID": ("负脉宽", "s"),
}
IDENTITY = r"(?i)^\s*(?:\*IDN\s+)?SIGLENT\s*,\s*SDS1202X(?:-[A-Z]+)?\s*,"
QUERY = re.compile(r"C([12]):PAVA\? ([A-Z]+)")
HEADER = re.compile(r"C([12])\s*:\s*(?:PAVA|PARAMETER_VALUE)\s+([A-Z]+)\s*,\s*(.+)", re.I)


class ParameterTransport:
    def __init__(self, transport):
        self.transport = transport
        self.evidence = []

    def query(self, command):
        entry = {"query": command, "requested_at": now()}
        self.evidence.append(entry)
        try:
            raw = self.transport.query(command)
        except InstrumentError as exc:
            entry.update(error_code=exc.code, detail=str(exc), received_at=now())
            raise
        entry.update(raw_text=raw, received_at=now())
        return raw

    def parse_reply(self, command, raw, spec):
        expected = QUERY.fullmatch(command)
        if not expected:
            raise InstrumentError("CONFIG_INVALID", "Only single PAVA measurement queries are supported")
        header = HEADER.fullmatch(raw.strip())
        if header:
            if (header.group(1), header.group(2).upper()) != expected.groups():
                raise InstrumentError("RESPONSE_MISMATCH", "Reply channel or parameter differs from query")
            scalar = header.group(3)
        else:
            scalar = raw.strip()
        match = NUMBER.fullmatch(scalar)
        if not match:
            raise InstrumentError("VALUE_PARSE_FAILED", "Expected one PAVA value, not a table or status")
        unit = PARAMETERS[expected.group(2)][1]
        # The programming manual uses uppercase S for seconds.
        suffix = match.group(2)
        if unit == "s" and suffix == "S":
            suffix = "s"
        if not suffix:
            raise InstrumentError("UNIT_MISSING", "PAVA reply omitted its documented unit")
        if suffix != unit:
            raise InstrumentError("UNIT_MISMATCH", "PAVA reply has an unexpected unit")
        return parse_value(match.group(1) + suffix, spec)


def config_for(channels, parameters):
    if not channels or any(ch not in (1, 2) for ch in channels):
        raise InstrumentError("CONFIG_INVALID", "SDS1202X channels must be 1 or 2")
    if not parameters or any(p not in PARAMETERS for p in parameters):
        raise InstrumentError("CONFIG_INVALID", "Unknown scalar parameter")
    return {"device_id": "siglent_sds1202x", "expected_idn_pattern": IDENTITY,
            "measurements": [
                {"id": "ch{}_{}".format(ch, p.lower()), "label": PARAMETERS[p][0],
                 "channel": str(ch), "query": "C{}:PAVA? {}".format(ch, p),
                 "unit": PARAMETERS[p][1]}
                for ch in dict.fromkeys(channels) for p in dict.fromkeys(parameters)]}


def usb_resources(backend=None):
    if os.name == "posix" and backend is None:
        return sorted(path for path in glob.glob("/dev/usbtmc[0-9]*")
                      if path[len("/dev/usbtmc"):].isdigit())
    manager = resource_manager(backend)
    try:
        return list(manager.list_resources("USB?*::INSTR"))
    except Exception as exc:
        raise InstrumentError("DISCOVERY_FAILED", str(exc)) from exc
    finally:
        manager.close()


def decode_screen_image(raw):
    """Return the instrument image bytes and their actual file extension."""
    if not isinstance(raw, bytes):
        raise InstrumentError("IMAGE_INVALID", "Screen dump was not binary data")
    if raw.startswith(b"#"):
        if len(raw) < 3 or raw[1:2] not in b"123456789":
            raise InstrumentError("IMAGE_INVALID", "Invalid binary block header")
        width = int(raw[1:2])
        if len(raw) < 2 + width or not raw[2:2 + width].isdigit():
            raise InstrumentError("IMAGE_INVALID", "Invalid binary block length")
        length = int(raw[2:2 + width])
        start = 2 + width
        if length <= 0 or len(raw) < start + length or raw[start + length:].strip(b"\r\n"):
            raise InstrumentError("IMAGE_INVALID", "Incomplete binary image block")
        raw = raw[start:start + length]
    if raw.startswith(b"BM") and len(raw) >= 54:
        length = int.from_bytes(raw[2:6], "little")
        offset = int.from_bytes(raw[10:14], "little")
        if 54 <= length <= len(raw) and 54 <= offset < length and raw[length:] in (b"", b"\n", b"\r\n", b"\x01\x01\n"):
            return raw[:length], "bmp"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        pos = 8
        while pos + 12 <= len(raw):
            length = int.from_bytes(raw[pos:pos + 4], "big")
            end = pos + 12 + length
            if end > len(raw):
                break
            if raw[pos + 4:pos + 8] == b"IEND" and length == 0 and not raw[end:].strip(b"\r\n"):
                return raw[:end], "png"
            pos = end
    if raw.startswith(b"\xff\xd8"):
        end = raw.rfind(b"\xff\xd9") + 2
        if end > 2 and not raw[end:].strip(b"\r\n"):
            return raw[:end], "jpg"
    raise InstrumentError("IMAGE_INVALID", "SCDP reply is not a complete BMP, PNG or JPEG image")


def capture_screen(resource=None, backend=None, timeout_ms=15000, output=Path("c_instrument/runs")):
    """Save the screen shown on the SDS1202X without changing acquisition settings."""
    if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
        raise InstrumentError("CONFIG_INVALID", "timeout_ms must be positive")
    if not resource:
        resources = usb_resources(backend)
        if len(resources) != 1:
            raise InstrumentError("RESOURCE_REQUIRED", "Select one USB VISA resource using --list and --resource; found: " + repr(resources))
        resource = resources[0]
    connection = (UsbtmcTransport(resource, timeout_ms) if resource.startswith("/dev/usbtmc") else
                  VisaTransport(resource, backend, timeout_ms))
    try:
        identity = connection.query("*IDN?")
        if not re.search(IDENTITY, identity):
            raise InstrumentError("DEVICE_IDENTITY_MISMATCH", "Identity does not match SDS1202X")
        image, extension = decode_screen_image(connection.query_raw("SCDP"))
    finally:
        connection.close()
    directory = Path(output) / (datetime.now(CN_TZ).strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / ("screen." + extension)
    path.write_bytes(image)
    return {"device_id": "siglent_sds1202x", "status": "complete", "valid": True,
            "source": "scpi", "transport": "usbtmc" if resource.startswith("/dev/usbtmc") else "visa",
            "simulated": False, "resource": resource,
            "identity": identity, "captured_at": now(), "image_path": str(path.resolve()),
            "image_bytes": len(image)}


def read_scope(resource, channels=(1,), parameters=("PKPK", "FREQ"),
               backend=None, timeout_ms=3000, request_id=None, output=None):
    config = config_for(channels, parameters)
    if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
        raise InstrumentError("CONFIG_INVALID", "timeout_ms must be positive")
    if not resource:
        resources = usb_resources(backend)
        if len(resources) != 1:
            raise InstrumentError("RESOURCE_REQUIRED", "Select one USB VISA resource using --list and --resource; found: " + repr(resources))
        resource = resources[0]
    connection = (UsbtmcTransport(resource, timeout_ms) if resource.startswith("/dev/usbtmc") else
                  VisaTransport(resource, backend, timeout_ms))
    transport = ParameterTransport(connection)
    try:
        result = acquire(config, transport, request_id)
        result.update(resource=resource, transport="usbtmc" if resource.startswith("/dev/usbtmc") else "visa",
                      evidence=transport.evidence,
                      identity_verified=bool(result.get("identity") and
                                             re.search(IDENTITY, result["identity"])))
    finally:
        connection.close()
    if output is not None:
        save_result(result, output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List USB VISA instruments without sending commands")
    parser.add_argument("--screenshot", action="store_true", help="Save the current screen image via SCDP")
    parser.add_argument("--resource", help="USB VISA resource address, or /dev/usbtmcN on Linux")
    parser.add_argument("--backend", help="Use @py for the bundled board USB backend")
    parser.add_argument("--channels", nargs="+", type=int, choices=(1, 2), default=[1])
    parser.add_argument("--measure", nargs="+", choices=sorted(PARAMETERS), default=["PKPK", "FREQ"])
    parser.add_argument("--timeout-ms", type=int)
    parser.add_argument("--request-id")
    parser.add_argument("--out", type=Path, default=Path("c_instrument/runs"))
    args = parser.parse_args()
    try:
        if args.list:
            result = {"resources": usb_resources(args.backend), "simulated": False}
        elif args.screenshot:
            result = capture_screen(args.resource, args.backend,
                                    15000 if args.timeout_ms is None else args.timeout_ms, args.out)
        else:
            result = read_scope(args.resource, args.channels, args.measure, args.backend,
                                3000 if args.timeout_ms is None else args.timeout_ms, args.request_id, args.out)
    except (InstrumentError, OSError) as exc:
        result = {"request_id": args.request_id or str(uuid.uuid4()), "device_id": "siglent_sds1202x",
                  "source": "scpi", "simulated": False, "valid": False, "status": "failed",
                  "captured_at": now(), "error_code": getattr(exc, "code", "FILE_IO_FAILED"),
                  "detail": str(exc), "measurements": []}
        if not args.list:
            save_result(result, args.out)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 2 if result.get("status") in ("partial", "failed") else 0


if __name__ == "__main__":
    sys.exit(main())
