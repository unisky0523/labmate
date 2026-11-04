import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from c_instrument.reader import acquire, load_config, parse_value, read_instrument, validate_config
from c_instrument.transport import InstrumentError, SimulatedTransport, VisaTransport


CONFIG = Path(__file__).parent / "configs" / "simulation.json"


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(CONFIG)

    def test_scalar_parsing_does_not_guess_units_or_extract_unrelated_numbers(self):
        spec = {"unit": "V"}
        self.assertEqual(parse_value("-1.25E-03 V", spec), (-0.00125, "V"))
        for raw in ("nan", "inf", "9.9E37", "channel1:3.2", "1,2", "", "2mV"):
            with self.subTest(raw=raw), self.assertRaises(InstrumentError):
                parse_value(raw, spec)

    def test_partial_results_keep_valid_measurement_and_raw_error(self):
        responses = dict(self.config["simulation_responses"])
        responses["DEMO:FREQUENCY?"] = "9.9E37"
        result = acquire(self.config, SimulatedTransport(responses), "b-001", True)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["valid"])
        self.assertEqual(result["valid_count"], 1)
        self.assertEqual(result["measurements"][0]["value"], 3.298)
        self.assertIsNone(result["measurements"][1]["value"])
        self.assertEqual(result["measurements"][1]["raw_text"], "9.9E37")

    def test_timeout_stops_subsequent_queries_to_prevent_late_reply_mixup(self):
        config = copy.deepcopy(self.config)
        config["measurements"].append({"id": "third", "label": "third", "query": "THIRD?", "unit": "V"})
        calls = []

        class TimeoutTransport:
            def query(inner, command):
                calls.append(command)
                if command == "DEMO:VOLTAGE?":
                    raise InstrumentError("QUERY_TIMEOUT", "test timeout")
                return "LABMATE,SIMULATOR,NO-HARDWARE,1.0"

        result = acquire(config, TimeoutTransport(), simulated=True)
        self.assertEqual(calls, ["*IDN?", "DEMO:VOLTAGE?"])
        self.assertEqual(result["measurements"][1]["error_code"], "SKIPPED_AFTER_IO_ERROR")
        self.assertEqual(result["measurements"][2]["error_code"], "SKIPPED_AFTER_IO_ERROR")

    def test_identity_mismatch_never_queries_measurements(self):
        result = acquire(self.config, SimulatedTransport({"*IDN?": "OTHER,MODEL"}), simulated=True)
        self.assertEqual(result["error_code"], "DEVICE_IDENTITY_MISMATCH")
        self.assertEqual(result["measurements"], [])

    def test_simulation_is_explicit_and_saved_with_request_id(self):
        with tempfile.TemporaryDirectory() as output:
            result = read_instrument(CONFIG, simulate=True, output=output, request_id="../../b-request")
            saved = json.loads(Path(result["result_path"]).read_text(encoding="utf-8"))
            self.assertTrue(saved["simulated"])
            self.assertEqual(saved["source"], "simulated_scpi")
            self.assertEqual(saved["request_id"], "../../b-request")
            self.assertEqual(Path(saved["result_path"]).parent.parent, Path(output))
            self.assertEqual(saved["status"], "complete")

    def test_demo_config_cannot_contact_hardware(self):
        with patch("c_instrument.reader.VisaTransport") as transport:
            with self.assertRaises(InstrumentError) as error:
                read_instrument(CONFIG, resource="USB0::EXAMPLE::INSTR")
            self.assertEqual(error.exception.code, "CONFIG_DEMO_ONLY")
            transport.assert_not_called()

    def test_template_is_rejected_before_hardware_access(self):
        template = load_config(CONFIG.parent / "device_template.json")
        with self.assertRaises(InstrumentError):
            validate_config(template)

    def test_query_parameters_are_allowed_but_multiple_commands_are_not(self):
        config = copy.deepcopy(self.config)
        config["measurements"][0]["query"] = "MEAS:EXAMPLE? CHAN1"
        validate_config(config, simulate=True)
        for query in ("READ?;RESET", "READ?\nRESET", "RESET"):
            config["measurements"][0]["query"] = query
            with self.subTest(query=query), self.assertRaises(InstrumentError):
                validate_config(config, simulate=True)

    def test_visa_sets_timeouts_and_terminations_and_closes(self):
        with patch("c_instrument.transport.resource_manager") as factory:
            manager = factory.return_value
            device = manager.open_resource.return_value
            device.query.return_value = "1.25\n"
            transport = VisaTransport("USB0::TEST::INSTR", timeout_ms=1200)
            self.assertEqual(device.timeout, 1200)
            self.assertEqual(device.read_termination, "\n")
            self.assertEqual(device.write_termination, "\n")
            self.assertEqual(transport.query("READ?"), "1.25")
            transport.close()
            device.close.assert_called_once()
            manager.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
