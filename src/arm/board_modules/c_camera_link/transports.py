"""UART first; Linux spidev backend for the future hardware SPI configuration."""

import ctypes
from pathlib import Path
import time
import sys
import struct

from .protocol import ACK, SPI_SIZE, check_ack, spi_packets


class UartLink:
    def __init__(self, port, baud=115200, timeout=5):
        import serial
        self.port = serial.Serial(port=None, baudrate=baud, timeout=0.1,
                                  write_timeout=timeout, rtscts=False, dsrdtr=False)
        self.port.dtr = False
        self.port.rts = False
        self.port.port = port
        self.port.open()
        self.port.reset_input_buffer()
        self.timeout = timeout
        self.baud = baud

    def send(self, data, sequence):
        # The overall deadline includes wire time, not only ESP32 processing.
        self.port.write_timeout = self.timeout + len(data) * 10.0 / self.baud
        if self.port.write(data) != len(data):
            raise IOError("Short UART write")
        deadline = time.monotonic() + self.port.write_timeout
        reply = bytearray()
        while time.monotonic() < deadline:
            reply.extend(self.port.read(64))
            pos = reply.find(b"LMAK")
            if pos >= 0 and len(reply) >= pos + ACK.size:
                check_ack(bytes(reply[pos:pos + ACK.size]), sequence)
                return
            if len(reply) > 256:
                del reply[:-3]
        raise TimeoutError("No UART frame acknowledgement; stop before retrying")

    def close(self):
        self.port.close()


class SpiTransfer(ctypes.Structure):
    _fields_ = [("tx_buf", ctypes.c_uint64), ("rx_buf", ctypes.c_uint64),
                ("len", ctypes.c_uint32), ("speed_hz", ctypes.c_uint32),
                ("delay_usecs", ctypes.c_uint16), ("bits_per_word", ctypes.c_uint8),
                ("cs_change", ctypes.c_uint8), ("tx_nbits", ctypes.c_uint8),
                ("rx_nbits", ctypes.c_uint8), ("word_delay_usecs", ctypes.c_uint8),
                ("pad", ctypes.c_uint8)]


class SpiLink:
    def __init__(self, device, ready_path, speed=1000000, timeout=5, mode=0):
        import fcntl
        import os
        if speed <= 0 or timeout <= 0:
            raise ValueError("SPI speed/timeout must be positive")
        self.ready = Path(ready_path)
        if self.ready.read_text().strip() not in ("0", "1"):
            raise ValueError("Ready GPIO must expose a readable 0/1 value")
        self.fd = os.open(device, os.O_RDWR)
        self.speed, self.timeout = speed, timeout
        try:
            fcntl.ioctl(self.fd, 0x40016b01, bytes([mode]))
            fcntl.ioctl(self.fd, 0x40016b03, bytes([8]))  # 8 bits per word
        except Exception:
            os.close(self.fd)
            raise

    def exchange(self, packet):
        import fcntl
        # Each queued slave transaction pulses READY low for at least 20 ms.
        # Waiting for low between transactions prevents clocking an unqueued slave.
        deadline = time.monotonic() + self.timeout
        while self.ready.read_text().strip() != "1":
            if time.monotonic() >= deadline:
                raise TimeoutError("ESP32 SPI READY did not become high")
            time.sleep(0.0002)
        tx = ctypes.create_string_buffer(packet, SPI_SIZE)
        rx = ctypes.create_string_buffer(SPI_SIZE)
        transfer = SpiTransfer(ctypes.addressof(tx), ctypes.addressof(rx),
                               SPI_SIZE, self.speed, 0, 8, 0, 0, 0, 0, 0)
        ioctl = 0x40006b00 | (ctypes.sizeof(SpiTransfer) << 16)
        if fcntl.ioctl(self.fd, ioctl, bytearray(bytes(transfer)), True) != SPI_SIZE:
            raise IOError("Short SPI transaction")
        while self.ready.read_text().strip() != "0":
            if time.monotonic() >= deadline:
                raise TimeoutError("SPI READY did not acknowledge transaction")
            time.sleep(0.0002)
        return rx.raw

    def send(self, data, sequence):
        for packet in spi_packets(data):
            self.exchange(packet)
        # Reply is queued after processing the last payload transaction.
        reply = self.exchange(bytes(SPI_SIZE))
        check_ack(reply[:ACK.size], sequence)

    def close(self):
        import os
        os.close(self.fd)


