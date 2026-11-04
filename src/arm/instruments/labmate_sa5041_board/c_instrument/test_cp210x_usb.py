import errno
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from c_instrument.cp210x_usb import Cp210xTransport
from c_instrument.sa5041 import read_sa5041
from c_instrument.transport import InstrumentError


class Cp210xTests(unittest.TestCase):
    def context(self, reply=b"\x00\x00VOLT:DC\r\n", devices=1, active=False):
        class Timeout(Exception):
            pass

        incoming = Mock(bmAttributes=2, bEndpointAddress=0x81)
        outgoing = Mock(bmAttributes=2, bEndpointAddress=0x01)
        incoming.read.side_effect = [reply]
        outgoing.write.side_effect = lambda data, **kw: len(data)

        class Interface(list):
            bInterfaceNumber = 0

        device = Mock()
        device.ctrl_transfer.side_effect = lambda req_type, req, value, index, data, **kw: len(data)
        device.get_active_configuration.return_value = {(0, 0): Interface([incoming, outgoing])}
        device.is_kernel_driver_active.return_value = active
        core = SimpleNamespace(find=lambda **kw: [device] * devices, USBTimeoutError=Timeout)
        util = SimpleNamespace(claim_interface=Mock(), release_interface=Mock(),
                               dispose_resources=Mock(), endpoint_type=lambda x: x & 3,
                               endpoint_direction=lambda x: x & 0x80)
        usb = SimpleNamespace(core=core, util=util)
        return {"usb": usb, "usb.core": core, "usb.util": util}, device, incoming, outgoing

    def test_setup_raw_padding_and_cleanup(self):
        modules, device, incoming, outgoing = self.context()
        with patch.dict(sys.modules, modules), patch("c_instrument.cp210x_usb.time.sleep"):
            connection = Cp210xTransport()
            self.assertEqual(connection.query(":FUNCtion?"), "\x00\x00VOLT:DC")
            connection.close()
        calls = device.ctrl_transfer.call_args_list
        self.assertEqual([c.args[1] for c in calls], [0, 0x1e, 3, 0x13, 7, 0x12, 0])
        self.assertEqual(calls[1].args[4], struct.pack("<I", 9600))
        self.assertEqual(calls[2].args[2], 0x0800)
        self.assertEqual(calls[3].args[4], bytes(16))
        self.assertEqual(calls[4].args[2], 0x0300)
        self.assertEqual(calls[5].args[2], 0x000f)
        self.assertTrue(all(c.args[0] == 0x41 and c.args[3] == 0 for c in calls))
        outgoing.write.assert_called_once_with(b":FUNCtion?\n", timeout=3000)
        modules["usb.util"].release_interface.assert_called_once_with(device, 0)

    def test_missing_and_busy_devices(self):
        for devices, active, code in [(0, False, "DEVICE_OPEN_FAILED"),
                                      (2, False, "DEVICE_OPEN_FAILED"),
                                      (1, True, "DEVICE_BUSY")]:
            modules, device, incoming, outgoing = self.context(devices=devices, active=active)
            with patch.dict(sys.modules, modules):
                with self.assertRaises(InstrumentError) as caught:
                    Cp210xTransport()
            self.assertEqual(caught.exception.code, code)
            device.ctrl_transfer.assert_not_called()

    def test_partial_timeout_and_extra_reply_rejected(self):
        for reply, expected in [(b"123", "QUERY_TIMEOUT"),
                                (b"123\n456\n", "RESPONSE_INVALID")]:
            modules, device, incoming, outgoing = self.context(reply=reply)
            incoming.read.side_effect = [reply, modules["usb.core"].USBTimeoutError()]
            with patch.dict(sys.modules, modules), patch("c_instrument.cp210x_usb.time.sleep"):
                connection = Cp210xTransport()
                with self.assertRaises(InstrumentError) as caught:
                    connection.query(":READ?")
                connection.close()
            self.assertEqual(caught.exception.code, expected)

    def test_short_configuration_write_releases_claim(self):
        modules, device, incoming, outgoing = self.context()
        device.ctrl_transfer.side_effect = lambda req_type, req, value, index, data, **kw: (
            2 if req == 0x1e else len(data))
        with patch.dict(sys.modules, modules):
            with self.assertRaises(InstrumentError) as caught:
                Cp210xTransport()
        self.assertEqual(caught.exception.code, "DEVICE_OPEN_FAILED")
        modules["usb.util"].release_interface.assert_called_once_with(device, 0)
        modules["usb.util"].dispose_resources.assert_called_once_with(device)

    def test_meter_entrypoint_uses_usb_transport(self):
        modules, device, incoming, outgoing = self.context()
        incoming.read.side_effect = [b"\x00\x00VOLT:DC\r\n", b"0.5V\r\n", b"VOLT:DC\r\n"]
        with patch.dict(sys.modules, modules), patch("c_instrument.cp210x_usb.time.sleep"):
            result = read_sa5041("cp210x-usb")
        self.assertEqual(result["transport"], "cp210x_usb")
        self.assertTrue(result["valid"])
        self.assertEqual((result["value"], result["unit"]), (0.5, "V"))
        self.assertEqual(outgoing.write.call_count, 3)
        modules["usb.util"].release_interface.assert_called_once_with(device, 0)
