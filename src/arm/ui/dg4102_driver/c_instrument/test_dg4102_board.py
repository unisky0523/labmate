from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from c_instrument.dg4102 import DGTransport
from c_instrument.dg4102_board import devices, select_device, visa_resource, load_binding, execute_host2, EXPECTED_SERIAL
from c_instrument.transport import InstrumentError


ROW = {"usb_route": "1-1.2", "serial": EXPECTED_SERIAL, "vendor_id": 0x1AB1, "product_id": 0x0641}
RESOURCE = "USB0::0x1AB1::0x0641::" + EXPECTED_SERIAL + "::INSTR"


class BoardTests(unittest.TestCase):
    def test_sysfs_enumeration_ignores_other_devices(self):
        with tempfile.TemporaryDirectory() as root:
            for name, vendor, product in (("1-1.2", "1ab1", "0641"), ("1-1.3", "f4ec", "ee3a")):
                path = Path(root) / name
                path.mkdir()
                for key, value in (("idVendor", vendor), ("idProduct", product), ("serial", EXPECTED_SERIAL)):
                    (path / key).write_text(value)
            self.assertEqual(devices(root), [ROW])

    def test_binding_uses_physical_route_and_serial_not_device_number(self):
        self.assertEqual(select_device([ROW], route="1-1.2"), ROW)
        for rows in ([], [dict(ROW, usb_route="1-1.3")], [dict(ROW, serial="OTHER")]):
            with self.assertRaises(InstrumentError):
                select_device(rows, route="1-1.2")

    def test_visa_hex_and_decimal_resources(self):
        for resource in (RESOURCE, "USB0::6833::1601::" + EXPECTED_SERIAL + "::0::INSTR"):
            self.assertEqual(visa_resource(ROW, ["USB0::0xF4EC::0xEE3A::SDS::INSTR", resource]), resource)
        with self.assertRaises(InstrumentError):
            visa_resource(ROW, [RESOURCE.replace(EXPECTED_SERIAL, "OTHER")])

    def test_missing_and_invalid_binding(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "binding.json"
            with self.assertRaises(InstrumentError):
                load_binding(path)
            path.write_text(json.dumps(dict(ROW, physical_port="HOST2")))
            self.assertEqual(load_binding(path)["usb_route"], "1-1.2")
            path.write_text("{}")
            with self.assertRaises(InstrumentError):
                load_binding(path)

    def test_voice_call_routes_to_bound_resource_and_preserves_request_id(self):
        config = dict(ROW, physical_port="HOST2")
        request = {"action": "output", "channel": 2, "state": "off"}
        with patch("c_instrument.dg4102_board.device_lock", return_value=nullcontext()), \
                patch("c_instrument.dg4102_board.load_binding", return_value=config), \
                patch("c_instrument.dg4102_board.devices", return_value=[ROW]), \
                patch("c_instrument.dg4102.usb_resources", return_value=[RESOURCE]), \
                patch("c_instrument.dg4102.execute", return_value={"status": "complete", "valid": True}) as execute:
            result = execute_host2(request, request_id="voice-42")
            self.assertEqual(result["request_id"], "voice-42")
            execute.assert_called_once_with(request, resource=RESOURCE, backend="@py", timeout_ms=3000)

    def test_voice_call_wrong_route_never_opens_instrument(self):
        with patch("c_instrument.dg4102_board.device_lock", return_value=nullcontext()), \
                patch("c_instrument.dg4102_board.load_binding", return_value=dict(ROW, physical_port="HOST2")), \
                patch("c_instrument.dg4102_board.devices", return_value=[dict(ROW, usb_route="1-1.3")]), \
                patch("c_instrument.dg4102.execute") as execute:
            result = execute_host2({"action": "status"})
            self.assertEqual(result["error_code"], "HOST2_DEVICE_NOT_FOUND")
            execute.assert_not_called()

    def test_pyvisa_py_unsupported_clear_is_allowed_but_io_failure_is_not(self):
        for code, allowed in ((-1073807257, True), (-1073807339, False)):
            manager = Mock()
            error = RuntimeError("clear failed")
            error.error_code = code
            manager.open_resource.return_value.clear.side_effect = error
            with patch("c_instrument.transport.resource_manager", return_value=manager):
                if allowed:
                    port = DGTransport(RESOURCE, "@py")
                    port.close()
                else:
                    with self.assertRaises(InstrumentError) as caught:
                        DGTransport(RESOURCE, "@py")
                    self.assertEqual(caught.exception.code, "DEVICE_CLEAR_FAILED")


if __name__ == "__main__":
    unittest.main()