class EmioSpiLink(SpiLink):
    """Mode1, alternating READY token; every frame uses an even transfer count."""

    def __init__(self, device, ready_path, speed=2000000, timeout=5, cs_high=False,
                 frame_poll=False, set_speed=False):
        # Configure once: changing mode twice can introduce idle CS edges.
        mode = 1 | (4 if cs_high else 0)  # SPI_CPHA | optional SPI_CS_HIGH
        super().__init__(device, ready_path, speed, timeout, mode=mode)
        if set_speed:
            import fcntl
            try:
                fcntl.ioctl(self.fd, 0x40046b04, struct.pack('=I', speed))
                value = bytearray(4)
                fcntl.ioctl(self.fd, 0x80046b04, value, True)
                configured = struct.unpack('=I', value)[0]
                if not configured:
                    raise IOError('spidev returned zero configured speed')
                print('SPI speed setting: requested={} readback={} Hz (not measured SCLK)'.format(
                    speed, configured), file=sys.stderr, flush=True)
            except Exception:
                self.close()
                raise
        print('SPI config: mode1 controller_CS={} (diagnostic={}) ACK={} requested_hz={}'.format(
            'high' if cs_high else 'low', cs_high,
            'frame' if frame_poll else 'chunk', speed), file=sys.stderr, flush=True)
        self.token = 1
        self.completed = 0
        self.context = 'startup'
        self.frame_poll = frame_poll

    def exchange(self, packet):
        import fcntl
        if len(packet) != SPI_SIZE:
            raise ValueError("SPI EMIO packets must be exactly 1024 bytes")
        deadline = time.monotonic() + self.timeout
        completed = getattr(self, 'completed', 0)
        context = getattr(self, 'context', 'unspecified')
        observed = self.ready.read_text().strip()
        if completed < 4:
            print('SPI wait: transaction={} {} expected_READY={} actual_READY={}'.format(
                completed + 1, context, self.token, observed), file=sys.stderr, flush=True)
        while observed != str(self.token):
            if time.monotonic() >= deadline:
                raise TimeoutError('SPI READY timeout: transaction={} {}, expected={}, actual={}, '
                                   'completed_ioctls={}; reset ESP32 before retrying'.format(
                                       completed + 1, context, self.token, observed, completed))
            time.sleep(0.0002)
            observed = self.ready.read_text().strip()
        tx = ctypes.create_string_buffer(packet, SPI_SIZE)
        rx = ctypes.create_string_buffer(SPI_SIZE)
        transfer = SpiTransfer(ctypes.addressof(tx), ctypes.addressof(rx),
                               SPI_SIZE, self.speed, 0, 8, 0, 0, 0, 0, 0)
        operation = 0x40006b00 | (ctypes.sizeof(SpiTransfer) << 16)
        started = time.monotonic()
        transferred = fcntl.ioctl(self.fd, operation, bytearray(bytes(transfer)), True)
        if transferred != SPI_SIZE:
            raise IOError('Short SPI transfer: transaction={} {} bytes={}/{}; reset ESP32 before retrying'.format(
                completed + 1, context, transferred, SPI_SIZE))
        self.completed = completed + 1
        if completed < 4:
            print('SPI ioctl done: transaction={} bytes={} elapsed_ms={:.2f} rx_prefix={}'.format(
                completed + 1, transferred, (time.monotonic() - started) * 1000,
                rx.raw[:12].hex()), file=sys.stderr, flush=True)
        self.token ^= 1
        return rx.raw

    def send(self, data, sequence):
        reply = b""
        if getattr(self, 'frame_poll', False):
            chunks = 0
            for chunks, packet in enumerate(spi_packets(data), 1):
                self.context = 'frame={} chunk={} DATA'.format(sequence, chunks)
                self.exchange(packet)
            self.context = 'frame={} final POLL'.format(sequence)
            reply = self.exchange(bytes(SPI_SIZE))
            # Preserve READY=1 at frame boundaries, including after process restart.
            # The ACK is consumed above; the optional padding reply is ignored.
            if chunks % 2 == 0:
                self.context = 'frame={} parity POLL'.format(sequence)
                self.exchange(bytes(SPI_SIZE))
            check_ack(reply[:ACK.size], sequence)
            return
        for index, packet in enumerate(spi_packets(data)):
            self.context = 'frame={} chunk={} DATA'.format(sequence, index + 1)
            self.exchange(packet)
            self.context = 'frame={} chunk={} POLL'.format(sequence, index + 1)
            reply = self.exchange(bytes(SPI_SIZE))
        check_ack(reply[:ACK.size], sequence)
