"""Linux preview process control with bounded restart and observable status."""

import argparse
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding='utf-8')
    temporary.replace(path)


def read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def matches(state):
    try:
        arguments = Path('/proc/{}/cmdline'.format(int(state['pid']))).read_bytes().split(b'\0')
        return (b'c_camera_link.preview_service' in arguments and
                state['run_id'].encode() in arguments and b'_run' in arguments)
    except (OSError, KeyError, ValueError):
        return False


def preflight(options, entry='native_preview', startup_timeout=0, stopping=lambda: False):
    if entry == 'emio_board':
        from .emio_board import discover_spi, discover_ready
        program = Path(__file__).parent / 'native/camera_jpeg_stream_armv7'
        if not program.is_file() or not os.access(str(program), os.X_OK):
            raise RuntimeError('Executable missing/not executable: {}'.format(program))
        deadline = time.monotonic() + startup_timeout
        while not stopping():
            try:
                if not all(Path(p).exists() for p in ('/dev/video0', '/dev/v4l-subdev0')):
                    raise RuntimeError('Waiting for camera video/subdev nodes')
                discover_spi()
                if Path(discover_ready()).read_text().strip() != '1':
                    raise RuntimeError('Waiting for ESP32 initial READY=1')
                return program
            except (OSError, RuntimeError) as error:
                if time.monotonic() >= deadline:
                    raise RuntimeError('SPI preview startup not ready: {}'.format(error))
                time.sleep(.5)
        return None
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--program', type=Path)
    parser.add_argument('--legacy-capture', action='store_true')
    parser.add_argument('--transport', choices=('uart', 'spi'), default='uart')
    parser.add_argument('--port')
    args, _ = parser.parse_known_args(options)
    if args.legacy_capture and args.program is None:
        raise RuntimeError('--legacy-capture requires --program')
    program = (args.program.resolve(strict=True) if args.legacy_capture else
               Path(__file__).parent / 'native/camera_stream_armv7')
    tool = Path(__file__).parent / 'native/ppm_to_jpeg_armv7'
    for path in (program, tool):
        if not path.is_file() or not os.access(str(path), os.X_OK):
            raise RuntimeError('Executable missing/not executable: {}'.format(path))
    if args.transport == 'uart':
        if not args.port:
            raise RuntimeError('--port required')
        port = Path(args.port).resolve(strict=True)
        for argument in Path('/proc/cmdline').read_text().split():
            if argument.startswith('console='):
                console = argument.split('=', 1)[1].split(',', 1)[0]
                if port == (Path('/dev') / console).resolve():
                    raise RuntimeError('Refusing Linux console port: {}'.format(port))
    return program


