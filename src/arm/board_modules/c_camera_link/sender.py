"""Send one JPEG or capture frames through UART / hardware SPI."""

import argparse
import json
import io
from pathlib import Path
import subprocess
import time
import tempfile

from .protocol import MAX_JPEG, frame


def encode_file(path, width=480, quality=60, encoder='opencv', jpeg_tool=None):
    if not 16 <= width <= 8192 or not 10 <= quality <= 95:
        raise ValueError('width 16..8192 and quality 10..95 required')
    raw = path.read_bytes()
    if raw.startswith(b'\xff\xd8') and raw.endswith(b'\xff\xd9') and len(raw) <= MAX_JPEG:
        return raw
    if encoder == 'native':
        tool = Path(jpeg_tool) if jpeg_tool else Path(__file__).parent / 'native/ppm_to_jpeg_armv7'
        if not tool.is_file():
            raise RuntimeError('Native JPEG tool missing: {}'.format(tool))
        with tempfile.TemporaryDirectory(prefix='labmate_jpeg_') as directory:
            output = Path(directory) / 'frame.jpg'
            command = [str(tool.resolve()), str(path.resolve()), str(output)]
            if (width, quality) != (480, 60):
                command.extend([str(width), str(quality)])
            subprocess.run(command, check=True, timeout=20)
            jpeg = output.read_bytes()
            frame(jpeg, 0)
            return jpeg
    if encoder == 'pillow':
        from PIL import Image
        if width < 16 or not 10 <= quality <= 95:
            raise ValueError('width >= 16 and quality 10..95 required')
        with Image.open(path) as source:
            image = source.convert('RGB')
        if image.width > width:
            image = image.resize((width, max(1, round(image.height * width / image.width))))
        for _ in range(10):
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=quality)
            jpeg = output.getvalue()
            if len(jpeg) <= MAX_JPEG:
                return jpeg
            image = image.resize((max(16, int(image.width * .8)), max(16, int(image.height * .8))))
        raise ValueError('Could not fit JPEG into receiver buffer')
    import cv2
    return encode_image(cv2.imread(str(path)), width, quality)


