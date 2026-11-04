"""Install the staged factory desktop with a verified original and rollback."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path('/home/root/labmate_ui_test')
DESKTOP = Path('/opt/qt5/QMainApp')
BACKUP = ROOT/'backups/desktop_entry_20261102'
ORIGINAL_SHA256 = 'fe2daff8aabba8ef5b8f85ac6839f2bc3ab0a3cbe9fd0056255ffe0395642373'
MARKER = b'LABMATE_DESKTOP_ENTRY_V1'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_sync(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o755)


def replace_file(path, data):
    temporary = path.with_name('.' + path.name + '.labmate.' + str(os.getpid()))
    write_sync(temporary, data)
    try:
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def install(root=ROOT, desktop=DESKTOP, backup=BACKUP, original_sha256=ORIGINAL_SHA256):
    binary = (root/'QMainApp').read_bytes()
    if (binary[:5] != b'\x7fELF\x01' or int.from_bytes(binary[18:20], 'little') != 40
            or MARKER not in binary):
        raise RuntimeError('Expected ARM desktop-entry binary')
    for name in ('run_ui_desktop.sh', 'run_ui_instruments.sh', 'run_ui_voice.sh', 'run_ui_test.sh'):
        if not (root/name).is_file():
            raise RuntimeError('Missing launcher: ' + name)
    if b'LABMATE_DESKTOP_CHILD' not in (root/'run_ui_test.sh').read_bytes():
        raise RuntimeError('Desktop child launch must not stop its parent')
    current = desktop.read_bytes()
    if digest(current) not in (original_sha256, digest(binary)):
        raise RuntimeError('Unexpected current factory desktop; left unchanged')
    backup.mkdir(parents=True, exist_ok=True)
    original = backup/'QMainApp.original'
    if original.exists():
        if digest(original.read_bytes()) != original_sha256:
            raise RuntimeError('Original desktop backup failed verification')
    elif digest(current) == original_sha256:
        write_sync(original, current)
    else:
        raise RuntimeError('Original desktop backup is missing')
    replace_file(desktop, binary)
    report = dict(original_sha256=original_sha256, installed_sha256=digest(binary),
                  desktop=str(desktop), backup=str(original))
    (backup/'install.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def rollback(desktop=DESKTOP, backup=BACKUP):
    report = json.loads((backup/'install.json').read_text(encoding='utf-8'))
    original = (backup/'QMainApp.original').read_bytes()
    if digest(original) != report['original_sha256']:
        raise RuntimeError('Original desktop backup failed verification')
    if digest(desktop.read_bytes()) != report['installed_sha256']:
        raise RuntimeError('Current desktop differs from this installation')
    replace_file(desktop, original)
    return report


if __name__ == '__main__':
    import sys
    result = rollback() if sys.argv[1:] == ['--rollback'] else install()
    print('__LM_DESKTOP_INSTALLED__=' + json.dumps(result), flush=True)
