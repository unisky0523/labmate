"""RIGOL DG4102 SCPI control core. Configuration leaves the selected output OFF."""

import argparse
import json
import math
from pathlib import Path
import re
import sys
import time
import uuid

from .reader import now, save_result
from .transport import InstrumentError, VisaTransport, resource_manager


class DGTransport(VisaTransport):
    """DG4000 can leave empty LF records between actual responses."""

    def __init__(self, resource, backend=None, timeout_ms=3000):
        super().__init__(resource, backend, timeout_ms)
        self.timeout_ms = timeout_ms
        try:
            self.device.clear()
        except Exception as exc:
            # PyVISA-py 0.6.3 has no USBTMC clear implementation. Its exact
            # unsupported-operation reply is acceptable; real USB errors are not.
            if getattr(exc, "error_code", None) != -1073807257:
                self.close()
                raise InstrumentError("DEVICE_CLEAR_FAILED", str(exc)) from exc

    def write(self, command):
        try:
            self.device.write(command)
        except Exception as exc:
            raise InstrumentError("WRITE_FAILED", str(exc)) from exc

    def query(self, command):
        deadline = time.monotonic() + self.timeout_ms / 1000.0
        try:
            self.write(command)
            time.sleep(0.08)
            while time.monotonic() < deadline:
                self.device.timeout = max(1, int((deadline - time.monotonic()) * 1000))
                reply = self.device.read().strip()
                if reply:
                    return reply
            raise InstrumentError("QUERY_TIMEOUT", "Only empty records received for " + command)
        except InstrumentError:
            raise
        except Exception as exc:
            code = "QUERY_TIMEOUT" if getattr(exc, "error_code", None) == -1073807339 else "QUERY_FAILED"
            raise InstrumentError(code, str(exc)) from exc
        finally:
            self.device.timeout = self.timeout_ms


def usb_resources(backend=None):
    manager = resource_manager(backend)
    try:
        return list(manager.list_resources("USB?*::INSTR"))
    finally:
        manager.close()