def supervise(args, options):
    import fcntl
    args.state_dir.mkdir(parents=True, exist_ok=True)
    lock = (args.state_dir / 'lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError('Preview service already running in this state directory')
    status_path = args.state_dir / 'status.json'
    logger = logging.Logger('preview', level=logging.INFO)
    handler = RotatingFileHandler(str(args.state_dir / 'preview.log'), maxBytes=262144,
                                  backupCount=2, encoding='utf-8')
    logger.addHandler(handler)
    status = {'pid': os.getpid(), 'run_id': args.run_id, 'status': 'starting',
              'attempt': 0, 'acknowledged_frames': 0, 'last_ack': None}
    child = None
    stopping = False

    def publish(**values):
        status.update(values)
        status['updated_at'] = datetime.now(timezone.utc).isoformat()
        save(status_path, status)

    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    publish()
    try:
        entry = getattr(args, 'entry', 'native_preview')
        preflight(options, entry, getattr(args, 'startup_timeout', 0), lambda: stopping)
        for attempt in range(args.max_restarts + 1):
            if stopping:
                break
            publish(status='starting', attempt=attempt + 1)
            child = subprocess.Popen([sys.executable, '-B', '-m', 'c_camera_link.' + entry,
                                      '--count', '0'] + options,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     universal_newlines=True, bufsize=1, start_new_session=True)
            # A timer also kills descendants if native capture ignores SIGTERM.
            import threading
            done = threading.Event()
            def reap_stopped(process):
                while not done.wait(.2):
                    if stopping:
                        if not done.wait(3):
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        return
            watcher = threading.Thread(target=reap_stopped, args=(child,), daemon=True)
            watcher.start()
            last_sequence = 0
            try:
                for line in child.stdout:
                    logger.info(line.rstrip()[:4096])
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(event, dict) and event.get('status') == 'acknowledged':
                        sequence = event.get('sequence', last_sequence + 1)
                        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence <= last_sequence:
                            sequence = last_sequence + 1
                        publish(status='streaming', acknowledged_frames=status['acknowledged_frames'] + sequence - last_sequence,
                                last_ack=datetime.now(timezone.utc).isoformat(), last_frame=event)
                        last_sequence = sequence
                exit_code = child.wait()
            finally:
                done.set()
                watcher.join(timeout=4)
                child.stdout.close()
                # Do not leave native descendants after timeout/failure of the Python worker.
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child = None
            if stopping:
                break
            if exit_code == 0:
                publish(status='complete', exit_code=0)
                return
            publish(status='retry_wait' if attempt < args.max_restarts else 'failed', exit_code=exit_code)
            if attempt < args.max_restarts:
                # Receiver abandons partial UART frames after >2s idle; wait before restarting.
                deadline = time.monotonic() + args.retry_delay
                while not stopping and time.monotonic() < deadline:
                    time.sleep(.1)
        if stopping:
            publish(status='stopped')
    except Exception as error:
        publish(status='failed', detail=str(error))
        raise
    finally:
        handler.close()
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'stop', 'status', '_run'))
    parser.add_argument('--state-dir', type=Path, default=Path('/tmp/labmate_camera_service'))
    parser.add_argument('--max-restarts', type=int, default=5)
    parser.add_argument('--retry-delay', type=float, default=4)
    parser.add_argument('--run-id')
    parser.add_argument('--entry', choices=('native_preview', 'emio_board'), default='native_preview')
    parser.add_argument('--startup-timeout', type=float, default=0)
    args, options = parser.parse_known_args()
    if os.name != 'posix':
        parser.error('Process control requires board Linux; use native_preview directly on other systems')
    if args.max_restarts < 0 or args.retry_delay < 3:
        parser.error('max-restarts >= 0 and retry-delay >= 3 required')
    if args.startup_timeout < 0:
        parser.error('startup-timeout must be nonnegative')
    if args.entry == 'emio_board' and args.max_restarts != 0:
        parser.error('SPI token transport requires --max-restarts 0; reset ESP32 after an interrupted transfer')
    args.state_dir = args.state_dir.resolve()
    path = args.state_dir / 'status.json'
    if args.action == '_run':
        if not args.run_id:
            parser.error('Missing internal run ID')
        supervise(args, options)
        return
    state = read(path)
    if args.action == 'status':
        state['running'] = matches(state)
        if state.get('last_ack'):
            state['last_ack_age_seconds'] = max(0, round((datetime.now(timezone.utc) -
                                                datetime.fromisoformat(state['last_ack'])).total_seconds(), 1))
        if not state['running'] and state.get('status') in ('starting', 'streaming', 'retry_wait'):
            state['status'] = 'exited'
        print(json.dumps(state, indent=2))
        return
    if args.action == 'stop':
        if matches(state):
            os.kill(int(state['pid']), signal.SIGTERM)
            deadline = time.monotonic() + 8
            while matches(state) and time.monotonic() < deadline:
                time.sleep(.1)
            if matches(state):
                raise RuntimeError('Stop not confirmed; inspect preview.log')
        print(json.dumps({'status': 'stopped'}))
        return
    if matches(state):
        raise RuntimeError('Preview is already running; stop it before starting again')
    preflight(options, args.entry)
    args.state_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    command = [sys.executable, '-B', '-m', 'c_camera_link.preview_service', '_run',
               '--state-dir', str(args.state_dir), '--run-id', run_id,
               '--max-restarts', str(args.max_restarts), '--retry-delay', str(args.retry_delay),
               '--entry', args.entry, '--startup-timeout', str(args.startup_timeout)] + options
    with (args.state_dir / 'launcher.log').open('wb') as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   start_new_session=True)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        state = read(path)
        if state.get('run_id') == run_id:
            if state.get('status') == 'failed':
                raise RuntimeError(state.get('detail', 'Startup failed; inspect preview.log'))
            print(json.dumps({'status': 'started', 'pid': process.pid, 'state_dir': str(args.state_dir)}))
            return
        if process.poll() is not None:
            raise RuntimeError('Preview exited during startup; inspect preview.log')
        time.sleep(.1)
    raise RuntimeError('Startup confirmation timed out; inspect status before retrying')


if __name__ == '__main__':
    main()
