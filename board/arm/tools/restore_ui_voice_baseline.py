"""Restore actual pre-records board ASR files from one upload backup cohort.

The receiver calls plan_restore before writing any update. No audio parameters
or locally selected recognition sources are substituted for the board backup.
"""
import hashlib
import os
from pathlib import Path
import shutil


VOICE_FILES = ['asr_adapter.py'] + [
    'asr_runtime/' + name + '.py' for name in
    'asr_backend asr_cli asr_grammar board_audio board_listen board_mic chunk main text_cli vosk_lite wave'.split()]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan_restore(target):
    target = Path(target).resolve()
    candidates = []
    for binary in target.glob('labassistant.bak.*'):
        data = binary.read_bytes()
        if not (data[:5] == b'\x7fELF\x01' and int.from_bytes(data[18:20], 'little') == 40
                and b'LABMATE_UI_ASR_V1' in data
                and b'LABMATE_UI_RECORDS_V2' not in data):
            continue
        stamp = binary.name.split('.bak.', 1)[1]
        try:
            order = tuple(int(part) for part in stamp.split('_'))
        except ValueError:
            continue
        if len(order) != 2:
            continue
        files = []
        for name in VOICE_FILES:
            destination = target / name
            source = target / (name + '.bak.' + stamp)
            if not source.is_file():
                break
            if target not in source.resolve().parents or target not in destination.resolve().parents:
                raise ValueError('Voice backup escapes the application directory')
            files.append((source, destination, digest(source)))
        else:
            candidates.append((order, stamp, files))
    if not candidates:
        raise ValueError('No complete pre-records ASR V1 backup found; no update files replaced')
    _, stamp, files = max(candidates, key=lambda item: item[0])
    return dict(stamp=stamp, files=files)


def apply_restore(plan, update_stamp):
    changed, backups = [], []
    for source, destination, expected in plan['files']:
        if digest(source) != expected:
            raise ValueError('Voice backup changed after preflight')
        if destination.exists() and digest(destination) == expected:
            continue
        changed.append((source, destination))
    try:
        for source, destination in changed:
            backup = destination.with_name(destination.name + '.before_voice_restore.' + update_stamp)
            if destination.exists():
                shutil.copy2(str(destination), str(backup))
                backups.append((backup, destination))
            else:
                backups.append((None, destination))
        for source, destination in changed:
            temporary = destination.with_name('.' + destination.name + '.voice_restore.' + update_stamp)
            try:
                shutil.copy2(str(source), str(temporary))
                os.replace(str(temporary), str(destination))
            finally:
                if temporary.exists():
                    temporary.unlink()
    except Exception:
        for backup, destination in reversed(backups):
            if backup is not None:
                shutil.copy2(str(backup), str(destination))
            elif destination.exists():
                destination.unlink()
        raise
    print('VOICE_BASELINE %s: restored %d files from actual board backup; preserved original backup files.'
          % (plan['stamp'], len(changed)), flush=True)
    if not changed:
        print('VOICE_BASELINE_IDENTICAL: current ASR already matches the pre-records backup.', flush=True)
