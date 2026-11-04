#!/usr/bin/env python3
"""Initialize SPI mode and READY input without issuing any SPI transfer."""
import fcntl
import os
from pathlib import Path
import struct
import time

matches = []
for node in Path('/sys/bus/spi/devices').glob('spi*.*'):
    compatible = node / 'of_node/compatible'
    if compatible.exists() and b'labmate,esp32-image-link' in compatible.read_bytes().split(b'\0'):
        matches.append('/dev/spidev' + node.name[3:])
if len(matches) != 1:
    raise RuntimeError('Expected exactly one ESP32 image-link SPI device: ' + repr(matches))
chips = []
for chip in Path('/sys/class/gpio').glob('gpiochip*'):
    label = (chip / 'label').read_text().lower()
    if ('zynq' in label or 'e000a000' in label) and int((chip / 'ngpio').read_text()) > 65:
        chips.append(chip)
if len(chips) != 1:
    raise RuntimeError('Expected exactly one PS GPIO controller')
number = int((chips[0] / 'base').read_text()) + 65
gpio = Path('/sys/class/gpio/gpio%d' % number)
if not gpio.exists():
    try:
        Path('/sys/class/gpio/export').write_text(str(number))
    except OSError:
        if not gpio.exists():
            raise
deadline = time.monotonic() + 2
while not (gpio / 'direction').exists():
    if time.monotonic() >= deadline:
        raise RuntimeError('READY GPIO export timed out')
    time.sleep(0.01)
(gpio / 'direction').write_text('in')
fd = os.open(matches[0], os.O_RDWR)
try:
    fcntl.ioctl(fd, 0x40016B01, struct.pack('B', 1))
    fcntl.ioctl(fd, 0x40016B03, struct.pack('B', 8))
    mode = bytearray(1)
    fcntl.ioctl(fd, 0x80016B01, mode, True)
    if mode[0] != 1:
        raise RuntimeError('SPI mode readback failed')
finally:
    os.close(fd)
print('LABMATE_SPI_READY device=%s mode=1 bits=8 ready=%s direction=in' % (matches[0], gpio / 'value'))
