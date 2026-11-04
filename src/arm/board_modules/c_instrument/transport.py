"""Optional VISA and serial transports; dependencies are loaded on demand."""

import time


class InstrumentError(Exception):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code


def resource_manager(backend):
    try:
        import pyvisa
    except ImportError as exc:
        raise InstrumentError("DEPENDENCY_MISSING", "Use the board launcher with c_instrument/vendor or install requirements-scope-board.txt") from exc
    try:
        return pyvisa.ResourceManager() if backend is None else pyvisa.ResourceManager(backend)
    except Exception as exc:
        raise InstrumentError("VISA_BACKEND_FAILED", str(exc)) from exc


def list_resources(backend="@py"):
    manager = resource_manager(backend)
    try:
        return list(manager.list_resources())
    except Exception as exc:
        raise InstrumentError("DISCOVERY_FAILED", str(exc)) from exc
    finally:
        manager.close()


class VisaTransport:
    def __init__(self, resource, backend="@py", timeout_ms=3000,
                 read_termination="\n", write_termination="\n"):
        self.manager = resource_manager(backend)
        self.device = None
        try:
            self.device = self.manager.open_resource(resource)
            self.device.timeout = timeout_ms
            self.device.read_termination = read_termination
            self.device.write_termination = write_termination
        except Exception as exc:
            self.close()
            raise InstrumentError("DEVICE_OPEN_FAILED", str(exc)) from exc

    def query(self, command):
        try:
            return self.device.query(command).strip()
        except Exception as exc:
            # Do not continue querying after an I/O error: a late response could
            # otherwise be mistaken for the next measurement's reply.
            code = "QUERY_TIMEOUT" if getattr(exc, "error_code", None) == -1073807339 else "QUERY_FAILED"
            raise InstrumentError(code, str(exc)) from exc

    def query_raw(self, command):
        termination = self.device.read_termination
        chunk_size = self.device.chunk_size
        try:
            # Binary screenshots can contain LF bytes; text termination truncates them.
            self.device.read_termination = None
            self.device.chunk_size = max(chunk_size, 2 * 1024 * 1024)
            self.device.write(command)
            return self.device.read_raw()
        except Exception as exc:
            code = "QUERY_TIMEOUT" if getattr(exc, "error_code", None) == -1073807339 else "QUERY_FAILED"
            raise InstrumentError(code, str(exc)) from exc
        finally:
            self.device.read_termination = termination
            self.device.chunk_size = chunk_size

    def close(self):
        try:
            if self.device is not None:
                self.device.close()
        finally:
            self.manager.close()


class SerialTransport:
    """LF-terminated ASCII queries, with one deadline for the entire reply."""

    def __init__(self, port, baudrate=9600, timeout_ms=3000):
        try:
            import serial
        except ImportError as exc:
            raise InstrumentError("DEPENDENCY_MISSING", "The optional ttyUSB transport needs pyserial==3.5; cp210x-usb uses PyUSB") from exc
        self.device = None
        self.timeout_seconds = timeout_ms / 1000.0
        try:
            self.device = serial.Serial(
                port=None, baudrate=baudrate, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                timeout=0, write_timeout=self.timeout_seconds,
                xonxoff=False, rtscts=False, dsrdtr=False)
            # Match the successful .NET SerialPort defaults. Disabling flow
            # control alone does not lower pyserial's default DTR/RTS states.
            self.device.dtr = False
            self.device.rts = False
            self.device.port = port
            self.device.open()
            time.sleep(0.5)
            self.device.reset_input_buffer()
        except Exception as exc:
            self.close()
            raise InstrumentError("DEVICE_OPEN_FAILED", str(exc)) from exc

    def query(self, command):
        if "\n" in command or "\r" in command:
            raise InstrumentError("CONFIG_INVALID", "Query must not contain line endings")
        reply = bytearray()
        try:
            message = (command + "\n").encode("ascii")
            if self.device.write(message) != len(message):
                raise InstrumentError("QUERY_FAILED", "Incomplete serial write")
            deadline = time.monotonic() + self.timeout_seconds
            while len(reply) < 512:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                # Changing pyserial.timeout on an open Windows port also calls
                # SetCommState. Keep configuration fixed while bytes are in flight.
                if not self.device.in_waiting:
                    time.sleep(min(0.01, remaining))
                    continue
                part = self.device.read(1)
                if not part:
                    break
                reply.extend(part)
                if part == b"\n":
                    return reply.decode("ascii").strip()
            code = "RESPONSE_TOO_LONG" if len(reply) >= 512 else "QUERY_TIMEOUT"
            raise InstrumentError(code, "Incomplete reply; received {!r}".format(bytes(reply)))
        except InstrumentError:
            raise
        except Exception as exc:
            raise InstrumentError("QUERY_FAILED", str(exc)) from exc

    def close(self):
        if self.device is not None:
            self.device.close()