def numeric(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise InstrumentError("CONFIG_INVALID", "{} must be finite, in [{}, {}]".format(name, low, high))
    return float(value)


def build_plan(request):
    """Allowlisted action contract for a future board/voice caller; no raw SCPI."""
    if not isinstance(request, dict):
        raise InstrumentError("CONFIG_INVALID", "Request must be an object")
    action = request.get("action", "status")
    channel = request.get("channel", 1)
    if type(channel) is not int or channel not in (1, 2):
        raise InstrumentError("CONFIG_INVALID", "channel must be 1 or 2")
    allowed = {"status": set(), "output": {"state"}, "stop": set(),
               "trigger": set(), "sine": {"frequency_hz", "amplitude_vpp", "offset_v", "load"},
               "sweep": {"start_hz", "stop_hz", "time_s", "spacing", "trigger", "amplitude_vpp", "offset_v", "load"}}
    if action not in allowed or set(request) - {"action", "channel"} - allowed.get(action, set()):
        raise InstrumentError("CONFIG_INVALID", "Unknown action or unsupported request fields")
    source = ":SOURce{}".format(channel)
    output = ":OUTPut{}".format(channel)
    if action == "status":
        return []
    if action == "output":
        if request.get("state") not in ("on", "off"):
            raise InstrumentError("CONFIG_INVALID", "state must be on or off")
        return [output + ":STATe " + request["state"].upper()]
    if action == "stop":
        return [output + ":STATe OFF", source + ":SWEep:STATe OFF"]
    if action == "trigger":
        return [source + ":SWEep:TRIGger:IMMediate"]
    amp = numeric(request.get("amplitude_vpp"), 0.02, 10, "amplitude_vpp")
    offset = numeric(request.get("offset_v", 0), -5, 5, "offset_v")
    load = request.get("load", "highz")
    if load not in ("highz", "50"):
        raise InstrumentError("CONFIG_INVALID", "load must be highz or 50")
    # This first adapter deliberately exposes a conservative voltage envelope.
    if abs(offset) + amp / 2 > (5 if load == "highz" else 2.5):
        raise InstrumentError("CONFIG_INVALID", "Amplitude plus offset exceeds adapter voltage envelope")
    if action == "sine":
        frequency = numeric(request.get("frequency_hz"), 1e-6, 100e6, "frequency_hz")
    else:
        start = numeric(request.get("start_hz"), 1e-6, 100e6, "start_hz")
        stop = numeric(request.get("stop_hz"), 1e-6, 100e6, "stop_hz")
        seconds = numeric(request.get("time_s"), 0.001, 300, "time_s")
        if start == stop:
            raise InstrumentError("CONFIG_INVALID", "Sweep endpoints must differ")
        if request.get("spacing", "lin") not in ("lin", "log") or request.get("trigger", "int") not in ("int", "man", "ext"):
            raise InstrumentError("CONFIG_INVALID", "Invalid sweep spacing or trigger")
        frequency = max(start, stop)
    if frequency > 10e6 and (amp > 1 or offset != 0):
        raise InstrumentError("CONFIG_INVALID", "Above 10 MHz this adapter permits <=1 Vpp and zero offset")
    commands = [output + ":STATe OFF", source + ":SWEep:STATe OFF",
                source + ":BURSt:STATe OFF", source + ":MOD:STATe OFF",
                source + ":FUNCtion:SHAPe SIN", output + ":LOAD " + ("INFinity" if load == "highz" else "50"),
                source + ":VOLTage:UNIT VPP", source + ":VOLTage:OFFSet 0",
                source + ":VOLTage {}".format(amp), source + ":VOLTage:OFFSet {}".format(offset)]
    if action == "sine":
        commands.append(source + ":FREQuency:FIXed {}".format(frequency))
    else:
        commands += [source + ":FREQuency:STARt {}".format(start), source + ":FREQuency:STOP {}".format(stop),
                     source + ":SWEep:TIME {}".format(seconds), source + ":SWEep:SPACing " + request.get("spacing", "lin").upper(),
                     source + ":SWEep:HTIMe:STARt 0", source + ":SWEep:HTIMe:STOP 0", source + ":SWEep:RTIMe 0",
                     source + ":SWEep:TRIGger:SOURce " + request.get("trigger", "int").upper(),
                     source + ":SWEep:STATe ON"]
    return commands


class Controller:
    def __init__(self, transport, evidence):
        self.transport = transport
        self.evidence = evidence

    def io(self, command, write=False):
        row = {"command": command, "operation": "write" if write else "query", "requested_at": now()}
        self.evidence.append(row)
        try:
            reply = self.transport.write(command) if write else self.transport.query(command)
            if not write:
                row["raw_text"] = reply
            return reply
        except InstrumentError as exc:
            row.update(error_code=exc.code, detail=str(exc))
            raise
        finally:
            row["completed_at"] = now()

    def error(self):
        reply = self.io(":SYSTem:ERRor?")
        match = re.match(r'^\s*([+-]?\d+)\s*,', reply)
        if not match:
            raise InstrumentError("RESPONSE_INVALID", "Invalid error queue reply: " + reply)
        if int(match[1]):
            raise InstrumentError("INSTRUMENT_ERROR", reply)

    def state(self, channel):
        source = ":SOURce{}".format(channel)
        output = ":OUTPut{}".format(channel)
        queries = {"output": output + ":STATe?", "load": output + ":LOAD?",
                   "waveform": source + ":FUNCtion:SHAPe?", "frequency_hz": source + ":FREQuency:FIXed?",
                   "amplitude_unit": source + ":VOLTage:UNIT?", "amplitude": source + ":VOLTage?",
                   "offset_v": source + ":VOLTage:OFFSet?", "sweep": source + ":SWEep:STATe?",
                   "start_hz": source + ":FREQuency:STARt?", "stop_hz": source + ":FREQuency:STOP?",
                   "time_s": source + ":SWEep:TIME?", "spacing": source + ":SWEep:SPACing?",
                   "trigger": source + ":SWEep:TRIGger:SOURce?"}
        result = {}
        for name, query in queries.items():
            reply = self.io(query)
            if name in ("frequency_hz", "amplitude", "offset_v", "start_hz", "stop_hz", "time_s"):
                try:
                    value = float(reply)
                    if not math.isfinite(value):
                        raise ValueError()
                except ValueError as exc:
                    raise InstrumentError("RESPONSE_INVALID", query + " returned " + repr(reply)) from exc
            else:
                value = reply.upper()
                choices = {"output": ("ON", "OFF"), "sweep": ("ON", "OFF"),
                           "amplitude_unit": ("VPP", "VRMS", "DBM"), "spacing": ("LIN", "LOG", "STE"),
                           "trigger": ("INT", "MAN", "EXT")}
                if name in choices and value not in choices[name]:
                    raise InstrumentError("RESPONSE_INVALID", query + " returned " + repr(reply))
            result[name] = value
        return result


def verify(state, request):
    action = request.get("action", "status")
    expected = {}
    if action in ("sine", "sweep"):
        expected.update(output="OFF", waveform="SIN", amplitude_unit="VPP",
                        amplitude=request["amplitude_vpp"], offset_v=request.get("offset_v", 0),
                        load="INFINITY" if request.get("load", "highz") == "highz" else "50")
        if action == "sine":
            expected.update(sweep="OFF", frequency_hz=request["frequency_hz"])
        else:
            expected.update(sweep="ON", start_hz=request["start_hz"], stop_hz=request["stop_hz"],
                            time_s=request["time_s"], spacing=request.get("spacing", "lin").upper(),
                            trigger=request.get("trigger", "int").upper())
    elif action == "output":
        expected["output"] = request["state"].upper()
    elif action == "stop":
        expected.update(output="OFF", sweep="OFF")
    for key, value in expected.items():
        actual = state[key]
        if key == "load" and value == "50":
            try:
                actual = float(actual)
                value = 50.0
            except ValueError:
                pass
        matches = math.isclose(actual, value, rel_tol=1e-6, abs_tol=1e-9) if isinstance(value, (int, float)) and isinstance(actual, (int, float)) else actual == value
        if not matches:
            raise InstrumentError("READBACK_MISMATCH", "{}: requested {}, received {}".format(key, value, actual))


def execute(request, resource=None, backend=None, timeout_ms=3000, dry_run=False, connection=None):
    result = {"request_id": str(uuid.uuid4()), "device_id": "rigol_dg4102", "source": "scpi",
              "simulated": connection is not None, "identity_verified": False, "status": "failed", "valid": False,
              "requested_at": now(), "request": request, "evidence": [], "electrical_output_verified": False}
    owned = connection is None
    try:
        commands = build_plan(request)
        if type(timeout_ms) is not int or timeout_ms <= 0:
            raise InstrumentError("CONFIG_INVALID", "timeout_ms must be positive")
        result["planned_commands"] = commands
        if dry_run:
            result.update(status="planned", valid=True, executed=False)
            return result
        if connection is None:
            if not resource:
                candidates = [r for r in usb_resources(backend) if "::0X1AB1::0X0641::" in r.upper()]
                if len(candidates) != 1:
                    raise InstrumentError("RESOURCE_REQUIRED", "Select the DG4102 using --list and --resource; found " + repr(candidates))
                resource = candidates[0]
            connection = DGTransport(resource, backend, timeout_ms)
        result["resource"] = resource
        controller = Controller(connection, result["evidence"])
        identity = controller.io("*IDN?")
        result["identity"] = identity
        fields = identity.split(",")
        if len(fields) < 4 or "RIGOL" not in fields[0].upper() or fields[1].strip().upper() != "DG4102":
            raise InstrumentError("DEVICE_IDENTITY_MISMATCH", "Expected RIGOL DG4102; received " + identity)
        result["identity_verified"] = True
        if commands:
            controller.error()
            if request["action"] in ("sine", "sweep"):
                coupling = controller.io(":COUPling:STATe?").upper()
                if re.sub(r"\s+", "", coupling) != "FREQ:OFF,PHASE:OFF,AMPL:OFF":
                    raise InstrumentError("COUPLING_ACTIVE", "Disable channel coupling before configuring: " + coupling)
            if request["action"] == "trigger":
                source = ":SOURce{}".format(request.get("channel", 1))
                if controller.io(source + ":SWEep:STATe?") != "ON" or controller.io(source + ":SWEep:TRIGger:SOURce?") != "MAN":
                    raise InstrumentError("TRIGGER_NOT_READY", "Sweep must be ON with MAN trigger source")
            for command in commands:
                controller.io(command, write=True)
                # Check every setting before sending a dependent command.
                time.sleep(0.08)
                controller.error()
        state = controller.state(request.get("channel", 1))
        result["state"] = state
        controller.error()
        verify(state, request)
        result.update(status="complete", valid=True, executed=bool(commands), error_code="")
    except (InstrumentError, OSError) as exc:
        result.update(error_code=getattr(exc, "code", "IO_FAILED"), detail=str(exc))
        if any(row["operation"] == "write" for row in result["evidence"]):
            result["detail"] += "; settings may be partially applied; inspect output state before retrying"
    finally:
        if owned and connection is not None:
            connection.close()
        result["completed_at"] = now()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--resource")
    parser.add_argument("--backend", default=None)
    parser.add_argument("--channel", type=int, choices=(1, 2), default=1)
    parser.add_argument("--timeout-ms", type=int, default=3000)
    parser.add_argument("--out", type=Path, default=Path("c_instrument/runs"))
    parser.add_argument("--dry-run", action="store_true", help="Print plan without connecting or changing settings")
    sub = parser.add_subparsers(dest="action")
    sub.add_parser("status")
    for action in ("sine", "sweep"):
        p = sub.add_parser(action)
        p.add_argument("--amplitude-vpp", type=float, required=True)
        p.add_argument("--offset-v", type=float, default=0)
        p.add_argument("--load", choices=("highz", "50"), default="highz")
        if action == "sine":
            p.add_argument("--frequency-hz", type=float, required=True)
        else:
            p.add_argument("--start-hz", type=float, required=True)
            p.add_argument("--stop-hz", type=float, required=True)
            p.add_argument("--time-s", type=float, required=True)
            p.add_argument("--spacing", choices=("lin", "log"), default="lin")
            p.add_argument("--trigger", choices=("int", "man", "ext"), default="int")
    sub.add_parser("output").add_argument("state", choices=("on", "off"))
    sub.add_parser("stop")
    sub.add_parser("trigger")
    args = parser.parse_args(argv)
    try:
        if args.list:
            result = {"resources": usb_resources(args.backend), "simulated": False}
        else:
            request = {k: v for k, v in vars(args).items() if k not in ("list", "resource", "backend", "timeout_ms", "out", "dry_run")}
            request["action"] = args.action or "status"
            result = execute(request, args.resource, args.backend, args.timeout_ms, args.dry_run)
            save_result(result, args.out)
    except (InstrumentError, OSError) as exc:
        result = {"status": "failed", "valid": False, "error_code": getattr(exc, "code", "IO_FAILED"), "detail": str(exc)}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 2 if result.get("status") == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