def encode_image(image, width=480, quality=60, max_bytes=MAX_JPEG):
    import cv2
    if image is None or image.size == 0:
        raise ValueError("Camera/image is empty")
    height, original_width = image.shape[:2]
    if width < 16 or not 10 <= quality <= 95:
        raise ValueError("width >= 16 and quality 10..95 required")
    scale = min(1.0, width / original_width)
    if scale < 1:
        image = cv2.resize(image, (max(1, round(original_width * scale)),
                                   max(1, round(height * scale))))
    for _ in range(10):
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise ValueError("JPEG encoding failed")
        jpeg = encoded.tobytes()
        if len(jpeg) <= max_bytes:
            return jpeg
        image = cv2.resize(image, (max(16, int(image.shape[1] * 0.8)),
                                   max(16, int(image.shape[0] * 0.8))))
    raise ValueError("Could not fit JPEG into receiver buffer")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("uart", "spi", "spi-emio"), default="uart")
    parser.add_argument("--port", help="A free UART, not the Linux console or instrument port")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--spi-device")
    parser.add_argument("--ready-path", help="Already configured input GPIO value file")
    parser.add_argument("--spi-speed", type=int, default=1000000)
    parser.add_argument("--spi-cs-high", action="store_true",
                        help="Diagnostic: invert controller CS polarity; spi-emio only")
    parser.add_argument('--spi-frame-poll', action='store_true',
                        help='SPI token firmware v3: poll ACK only at frame end, keep even transfer count')
    parser.add_argument('--spi-set-speed', action='store_true',
                        help='Also configure and read back the spidev max-speed setting')
    parser.add_argument('--pipeline', action='store_true',
                        help='Prepare one native JPEG during the current SPI/UART send; no frame queue')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", type=Path)
    source.add_argument("--camera", help="OpenCV camera index or video device")
    source.add_argument("--native-stream", type=Path, help="Persistent native camera executable (Linux)")
    source.add_argument('--native-jpeg-stream', type=Path, help='Persistent capture with in-process JPEG encoder')
    source.add_argument("--capture-command", nargs=argparse.REMAINDER,
                        help="Last option: trusted command argv including flags; must write --capture-file; no shell")
    parser.add_argument("--capture-file", type=Path)
    parser.add_argument("--capture-timeout", type=float, default=15)
    parser.add_argument("--count", type=int, default=1, help="0 means continuous")
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument('--log-every', type=int, default=1,
                        help='Print first/final frame and every Nth ACK; all frames still checked')
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--width", type=int, default=480)
    parser.add_argument("--quality", type=int, default=60)
    parser.add_argument("--encoder", choices=("opencv", "pillow", "native"), default="opencv",
                        help="File/PPM conversion backend; pillow avoids importing cv2")
    parser.add_argument("--jpeg-tool", type=Path, help="Native P6 PPM to JPEG executable")
    parser.add_argument("--camera-width", type=int, default=640)
    parser.add_argument("--camera-height", type=int, default=480)
    args = parser.parse_args()
    if args.count < 0 or args.interval < 0 or args.timeout <= 0 or args.baud <= 0 or args.log_every <= 0:
        parser.error("Invalid count, interval, timeout or baud")
    if args.capture_timeout <= 0:
        parser.error("capture-timeout must be positive")
    if not 16 <= args.width <= 8192 or not 10 <= args.quality <= 95:
        parser.error('width 16..8192 and quality 10..95 required')
    if args.capture_command and not args.capture_file:
        parser.error("--capture-command requires --capture-file")
    if args.transport == "uart" and not args.port:
        parser.error("--port is required for UART")
    if args.spi_cs_high and args.transport != 'spi-emio':
        parser.error('--spi-cs-high requires --transport spi-emio')
    if args.spi_frame_poll and args.transport != 'spi-emio':
        parser.error('--spi-frame-poll requires --transport spi-emio')
    if args.spi_set_speed and args.transport != 'spi-emio':
        parser.error('--spi-set-speed requires --transport spi-emio')
    if args.native_jpeg_stream and args.width > 800:
        parser.error('--native-jpeg-stream width cannot exceed sensor width 800')
    if args.pipeline and (not args.native_jpeg_stream or args.interval != 0):
        parser.error('--pipeline requires --native-jpeg-stream and --interval 0')
    if args.transport in ("spi", "spi-emio") and not (args.spi_device and args.ready_path):
        parser.error("SPI requires --spi-device and --ready-path")
    from .transports import SpiLink, EmioSpiLink, UartLink
    link = None
    camera = None
    native_camera = None
    jpeg_camera = None
    native_directory = None
    try:
        if args.native_stream:
            from .persistent_capture import PersistentCapture
            native_camera = PersistentCapture(args.native_stream, args.capture_timeout)
            native_directory = tempfile.TemporaryDirectory(prefix='labmate_stream_')
        if args.native_jpeg_stream:
            from .persistent_capture import PersistentJpegCapture
            jpeg_camera = PersistentJpegCapture(args.native_jpeg_stream, args.capture_timeout,
                                                args.width, args.quality)
        if args.camera is not None:
            import cv2
            device = int(args.camera) if args.camera.isdigit() else args.camera
            camera = cv2.VideoCapture(device)
            if not camera.isOpened():
                raise RuntimeError("Camera could not open; use --image to test link first")
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, args.camera_width)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, args.camera_height)
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if args.transport == 'uart':
            link = UartLink(args.port, args.baud, args.timeout)
        elif args.transport == 'spi-emio':
            link = EmioSpiLink(args.spi_device, args.ready_path, args.spi_speed, args.timeout,
                               cs_high=args.spi_cs_high, frame_poll=args.spi_frame_poll,
                               set_speed=args.spi_set_speed)
        else:
            link = SpiLink(args.spi_device, args.ready_path, args.spi_speed, args.timeout)
        sequence = 1
        first_ack = None
        while args.count == 0 or sequence <= args.count:
            started = time.monotonic()
            native_timings = None
            if jpeg_camera is not None:
                jpeg, capture_ms, encode_ms = jpeg_camera.capture_jpeg()
                native_timings = (capture_ms, encode_ms)
                captured = time.monotonic()
            elif camera is not None:
                ok, image = camera.read()
                if not ok:
                    raise RuntimeError("Camera read failed")
                captured = time.monotonic()
                jpeg = encode_image(image, args.width, args.quality)
            else:
                path = args.image
                if native_camera is not None:
                    path = Path(native_directory.name) / 'frame.ppm'
                    native_camera.capture(path)
                if args.capture_command:
                    # Delete only the explicitly named output; never send an old capture.
                    try:
                        args.capture_file.unlink()
                    except FileNotFoundError:
                        pass
                    subprocess.run(args.capture_command, check=True, timeout=args.capture_timeout)
                    path = args.capture_file
                captured = time.monotonic()
                jpeg = encode_file(path, args.width, args.quality, args.encoder, args.jpeg_tool)
            encoded = time.monotonic()
            # One outstanding request overlaps the existing camera child with blocking SPI I/O.
            if args.pipeline and (args.count == 0 or sequence < args.count):
                jpeg_camera.request_jpeg()
            transactions_before = getattr(link, 'completed', 0)
            link.send(frame(jpeg, sequence), sequence)
            finished = time.monotonic()
            if first_ack is None:
                first_ack = finished
            period = max(args.interval, finished - started)
            capture_ms = ((captured - started) * 1000 if native_timings is None else native_timings[0])
            encode_ms = ((encoded - captured) * 1000 if native_timings is None else native_timings[1])
            report = {"status": "acknowledged", "sequence": sequence,
                              "bytes": len(jpeg), "transport": args.transport,
                              "elapsed_seconds": round(finished - started, 3),
                              "pipelined": args.pipeline,
                              "capture_ms": round(capture_ms, 1),
                              "encode_ms": round(encode_ms, 1),
                              "prepare_ms": round(max(0, (encoded - started) * 1000 - capture_ms - encode_ms), 1),
                              "send_ms": round((finished - encoded) * 1000, 1),
                              "spi_transactions": (getattr(link, 'completed', 0) - transactions_before
                                                   if args.transport == 'spi-emio' else None),
                              "estimated_fps": round(1 / period, 2) if period else None,
                              "measured_fps": (round((sequence - 1) / (finished - first_ack), 2)
                                               if sequence > 1 and finished > first_ack else None)}
            if sequence == 1 or sequence % args.log_every == 0 or sequence == args.count:
                print(json.dumps(report), flush=True)
            sequence += 1
            remaining = args.interval - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        if jpeg_camera is not None:
            jpeg_camera.close()
        if native_camera is not None:
            native_camera.close()
        if native_directory is not None:
            native_directory.cleanup()
        if camera is not None:
            camera.release()
        if link is not None:
            link.close()


if __name__ == "__main__":
    main()
