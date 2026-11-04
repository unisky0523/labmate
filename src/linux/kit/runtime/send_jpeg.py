#!/usr/bin/env python3
"""Send one JPEG using Linux spidev; no third-party Python packages required."""
import argparse
import ctypes
import fcntl
import glob
import os
from pathlib import Path
import struct
import time
import zlib

MAGIC, ACK_MAGIC = 0x314A4D4C, 0x31414D4C
CHUNK, MAX_JPEG = 1024, 65536
FIRST, LAST, POLL = 1, 2, 4

def packet(frame, total, offset, payload, frame_crc, flags):
    header = struct.pack("<7I", MAGIC, frame, total, offset, len(payload), frame_crc, flags)
    crc = zlib.crc32(payload, zlib.crc32(header))
    result = header + struct.pack("<I", crc) + payload
    return result if flags == POLL else result.ljust(32 + CHUNK, b"\0")

def check_ack(data, frame, expected_offset, complete, frame_crc):
    words = struct.unpack("<8I", data[:32])
    if words[0] != ACK_MAGIC or words[7] != zlib.crc32(data[:28]):
        raise RuntimeError("ACK format/CRC error; inspect SPI mode and wiring")
    if words[1:5] != (frame, expected_offset, int(complete), frame_crc):
        raise RuntimeError("ESP32 rejected packet: frame,offset,status,crc=" + repr(words[1:5]))

def find_spi():
    for node in glob.glob("/sys/bus/spi/devices/spi*.*"):
        compatible = Path(node) / "of_node/compatible"
        if compatible.exists() and b"labmate,esp32-image-link" in compatible.read_bytes().split(b"\0"):
            return "/dev/" + Path(node).name.replace("spi", "spidev", 1)
    raise RuntimeError("SPI device not found; apply the supplied device-tree fragment first")

def ready_path():
    for chip in glob.glob("/sys/class/gpio/gpiochip*"):
        label = (Path(chip) / "label").read_text().strip()
        if "zynq" in label.lower() or "e000a000" in label.lower():
            line = int((Path(chip) / "base").read_text()) + 65
            gpio = Path("/sys/class/gpio/gpio%d" % line)
            if not gpio.exists():
                Path("/sys/class/gpio/export").write_text(str(line))
            (gpio / "direction").write_text("in")
            return str(gpio / "value")
    raise RuntimeError("PS GPIO controller not found; use --ready-value with the correct sysfs value path")

class SpiLink:
    def __init__(self, spi, ready, hz):
        self.spi = os.open(spi, os.O_RDWR)
        self.ready = os.open(ready, os.O_RDONLY)
        self.hz, self.token = hz, 1
        fcntl.ioctl(self.spi, 0x40016B01, struct.pack("B", 1))  # SPI mode1
        fcntl.ioctl(self.spi, 0x40016B03, struct.pack("B", 8))
        fcntl.ioctl(self.spi, 0x40046B04, struct.pack("=I", hz))

    def transfer(self, data):
        deadline = time.monotonic() + 3
        while True:
            os.lseek(self.ready, 0, os.SEEK_SET)
            if os.read(self.ready, 1) == str(self.token).encode():
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("READY token timeout; check ESP32/reset and U4 KEY wiring")
            time.sleep(0.0002)
        tx, rx = ctypes.create_string_buffer(data), ctypes.create_string_buffer(len(data))
        # Linux UAPI spi_ioc_transfer is 32 bytes on both ARM32 and x86_64.
        transfer = struct.pack("=QQIIHBBBBBB", ctypes.addressof(tx), ctypes.addressof(rx),
                               len(data), self.hz, 0, 8, 0, 0, 0, 0, 0)
        fcntl.ioctl(self.spi, 0x40206B00, transfer)  # SPI_IOC_MESSAGE(1), one CS assertion
        self.token ^= 1
        return rx.raw

    def close(self):
        os.close(self.ready)
        os.close(self.spi)

def send(link, jpeg, frame):
    crc, start = zlib.crc32(jpeg), time.monotonic()
    for offset in range(0, len(jpeg), CHUNK):
        payload = jpeg[offset:offset + CHUNK]
        last = offset + len(payload) == len(jpeg)
        flags = (FIRST if offset == 0 else 0) | (LAST if last else 0)
        link.transfer(packet(frame, len(jpeg), offset, payload, crc, flags))
        ack = link.transfer(packet(frame, len(jpeg), 0, b"", crc, POLL))
        check_ack(ack, frame, offset + len(payload), last, crc)
    print("JPEG delivered: %d bytes, CRC32=%08x, %.3f s" % (len(jpeg), crc, time.monotonic() - start))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("jpeg")
    p.add_argument("--spi", help="e.g. /dev/spidev1.0; default discovers the DT compatible")
    p.add_argument("--ready-value", help="/sys/class/gpio/gpioN/value; default PS base +65")
    p.add_argument("--hz", type=int, default=2000000, help="requested SCLK, actual clock may be rounded down")
    a = p.parse_args()
    jpeg = Path(a.jpeg).read_bytes()
    if not 4 <= len(jpeg) <= MAX_JPEG or not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
        p.error("input must be a JPEG with SOI/EOI markers, at most 65536 bytes")
    if not 650000 <= a.hz <= 4000000:
        p.error("initial configuration range: requested 650000..4000000 Hz")
    link = SpiLink(a.spi or find_spi(), a.ready_value or ready_path(), a.hz)
    try:
        send(link, jpeg, int(time.time() * 1000) & 0xFFFFFFFF)
    finally:
        link.close()

if __name__ == "__main__":
    main()
