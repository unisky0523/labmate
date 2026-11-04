"""Linux USB Host2 binding and DG4102 control using bundled PyVISA-py."""

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sys

from . import dg4102
from .reader import now, save_result
from .transport import InstrumentError


DEFAULT_CONFIG = Path(__file__).resolve().parent / "board_config" / "dg4102_host2.json"
EXPECTED_SERIAL = "DG4E184950519"


def devices(sysfs=Path("/sys/bus/usb/devices")):
    """Read actual physical USB routes, independent of /dev node numbering."""
    rows = []
    for path in sorted(Path(sysfs).glob("*")):
        if ":" in path.name:
            continue
        try:
            vendor = int((path / "idVendor").read_text().strip(), 16)
            product = int((path / "idProduct").read_text().strip(), 16)
            if (vendor, product) != (0x1AB1, 0x0641):
                continue
            rows.append({"usb_route": path.name, "serial": (path / "serial").read_text().strip(),
                         "vendor_id": vendor, "product_id": product})
        except FileNotFoundError:
            continue
    return rows


def select_device(rows, serial=EXPECTED_SERIAL, route=None):
    matches = [r for r in rows if r["serial"] == serial and (route is None or r["usb_route"] == route)]
    if len(matches) != 1:
        raise InstrumentError("HOST2_DEVICE_NOT_FOUND", "Connect DG4102 {} to the bound HOST2 socket; detected: {}".format(serial, rows))
    return matches[0]


def visa_resource(row, resources):
    matches = []
    for resource in resources:
        parts = resource.split("::")
        if len(parts) < 5 or not parts[0].upper().startswith("USB") or parts[-1].upper() != "INSTR":
            continue
        try:
            ids = tuple(int(p, 16 if p.lower().startswith("0x") else 10) for p in parts[1:3])
        except ValueError:
            continue
        if ids == (0x1AB1, 0x0641) and parts[3] == row["serial"]:
            matches.append(resource)
    if len(matches) != 1:
        raise InstrumentError("RESOURCE_REQUIRED", "Expected one VISA resource for bound DG4102; detected " + repr(resources))
    return matches[0]


def load_binding(path):
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InstrumentError("HOST2_NOT_BOUND", "First connect DG4102 to HOST2 and run --bind-host2: " + str(exc)) from exc
    if (not isinstance(config, dict) or config.get("physical_port") != "HOST2" or
            config.get("serial") != EXPECTED_SERIAL or not isinstance(config.get("usb_route"), str) or
            not config["usb_route"]):
        raise InstrumentError("HOST2_NOT_BOUND", "Invalid HOST2 binding; run --bind-host2 after connecting to HOST2")
    return config


@contextmanager
def device_lock(config_path):
    import fcntl
    path = Path(config_path).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InstrumentError("DEVICE_BUSY", "Another DG4102 request is running; retry after it completes") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def execute_host2(request, config_path=DEFAULT_CONFIG, request_id=None, timeout_ms=3000, output=None):
    """Voice integration entry: one serialized action and a structured result."""
    result = None
    try:
        dg4102.build_plan(request)
        with device_lock(config_path):
            config = load_binding(config_path)
            row = select_device(devices(), config["serial"], config["usb_route"])
            resource = visa_resource(row, dg4102.usb_resources("@py"))
            result = dg4102.execute(request, resource=resource, backend="@py", timeout_ms=timeout_ms)
            result["host2_binding"] = config
        if request_id is not None:
            result["request_id"] = request_id
        if output is not None:
            save_result(result, output)
        return result
    except (InstrumentError, OSError) as exc:
        return {"request_id": request_id, "device_id": "rigol_dg4102", "status": "failed", "valid": False,
                "simulated": False, "request": request, "completed_at": now(),
                "error_code": getattr(exc, "code", "IO_FAILED"), "detail": str(exc),
                "control_result": result}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--bind-host2", action="store_true")
    parser.add_argument("--host2-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--list", action="store_true")
    args, remaining = parser.parse_known_args(argv)
    try:
        if any(arg.split("=", 1)[0] in ("--resource", "--backend") for arg in remaining):
            raise InstrumentError("CONFIG_INVALID", "Board HOST2 entry chooses resource and @py backend automatically")
        rows = devices()
        if args.list:
            if args.bind_host2 or remaining:
                raise InstrumentError("CONFIG_INVALID", "Use --list without a control action")
            print(json.dumps({"devices": rows, "binding_path": str(args.host2_config), "simulated": False}, indent=2))
            return 0
        if args.bind_host2:
            if remaining:
                raise InstrumentError("CONFIG_INVALID", "Run --bind-host2 separately from control actions")
            with device_lock(args.host2_config):
                row = select_device(rows)
                resource = visa_resource(row, dg4102.usb_resources("@py"))
                result = dg4102.execute({"action": "status", "channel": 2}, resource=resource, backend="@py")
                if not result["valid"]:
                    print(json.dumps(result, indent=2))
                    return 2
                config = dict(row, physical_port="HOST2", bound_at=now())
                args.host2_config.parent.mkdir(parents=True, exist_ok=True)
                temporary = args.host2_config.with_suffix(".tmp")
                temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
                temporary.replace(args.host2_config)
            result.update(host2_binding=config, binding_path=str(args.host2_config))
            print(json.dumps(result, indent=2))
            return 0
        # Help and disconnected dry runs do not require a binding.
        if "--help" in remaining or "-h" in remaining or "--dry-run" in remaining:
            return dg4102.main(remaining)
        with device_lock(args.host2_config):
            config = load_binding(args.host2_config)
            row = select_device(rows, config["serial"], config["usb_route"])
            resource = visa_resource(row, dg4102.usb_resources("@py"))
            return dg4102.main(["--backend", "@py", "--resource", resource] + remaining)
    except (InstrumentError, OSError) as exc:
        print(json.dumps({"status": "failed", "valid": False, "simulated": False,
                          "error_code": getattr(exc, "code", "IO_FAILED"), "detail": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
