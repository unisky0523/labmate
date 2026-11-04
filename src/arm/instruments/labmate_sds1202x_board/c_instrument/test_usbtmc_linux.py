import errno
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from c_instrument.transport import InstrumentError
from c_instrument.usbtmc_linux import USBTMC_IOCTL_SET_TIMEOUT, UsbtmcTransport


class UsbtmcTransportTests(unittest.TestCase):
    def test_text_and_binary_queries(self):
        writes = []
        closed = []

        def write(fd, data):
            writes.append((fd, data))
            return len(data)

        def ioctl(fd, request, value):
            self.assertEqual((fd, request, value),
                             (7, USBTMC_IOCTL_SET_TIMEOUT, b"\xb8\x0b\x00\x00"))

        fake_fcntl = SimpleNamespace(ioctl=ioctl)
        with patch.dict(sys.modules, {"fcntl": fake_fcntl}), \
                patch("c_instrument.usbtmc_linux.os.open", return_value=7), \
                patch("c_instrument.usbtmc_linux.os.write", side_effect=write), \
                patch("c_instrument.usbtmc_linux.os.read", side_effect=[b"SIGLENT\n", b"BM\x00\xff"]), \
                patch("c_instrument.usbtmc_linux.os.close", side_effect=closed.append):
            port = UsbtmcTransport("/dev/usbtmc0", 3000)
            self.assertEqual(port.query("*IDN?"), "SIGLENT")
            self.assertEqual(port.query_raw("SCDP"), b"BM\x00\xff")
            port.close()
        self.assertEqual(writes, [(7, b"*IDN?\n"), (7, b"SCDP\n")])
        self.assertEqual(closed, [7])

    def test_timeout_and_invalid_path(self):
        with self.assertRaises(InstrumentError) as error:
            UsbtmcTransport("/dev/ttyUSB0")
        self.assertEqual(error.exception.code, "CONFIG_INVALID")

        fake_fcntl = SimpleNamespace(ioctl=lambda *args: None)
        with patch.dict(sys.modules, {"fcntl": fake_fcntl}), \
                patch("c_instrument.usbtmc_linux.os.open", return_value=7), \
                patch("c_instrument.usbtmc_linux.os.write", return_value=6), \
                patch("c_instrument.usbtmc_linux.os.read",
                      side_effect=OSError(errno.ETIMEDOUT, "timed out")), \
                patch("c_instrument.usbtmc_linux.os.close"):
            port = UsbtmcTransport("/dev/usbtmc0")
            with self.assertRaises(InstrumentError) as error:
                port.query("*IDN?")
            self.assertEqual(error.exception.code, "QUERY_TIMEOUT")
            port.close()
