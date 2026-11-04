import unittest
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch

from c_instrument.reader import acquire
from c_instrument.sds1202x import ParameterTransport, capture_screen, config_for, decode_screen_image, read_scope
from c_instrument.transport import InstrumentError, SimulatedTransport


class ScopeTests(unittest.TestCase):
    def connection(self, responses):
        return ParameterTransport(SimulatedTransport(dict({
            "*IDN?": "SIGLENT,SDS1202X,SERIAL,FW"}, **responses)))

    def test_header_values_units_and_raw_evidence(self):
        transport = self.connection({"C1:PAVA? PKPK": "C1:PAVA PKPK,2.5E+00V",
                                     "C1:PAVA? FREQ": "C1:PAVA FREQ,1.0E+03Hz"})
        result = acquire(config_for([1], ["PKPK", "FREQ"]), transport)
        self.assertTrue(result["valid"])
        self.assertEqual([r["value"] for r in result["measurements"]], [2.5, 1000])
        self.assertEqual(transport.evidence[1]["raw_text"], "C1:PAVA PKPK,2.5E+00V")

    def test_channel_parameter_mismatch_or_missing_unit_keeps_other_result(self):
        for bad in ["C2:PAVA PKPK,1V", "C1:PAVA RMS,1V", "C1:PAVA PKPK,1", "1Hz", "****"]:
            with self.subTest(bad=bad):
                transport = self.connection({"C1:PAVA? PKPK": bad, "C1:PAVA? FREQ": "100Hz"})
                result = acquire(config_for([1], ["PKPK", "FREQ"]), transport)
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["valid_count"], 1)
                self.assertEqual(result["measurements"][1]["value"], 100)

    def test_overload_and_time_units(self):
        transport = self.connection({"C2:PAVA? PER": "C2:PARAMETER_VALUE PER,3.6E-9S",
                                     "C2:PAVA? RMS": "C2:PAVA RMS,9.9E37V"})
        result = acquire(config_for([2], ["PER", "RMS"]), transport)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["measurements"][0]["unit"], "s")
        self.assertEqual(result["measurements"][1]["error_code"], "VALUE_INVALID")

    def test_wrong_identity_stops_measurement_queries(self):
        transport = self.connection({"*IDN?": "SIGLENT,SDS2104X,SERIAL,FW"})
        result = acquire(config_for([1], ["PKPK"]), transport)
        self.assertEqual(result["error_code"], "DEVICE_IDENTITY_MISMATCH")
        self.assertEqual(len(transport.evidence), 1)

    def test_identity_accepts_actual_siglent_idn_prefix(self):
        transport = self.connection({"*IDN?": "*IDN SIGLENT,SDS1202X,SERIAL,FW",
                                     "C1:PAVA? PKPK": "C1:PAVA PKPK,2.5V"})
        result = acquire(config_for([1], ["PKPK"]), transport)
        self.assertTrue(result["valid"])
        self.assertEqual(result["measurements"][0]["value"], 2.5)

    def test_timeout_stops_following_queries(self):
        class TimeoutTransport:
            def query(self, command):
                if command == "*IDN?":
                    return "SIGLENT,SDS1202X-E,SERIAL,FW"
                raise InstrumentError("QUERY_TIMEOUT", "test")
        transport = ParameterTransport(TimeoutTransport())
        result = acquire(config_for([1], ["PKPK", "FREQ"]), transport)
        self.assertEqual(result["measurements"][1]["error_code"], "SKIPPED_AFTER_IO_ERROR")
        self.assertEqual(len(transport.evidence), 2)

    def test_screen_dump_bmp_and_trailer(self):
        bmp = (struct.pack("<2sIHHI", b"BM", 58, 0, 0, 54)
               + struct.pack("<IiiHHIIiiII", 40, 1, 1, 1, 24, 0, 4, 2835, 2835, 0, 0)
               + b"\x00\x00\x00\x00")
        self.assertEqual(decode_screen_image(bmp + b"\x01\x01\n"), (bmp, "bmp"))
        with self.assertRaises(InstrumentError):
            decode_screen_image(bmp[:40])
        with tempfile.TemporaryDirectory() as root:
            class FakeVisa:
                def __init__(self, *args):
                    pass

                def query(self, command):
                    assert command == "*IDN?"
                    return "*IDN SIGLENT,SDS1202X,SERIAL,FW"

                def query_raw(self, command):
                    assert command == "SCDP"
                    return bmp + b"\x01\x01\n"

                def close(self):
                    pass

            with patch("c_instrument.sds1202x.VisaTransport", FakeVisa):
                result = capture_screen("USB::test", output=Path(root))
            self.assertEqual(Path(result["image_path"]).read_bytes(), bmp)
            self.assertEqual(result["image_bytes"], 58)

    def test_linux_device_path_uses_usbtmc_instead_of_visa(self):
        class FakeUsbtmc:
            def __init__(self, path, timeout_ms):
                self.path = path

            def query(self, command):
                return {"*IDN?": "*IDN SIGLENT,SDS1202X,SERIAL,FW",
                        "C1:PAVA? PKPK": "C1:PAVA PKPK,4.88V"}[command]

            def close(self):
                pass

        with patch("c_instrument.sds1202x.UsbtmcTransport", FakeUsbtmc), \
                patch("c_instrument.sds1202x.VisaTransport",
                      side_effect=AssertionError("VISA must not be used on /dev/usbtmc0")):
            result = read_scope("/dev/usbtmc0", parameters=("PKPK",))
        self.assertTrue(result["identity_verified"])
        self.assertEqual(result["transport"], "usbtmc")
        self.assertEqual(result["measurements"][0]["value"], 4.88)


if __name__ == "__main__":
    unittest.main()
