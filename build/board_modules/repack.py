"""Verify or package this board handoff using only Python's standard library."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'MANIFEST.sha256.json'
EXCLUDED = {'__pycache__', '.git', '.pio', 'runs', 'board_config', 'build', '.venv'}


def payload():
    return sorted(path for path in ROOT.rglob('*') if path.is_file()
                  and path.name != MANIFEST
                  and not any(part in EXCLUDED for part in path.relative_to(ROOT).parts)
                  and path.suffix not in ('.pyc', '.pyo', '.log', '.zip')
                  and path.relative_to(ROOT).as_posix() != 'c_vision_lite/assets/smoke_infer')


def inventory():
    return {p.relative_to(ROOT).as_posix(): {
        'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in payload()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    actual = inventory()
    manifest = ROOT / MANIFEST
    if args.verify:
        expected = json.loads(manifest.read_text(encoding='utf-8'))['files']
        if actual != expected:
            changed = sorted(k for k in set(actual) | set(expected) if actual.get(k) != expected.get(k))
            raise SystemExit('Checksum or file list mismatch: ' + ', '.join(changed))
        print('Verified {} files'.format(len(actual)))
        return
    manifest.write_text(json.dumps({'algorithm': 'sha256', 'files': actual},
                                  ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    target = ROOT.parent / (ROOT.name + '.zip')
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(payload() + [manifest]):
            name = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(ROOT.name + '/' + name, (2026, 11, 4, 0, 0, 0))
            info.create_system = 3
            mode = 0o755 if path.suffix == '.sh' or path.name.endswith('_armv7') else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise SystemExit('ZIP CRC validation failed')
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(digest + '  ' + target.name + '\n', encoding='ascii')
    print(json.dumps({'archive': str(target), 'files': len(actual) + 1,
                      'bytes': target.stat().st_size, 'sha256': digest}, indent=2))


if __name__ == '__main__':
    main()
