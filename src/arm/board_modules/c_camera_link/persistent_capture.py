"""On-demand frames from one continuously open native V4L2 process."""

import os
from pathlib import Path
import select
import struct
import subprocess
import time


class PersistentCapture:
    def __init__(self, executable, timeout=20, arguments=()):
        if os.name != 'posix':
            raise RuntimeError('Persistent camera capture requires Linux')
        self.timeout = timeout
        self.process = subprocess.Popen([str(Path(executable).resolve(strict=True))] + list(arguments),
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)

    def read_exact(self, length, deadline):
        data = bytearray()
        while len(data) < length:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise TimeoutError('Native camera frame timed out')
            part = os.read(self.process.stdout.fileno(), length-len(data))
            if not part:
                raise RuntimeError('Native camera stream exited before a complete frame')
            data.extend(part)
        return bytes(data)

    def capture(self, path):
        self.process.stdin.write(b'F')
        self.process.stdin.flush()
        deadline = time.monotonic() + self.timeout
        length = struct.unpack('<I', self.read_exact(4, deadline))[0]
        if not 16 <= length <= 16 * 1024 * 1024:
            raise ValueError('Native camera returned invalid frame length')
        data = self.read_exact(length, deadline)
        if not data.startswith(b'P6\n'):
            raise ValueError('Native camera did not return P6 data')
        Path(path).write_bytes(data)

    def close(self):
        try:
            self.process.stdin.close()
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        finally:
            self.process.stdout.close()


class PersistentJpegCapture(PersistentCapture):
    """Read bounded JPEGs and native stage timings without intermediate PPM files."""

    def __init__(self, executable, timeout=20, width=320, quality=50):
        if not 16 <= width <= 800 or not 10 <= quality <= 95:
            raise ValueError('JPEG stream width 16..800 and quality 10..95 required')
        super().__init__(executable, timeout, (str(width), str(quality)))
        self.pending_deadline = None

    def request_jpeg(self):
        if getattr(self, 'pending_deadline', None) is not None:
            raise RuntimeError('A native JPEG request is already pending')
        self.pending_deadline = time.monotonic() + self.timeout
        self.process.stdin.write(b'J')
        self.process.stdin.flush()

    def capture_jpeg(self):
        from .protocol import MAX_JPEG, frame
        if getattr(self, 'pending_deadline', None) is None:
            self.request_jpeg()
        deadline = self.pending_deadline
        length, capture_us, encode_us = struct.unpack('<III', self.read_exact(12, deadline))
        if not 4 <= length <= MAX_JPEG:
            raise ValueError('Native JPEG stream returned invalid frame length')
        jpeg = self.read_exact(length, deadline)
        frame(jpeg, 0)
        self.pending_deadline = None
        return jpeg, capture_us / 1000.0, encode_us / 1000.0
