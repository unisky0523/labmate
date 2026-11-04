"""Install the proven SPI preview command into board Linux boot services."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


MARKER = '# LabMate camera autostart v1'
BASE = '/usr/local/lib/labmate-camera'
MANIFEST = '/etc/labmate-camera/installation.json'
UNIT = '/etc/systemd/system/labmate-camera.service'


def at(root, absolute):
    return root / absolute.lstrip('/')


def detect_backend(root):
    if at(root, '/run/systemd/system').is_dir():
        return 'systemd', ['/etc/systemd/system/multi-user.target.wants/labmate-camera.service']
    inittab = at(root, '/etc/inittab')
    text = inittab.read_text() if inittab.is_file() else ''
    lines = [line for line in text.splitlines() if not line.lstrip().startswith('#')]
    # SysV init must actually invoke the runlevel dispatcher, not merely have rc directories.
    if at(root, '/etc/init.d/rc').is_file() and any(
            re.search(r':(?:wait|once):.*?/etc/init\.d/rc\s+[0-6S]\b', line) for line in lines):
        links = []
        for level in (2, 3, 4, 5):
            if at(root, '/etc/rc{}.d'.format(level)).is_dir():
                links.append('/etc/rc{}.d/S99labmate-camera'.format(level))
        if not links:
            raise RuntimeError('SysV dispatcher found but no multi-user rc2..5.d directory exists')
        for level in (0, 1, 6):
            if at(root, '/etc/rc{}.d'.format(level)).is_dir():
                links.append('/etc/rc{}.d/K01labmate-camera'.format(level))
        return 'sysv', links
    rcs = at(root, '/etc/init.d/rcS')
    script = rcs.read_text() if rcs.is_file() else ''
    script = '\n'.join(line for line in script.splitlines() if not line.lstrip().startswith('#'))
    if any(':sysinit:' in line and '/etc/init.d/rcS' in line for line in lines) and re.search(
            r'/etc/init\.d/S(?:\?\?|\[[^\]]+\]\[[^\]]+\]|\*)\*?', script):
        return 'busybox', ['/etc/init.d/S99labmate-camera']
    raise RuntimeError('Boot mechanism not recognized; no boot files changed. '
                       'Inspect /proc/1/comm, /etc/inittab and /etc/init.d/rcS')


def boot_script(project, python):
    quote = shlex.quote
    return '''#!/bin/sh
{marker}
set -eu
ROOT={root}
trap 'exit 0' TERM INT
remaining=120
while test ! -f "$ROOT/c_camera_link/preview_service.py"; do
    if test "$remaining" -le 0; then echo "SD project unavailable: $ROOT" >&2; exit 1; fi
    sleep 1
    remaining=$((remaining - 1))
done
cd "$ROOT"
export PYTHONPATH="$ROOT/vendor:$ROOT${{PYTHONPATH:+:$PYTHONPATH}}"
exec {python} -B -m c_camera_link.preview_service _run \\
    --run-id "boot-$$" --entry emio_board --max-restarts 0 --startup-timeout 120 \\
    --state-dir /tmp/labmate_camera_service \\
    --spi-cs-high --preview --max-fps --count 0
'''.format(marker=MARKER, root=quote(str(project)), python=quote(python))


def service_unit():
    return '''{marker}
[Unit]
Description=LabMate camera SPI preview
After=local-fs.target

[Service]
Type=simple
ExecStart=/bin/sh {base}/boot.sh
StandardOutput=journal
StandardError=journal
KillMode=mixed
TimeoutStopSec=12
Restart=no

[Install]
WantedBy=multi-user.target
'''.format(marker=MARKER, base=BASE)


def install(root, project, python):
    backend, links = detect_backend(root)
    required = ('preview_service.py', 'emio_board.py', 'sender.py', 'native/camera_jpeg_stream_armv7')
    for name in required:
        if not (project / 'c_camera_link' / name).is_file():
            raise RuntimeError('Project file missing: {}'.format(name))
    manifest_path = at(root, MANIFEST)
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        if previous.get('backend') != backend or previous.get('project') != str(project):
            raise RuntimeError('Another camera boot installation exists; disable it before changing project/backend')
    files = {
        BASE + '/boot.sh': boot_script(project, python),
        BASE + '/control.sh': (Path(__file__).parent / 'boot_init.sh').read_text(),
    }
    if backend == 'systemd':
        files[UNIT] = service_unit()
    else:
        files['/etc/init.d/labmate-camera'] = files[BASE + '/control.sh']
    target = UNIT if backend == 'systemd' else '/etc/init.d/labmate-camera'
    # Reject collisions before writing anything; other boot scripts are never edited.
    for name in files:
        path = at(root, name)
        if path.is_symlink() or (path.exists() and MARKER not in path.read_text()):
            raise RuntimeError('Refusing to replace another file: {}'.format(name))
    for name in links:
        path = at(root, name)
        expected = os.path.relpath(target, str(Path(name).parent))
        if (path.exists() or path.is_symlink()) and not (
                path.is_symlink() and os.readlink(str(path)) == expected):
            raise RuntimeError('Refusing to replace another boot entry: {}'.format(name))
    for name, text in files.items():
        path = at(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.replace('\r\n', '\n'), encoding='utf-8')
        path.chmod(0o644 if name.endswith('.service') else 0o755)
    for name in links:
        path = at(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_symlink():
            path.symlink_to(os.path.relpath(target, str(Path(name).parent)))
    record = {'backend': backend, 'project': str(project), 'enabled': True, 'links': links,
              'files': list(files), 'state_dir': '/tmp/labmate_camera_service'}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(record, indent=2), encoding='utf-8')
    return record


def control(record, action):
    if record['backend'] == 'systemd':
        return subprocess.call(['systemctl', '--no-pager', action, 'labmate-camera.service'])
    return subprocess.call(['/bin/sh', BASE + '/control.sh', action])


def disable(root, record):
    target = UNIT if record['backend'] == 'systemd' else '/etc/init.d/labmate-camera'
    for name in record['links']:
        path = at(root, name)
        expected = os.path.relpath(target, str(Path(name).parent))
        if path.is_symlink() and os.readlink(str(path)) == expected:
            path.unlink()
    record['enabled'] = False
    at(root, MANIFEST).write_text(json.dumps(record, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'disable', 'start', 'stop', 'status'))
    args = parser.parse_args()
    if os.name != 'posix':
        parser.error('Run this command in the board Linux serial shell')
    if args.action != 'status' and os.geteuid() != 0:
        parser.error('Root is required to configure/control board startup')
    root = Path('/')
    try:
        if args.action == 'install':
            # Check the board's trimmed Python runtime before registering a boot hook.
            from . import preview_service
            import fcntl
            import threading
            record = install(root, Path(__file__).resolve().parent.parent, sys.executable)
            if record['backend'] == 'systemd':
                subprocess.run(['systemctl', 'daemon-reload'], check=True)
            print(json.dumps(record, indent=2))
            print('Boot enabled. Stop any manual preview before starting/rebooting.')
        else:
            record = json.loads(at(root, MANIFEST).read_text())
            if args.action == 'disable':
                result = control(record, 'stop')
                if result not in (0, 3):
                    raise RuntimeError('Stop failed; boot configuration retained')
                disable(root, record)
                if record['backend'] == 'systemd':
                    subprocess.run(['systemctl', 'daemon-reload'], check=True)
                print('Camera boot disabled; project files retained')
            else:
                print('Boot enabled: {}'.format(record['enabled']), flush=True)
                return control(record, args.action)
    except (OSError, ValueError, RuntimeError, ImportError, subprocess.CalledProcessError) as error:
        print('Camera autostart failed: {}'.format(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
