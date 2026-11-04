import hashlib
import os
import pathlib
import select
import sys
import termios
import time

size, expected, destination, speed = int(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4])
old = termios.tcgetattr(0)
target = pathlib.Path(destination)
temporary = target.with_name(target.name + '.incoming')
try:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or temporary.exists():
        raise RuntimeError('destination already exists')
    print('__SPI_SWITCH__', flush=True)
    time.sleep(0.7)
    settings = termios.tcgetattr(0)
    settings[0] = settings[1] = settings[3] = 0
    settings[2] = (settings[2] & ~(termios.CSIZE | termios.PARENB)) | termios.CS8
    settings[6][termios.VMIN] = 1
    settings[6][termios.VTIME] = 0
    settings[4] = settings[5] = getattr(termios, 'B' + str(speed))
    termios.tcsetattr(0, termios.TCSANOW, settings)
    os.write(1, b'__SPI_READY__\n')
    digest = hashlib.sha256()
    offset = 0
    with temporary.open('xb') as output:
        while offset < size:
            count = min(1024, size - offset)
            chunk = bytearray()
            while len(chunk) < count:
                if not select.select([0], [], [], 12)[0]:
                    raise TimeoutError('UART input timeout')
                data = os.read(0, count - len(chunk))
                if not data:
                    raise RuntimeError('UART EOF')
                chunk.extend(data)
            output.write(chunk)
            digest.update(chunk)
            offset += count
            os.write(1, ('__SPI_ACK_%d__\n' % offset).encode())
        output.flush()
        os.fsync(output.fileno())
    if digest.hexdigest() != expected:
        raise RuntimeError('SHA256 mismatch: ' + digest.hexdigest())
    temporary.rename(target)
    os.write(1, ('__SPI_SUCCESS__ ' + digest.hexdigest() + '\n').encode())
except Exception as error:
    os.write(1, ('__SPI_ERROR__ ' + str(error) + '\n').encode())
finally:
    termios.tcdrain(1)
    time.sleep(0.5)
    termios.tcsetattr(0, termios.TCSANOW, old)
