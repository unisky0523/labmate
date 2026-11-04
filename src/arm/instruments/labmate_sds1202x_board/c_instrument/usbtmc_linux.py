"""Minimal Linux /dev/usbtmc transport for SCPI text and binary replies."""

import errno
import os
import struct

from .transport import InstrumentError


# Linux 5.4 include/uapi/linux/usb/tmc.h: _IOW(91, 10, __u32).
USBTMC_IOCTL_SET_TIMEOUT = 0x40045B0A
MAX_REPLY_BYTES = 2 * 1024 * 1024


class UsbtmcTransport:
    def __init__(self, path, timeout_ms=3000):
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
            raise InstrumentError("CONFIG_INVALID", "timeout_ms must be positive")
        if not isinstance(path, str) or not path.startswith("/dev/usbtmc") or not path[len("/dev/usbtmc"):].isdigit():
            raise InstrumentError("CONFIG_INVALID", "Pass a /dev/usbtmcN device path")
        self.fd = None
        try:
            import fcntl
            self.fd = os.open(path, os.O_RDWR)
            fcntl.ioctl(self.fd, USBTMC_IOCTL_SET_TIMEOUT, struct.pack("I", timeout_ms))
        except (ImportError, OSError) as exc:
            self.close()
            raise InstrumentError("DEVICE_OPEN_FAILED", str(exc)) from exc

    def query_raw(self, command):
        if not isinstance(command, str) or not command.isascii() or "\r" in command or "\n" in command:
            raise InstrumentError("CONFIG_INVALID", "USBTMC command must be one ASCII line")
        message = (command + "\n").encode("ascii")
        try:
            if os.write(self.fd, message) != len(message):
                raise InstrumentError("QUERY_FAILED", "Incomplete USBTMC command write")
            reply = os.read(self.fd, MAX_REPLY_BYTES)
        except InstrumentError:
            raise
        except OSError as exc:
            code = "QUERY_TIMEOUT" if exc.errno in (errno.ETIMEDOUT, errno.EAGAIN) else "QUERY_FAILED"
            raise InstrumentError(code, str(exc)) from exc
        if not reply:
            raise InstrumentError("QUERY_FAILED", "Empty USBTMC reply")
        return reply

    def query(self, command):
        raw = self.query_raw(command)
        try:
            return raw.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise InstrumentError("RESPONSE_INVALID", "Expected ASCII USBTMC reply") from exc

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
