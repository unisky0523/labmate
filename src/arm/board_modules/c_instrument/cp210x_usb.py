"""CP210x userspace USB bridge, fixed 9600/8N1 with DTR/RTS low."""

import struct
import time

from .transport import InstrumentError


class Cp210xTransport:
    def __init__(self, timeout_ms=3000):
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
            raise InstrumentError("CONFIG_INVALID", "timeout_ms must be positive")
        self.device = None
        self.claimed = False
        self.timeout_ms = timeout_ms
        try:
            import usb.core
            import usb.util
            self.usb = usb
            devices = list(usb.core.find(find_all=True, idVendor=0x10c4, idProduct=0xea60))
            if len(devices) != 1:
                raise InstrumentError("DEVICE_OPEN_FAILED", "Expected one CP210x 10c4:ea60; found {}".format(len(devices)))
            self.device = devices[0]
            config = self.device.get_active_configuration()
            interface = config[(0, 0)]
            self.interface = interface.bInterfaceNumber
            if self.device.is_kernel_driver_active(self.interface):
                raise InstrumentError("DEVICE_BUSY", "Kernel driver is active; use /dev/ttyUSBx instead")
            usb.util.claim_interface(self.device, self.interface)
            self.claimed = True
            endpoints = [e for e in interface if usb.util.endpoint_type(e.bmAttributes) == 2]
            self.input = next(e for e in endpoints if usb.util.endpoint_direction(e.bEndpointAddress) == 0x80)
            self.output = next(e for e in endpoints if usb.util.endpoint_direction(e.bEndpointAddress) == 0)
            # CP210x vendor-interface requests, matching Linux cp210x definitions.
            self.control(0x00, 1)                 # IFC_ENABLE
            self.write_block(0x1e, struct.pack("<I", 9600))
            self.control(0x03, 0x0800)            # SET_LINE_CTL: 8 data, no parity, 1 stop
            self.write_block(0x13, struct.pack("<IIII", 0, 0, 0, 0))
            self.control(0x07, 0x0300)            # SET_MHS: write DTR and RTS, both low
            time.sleep(0.5)
            self.control(0x12, 0x000f)            # PURGE: clear both queues before querying
        except InstrumentError:
            try:
                self.close()
            except Exception:
                pass
            raise
        except Exception as exc:
            try:
                self.close()
            except Exception:
                pass
            raise InstrumentError("DEVICE_OPEN_FAILED", str(exc)) from exc

    def control(self, request, value):
        count = self.device.ctrl_transfer(0x41, request, value, self.interface, b"", timeout=self.timeout_ms)
        if count != 0:
            raise InstrumentError("DEVICE_OPEN_FAILED", "Unexpected CP210x control reply")

    def write_block(self, request, payload):
        count = self.device.ctrl_transfer(0x41, request, 0, self.interface, payload, timeout=self.timeout_ms)
        if count != len(payload):
            raise InstrumentError("DEVICE_OPEN_FAILED", "Incomplete CP210x control write")

    def query(self, command):
        if not command.isascii() or "\n" in command or "\r" in command:
            raise InstrumentError("CONFIG_INVALID", "Use one ASCII command")
        reply = bytearray()
        try:
            message = (command + "\n").encode("ascii")
            if self.output.write(message, timeout=self.timeout_ms) != len(message):
                raise InstrumentError("QUERY_FAILED", "Incomplete USB serial write")
            deadline = time.monotonic() + self.timeout_ms / 1000.0
            while len(reply) < 512:
                remaining = int((deadline - time.monotonic()) * 1000)
                if remaining <= 0:
                    break
                try:
                    part = bytes(self.input.read(512, timeout=max(1, remaining)))
                except self.usb.core.USBTimeoutError:
                    break
                reply.extend(part)
                if b"\n" in reply:
                    line, extra = bytes(reply).split(b"\n", 1)
                    if extra.strip(b"\x00\r\n"):
                        raise InstrumentError("RESPONSE_INVALID", "Unexpected extra serial reply")
                    return line.decode("ascii").strip()
            raise InstrumentError("QUERY_TIMEOUT", "Incomplete reply; received {!r}".format(bytes(reply)))
        except InstrumentError:
            raise
        except Exception as exc:
            raise InstrumentError("QUERY_FAILED", str(exc)) from exc

    def close(self):
        if self.device is not None:
            try:
                if self.claimed:
                    self.control(0x00, 0)
            except Exception:
                pass
            finally:
                try:
                    if self.claimed:
                        self.usb.util.release_interface(self.device, self.interface)
                finally:
                    self.usb.util.dispose_resources(self.device)
                    self.device = None
                    self.claimed = False
