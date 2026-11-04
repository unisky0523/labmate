import unittest
from unittest.mock import Mock, patch

from c_instrument.dg4102 import DGTransport, build_plan, execute
from c_instrument.transport import InstrumentError


SWEEP = {"action": "sweep", "channel": 2, "start_hz": 100, "stop_hz": 10000,
         "time_s": 5, "amplitude_vpp": 1}


class Device:
    def __init__(self):
        self.writes = []
        self.identity = "Rigol Technologies,DG4102,TEST,00.01.13"
        self.error_after = None
        self.coupling = "FREQ:OFF,PHASE:OFF,AMPL:OFF"
        self.mismatch = False

    def write(self, command):
        self.writes.append(command)

    def query(self, command):
        if command == "*IDN?":
            return self.identity
        if command == ":COUPling:STATe?":
            return self.coupling
        if command == ":SYSTem:ERRor?":
            return '-222,"Data out of range"' if self.error_after and len(self.writes) >= self.error_after else '0,"No error"'
        replies = {":OUTPut2:STATe?": "OFF", ":OUTPut2:LOAD?": "INFINITY",
                   ":SOURce2:FUNCtion:SHAPe?": "SIN", ":SOURce2:FREQuency:FIXed?": "1000",
                   ":SOURce2:VOLTage:UNIT?": "VPP", ":SOURce2:VOLTage?": "1",
                   ":SOURce2:VOLTage:OFFSet?": "0", ":SOURce2:SWEep:STATe?": "ON",
                   ":SOURce2:FREQuency:STARt?": "100", ":SOURce2:FREQuency:STOP?": "10000",
                   ":SOURce2:SWEep:TIME?": "4" if self.mismatch else "5",
                   ":SOURce2:SWEep:SPACing?": "LIN", ":SOURce2:SWEep:TRIGger:SOURce?": "INT"}
        return replies[command]


class DG4102Tests(unittest.TestCase):
    def run_device(self, device, request=SWEEP):
        with patch("c_instrument.dg4102.time.sleep"):
            return execute(request, connection=device)

    def test_sweep_verifies_readbacks_and_never_enables_output(self):
        device = Device()
        result = self.run_device(device)
        self.assertTrue(result["valid"])
        self.assertTrue(result["simulated"])
        self.assertFalse(result["electrical_output_verified"])
        self.assertEqual(device.writes[0], ":OUTPut2:STATe OFF")
        self.assertEqual(device.writes[-1], ":SOURce2:SWEep:STATe ON")
        self.assertFalse(any(":OUTPut1" in c or ":SOURce1" in c or ":STATe ON" in c and c.startswith(":OUTPut") for c in device.writes))

    def test_wrong_identity_and_coupling_prevent_writes(self):
        for attribute, value, code in (("identity", "RIGOL,DG4162,S,F", "DEVICE_IDENTITY_MISMATCH"),
                                       ("coupling", "FREQ:ON,PHASE:OFF,AMPL:OFF", "COUPLING_ACTIVE")):
            device = Device()
            setattr(device, attribute, value)
            self.assertEqual(self.run_device(device)["error_code"], code)
            self.assertEqual(device.writes, [])

    def test_command_error_stops_remaining_writes(self):
        device = Device()
        device.error_after = 2
        result = self.run_device(device)
        self.assertEqual(result["error_code"], "INSTRUMENT_ERROR")
        self.assertEqual(len(device.writes), 2)

    def test_readback_mismatch_fails(self):
        device = Device()
        device.mismatch = True
        self.assertEqual(self.run_device(device)["error_code"], "READBACK_MISMATCH")

    def test_invalid_requests_rejected_before_connection(self):
        for changes in ({"start_hz": float("nan")}, {"amplitude_vpp": float("inf")},
                        {"channel": True}, {"channel": 3}, {"stop_hz": 101e6},
                        {"stop_hz": 100}, {"time_s": 0}, {"amplitude_vpp": 10, "offset_v": 1},
                        {"spacing": "lin;*RST"}, {"raw_scpi": "*RST"}):
            with self.subTest(changes=changes), patch("c_instrument.dg4102.DGTransport") as transport:
                result = execute(dict(SWEEP, **changes))
                self.assertEqual(result["error_code"], "CONFIG_INVALID")
                transport.assert_not_called()

    def test_dry_run_does_not_connect(self):
        with patch("c_instrument.dg4102.DGTransport") as transport:
            result = execute(SWEEP, dry_run=True)
            self.assertEqual(result["status"], "planned")
            self.assertFalse(result["identity_verified"])
            transport.assert_not_called()

    def test_status_never_writes_and_timeout_does_not_continue(self):
        device = Device()
        result = self.run_device(device, {"action": "status", "channel": 2})
        self.assertTrue(result["valid"])
        self.assertEqual(device.writes, [])
        device.query = Mock(side_effect=InstrumentError("QUERY_TIMEOUT", "test"))
        result = self.run_device(device)
        self.assertEqual(result["error_code"], "QUERY_TIMEOUT")
        self.assertEqual(device.query.call_count, 1)

    def test_manual_trigger_guard(self):
        result = self.run_device(Device(), {"action": "trigger", "channel": 2})
        self.assertEqual(result["error_code"], "TRIGGER_NOT_READY")

    def test_output_and_stop_contract(self):
        self.assertEqual(build_plan({"action": "output", "state": "on"}), [":OUTPut1:STATe ON"])
        self.assertEqual(build_plan({"action": "stop"}), [":OUTPut1:STATe OFF", ":SOURce1:SWEep:STATe OFF"])

    def test_empty_records_consumed_before_next_command(self):
        transport = DGTransport.__new__(DGTransport)
        transport.device = Mock()
        transport.timeout_ms = 3000
        transport.device.read.side_effect = ["", "\n", "OFF"]
        with patch("c_instrument.dg4102.time.sleep"):
            self.assertEqual(transport.query(":OUTPut2:STATe?"), "OFF")
        transport.device.write.assert_called_once_with(":OUTPut2:STATe?")
        self.assertEqual(transport.device.read.call_count, 3)


if __name__ == "__main__":
    unittest.main()
