#!/usr/bin/env python3
"""Board Python 3.7 wrapper; preserve native log and PPM even if PNG fails."""
import argparse
import json
import os
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--capture-only', action='store_true')
    modes.add_argument('--autofocus', action='store_true')
    args = parser.parse_args()
    base = os.path.dirname(os.path.abspath(__file__))
    run = tempfile.mkdtemp(prefix='af_run_' + time.strftime('%Y%m%d_%H%M%S_'), dir=base)
    mode = '--autofocus' if args.autofocus else '--capture-only'
    print('OUTPUT=' + run, flush=True)
    for path in ('/sys/class/i2c-adapter/i2c-2/name', '/sys/bus/i2c/devices/2-003c/name'):
        try:
            with open(path) as source:
                print(path + '=' + source.read().strip(), flush=True)
        except OSError as exc:
            print('INFO: ' + str(exc), flush=True)
    binary = os.path.join(base, 'af_capture')
    os.chmod(binary, 0o755)
    with open(os.path.join(run, 'native.log'), 'w') as log:
        try:
            proc = subprocess.Popen([binary, mode], cwd=run, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, universal_newlines=True)
            try:
                for line in proc.stdout:
                    print(line, end='', flush=True)
                    log.write(line)
                    log.flush()
                code = proc.wait(timeout=5)
            except BaseException:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise
        except OSError as exc:
            log.write(str(exc) + '\n')
            raise
    report = {'mode': mode, 'native_exit': code, 'images': {}}
    if code:
        try:
            kernel = subprocess.check_output(['dmesg'], universal_newlines=True, timeout=5)
            tail = '\n'.join(kernel.splitlines()[-60:]) + '\n'
            with open(os.path.join(run, 'dmesg_tail.txt'), 'w') as output:
                output.write(tail)
            print('DMESG_LOG=' + os.path.join(run, 'dmesg_tail.txt'), flush=True)
        except (OSError, subprocess.SubprocessError) as exc:
            print('INFO: cannot collect dmesg: ' + str(exc), flush=True)
    # Convert in a separate process: a cv2 crash cannot erase the native report.
    conversion = subprocess.call(['python3', os.path.join(base, 'convert_images.py'), run])
    report['conversion_exit'] = conversion
    with open(os.path.join(run, 'report.json'), 'w') as output:
        json.dump(report, output, indent=2)
    print('OUTPUT=' + run)
    print('NATIVE_EXIT=' + str(code))
    return code if code else conversion


if __name__ == '__main__':
    raise SystemExit(main())
