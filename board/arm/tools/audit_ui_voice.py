"""Read board files and launch settings; never import ASR or open audio devices."""
import hashlib
import re
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(root, expected):
    root = Path(root)
    print('__LM_VOICE_AUDIT_START__', flush=True)
    print('READ_ONLY_ROOT', root, flush=True)
    for group in ('voice', 'records'):
        matched = 0
        for name, wanted in sorted(expected[group].items()):
            path = root / name
            actual = digest(path) if path.is_file() else 'MISSING'
            if actual == wanted:
                matched += 1
            else:
                print('DIFFERENT', name, 'board=' + actual, 'expected=' + wanted, flush=True)
        print('%s_MATCH %d/%d' % (group.upper(), matched, len(expected[group])), flush=True)

    binary = root / 'labassistant'
    if binary.is_file():
        data = binary.read_bytes()
        marker = ('RECORDS_V2' if b'LABMATE_UI_RECORDS_V2' in data else
                  'ASR_V1' if b'LABMATE_UI_ASR_V1' in data else 'UNKNOWN')
        print('GUI', marker, 'same_as_windows=' + str(hashlib.sha256(data).hexdigest() == expected['gui']), flush=True)
    else:
        print('GUI MISSING', flush=True)

    launcher = root / 'run_ui_voice.sh'
    if launcher.is_file():
        for line in launcher.read_text(encoding='utf-8', errors='replace').splitlines():
            if re.match(r'\s*(?:export\s+)?LABMATE_(?:ASR_ROOT|BACKEND|MODEL_PATH)=', line):
                print('LAUNCH', line.strip(), flush=True)
    for name in ('asr_adapter.py', 'asr_runtime/board_listen.py', 'asr_runtime/board_mic.py'):
        print('SOURCE', name, '->', (root / name).resolve(), flush=True)

    # Show what each actual upload backup contains, without choosing or restoring it.
    cohorts = []
    for path in root.glob('labassistant.bak.*'):
        stamp = path.name.split('.bak.', 1)[1]
        if re.fullmatch(r'[0-9]+_[0-9]+', stamp):
            cohorts.append((tuple(map(int, stamp.split('_'))), stamp, path))
    for _, stamp, path in sorted(cohorts, reverse=True)[:8]:
        data = path.read_bytes()
        if b'LABMATE_UI_ASR_V1' not in data or b'LABMATE_UI_RECORDS_V2' in data:
            continue
        present = matches = 0
        for name, wanted in expected.get('original_voice', expected['voice']).items():
            backup = root / (name + '.bak.' + stamp)
            if backup.is_file():
                present += 1
                matches += digest(backup) == wanted
        print('V1_BACKUP', stamp, 'files=%d/%d original_matches=%d/%d' % (
            present, len(expected['voice']), matches, len(expected['voice'])), flush=True)

    log = root / 'run.log'
    if log.is_file():
        print('RUN_LOG_TAIL', flush=True)
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size - 4096))
            tail = stream.read().decode('utf-8', 'replace').splitlines()[-20:]
        for line in tail:
            print('LOG', line, flush=True)
    print('__LM_VOICE_AUDIT_END__', flush=True)
