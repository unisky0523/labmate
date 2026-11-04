"""Bounded, CRC-checked JPEG frames; shared by UART and SPI transports."""

import struct
import zlib

MAGIC = b"LMJPEG01"
HEADER = struct.Struct("<8sIII")
ACK = struct.Struct("<4sII")
MAX_JPEG = 32768
SPI_SIZE = 1024
CHUNK = struct.Struct("<4sHH")


def frame(jpeg, sequence):
    if not 4 <= len(jpeg) <= MAX_JPEG:
        raise ValueError("JPEG must be 4..32768 bytes")
    if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
        raise ValueError("Expected a complete JPEG")
    return HEADER.pack(MAGIC, sequence, len(jpeg), zlib.crc32(jpeg)) + jpeg


def check_ack(data, sequence):
    if len(data) != ACK.size:
        raise IOError("Incomplete acknowledgement")
    magic, received, status = ACK.unpack(data)
    if magic != b"LMAK" or received != sequence:
        raise IOError("Acknowledgement does not match frame")
    if status:
        raise IOError("ESP32 rejected frame; status={}".format(status))


def spi_packets(data):
    for start in range(0, len(data), SPI_SIZE - CHUNK.size):
        part = data[start:start + SPI_SIZE - CHUNK.size]
        yield (CHUNK.pack(b"LMCK", len(part), 0) + part).ljust(SPI_SIZE, b"\x00")


