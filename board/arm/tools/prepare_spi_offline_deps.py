"""Download the Ubuntu 18.04 amd64 native tools needed beside the existing SDK."""
import concurrent.futures
import hashlib
import json
import lzma
from pathlib import Path
import re
import time
import urllib.request


ROOT = Path(r'D:\fpga amd xinlx\work\spi_offline_deps_20261104')
INDEX = ROOT / 'indexes'
DEBS = ROOT / 'debs'
TARGETS = ['bc', 'bison', 'flex', 'libssl-dev', 'libelf-dev', 'zlib1g-dev',
           'u-boot-tools', 'device-tree-compiler', 'kmod', 'pkg-config']
# The established Ubuntu Qt build already has its system C/C++ compiler and libc.
# Do not stage a second libc in the isolated native-tool directory.
SYSTEM = {'libc6', 'libc-bin', 'libc6-dev', 'libc-dev-bin', 'linux-libc-dev',
          'libgcc1', 'libstdc++6', 'dpkg', 'debconf', 'debconf-2.0',
          'multiarch-support', 'install-info', 'ucf', 'perl', 'perl-base'}


def fetch(url, path, digest=None):
    if path.exists() and (digest is None or hashlib.sha256(path.read_bytes()).hexdigest() == digest):
        return path.read_bytes()
    for attempt in range(4):
        try:
            candidate = url
            if attempt >= 2 and 'security.ubuntu.com/ubuntu/' in url:
                candidate = url.replace('security.ubuntu.com', 'archive.ubuntu.com')
            request = urllib.request.Request(candidate, headers={'User-Agent': 'Labmate-SPI-build-kit/1.0'})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
            break
        except OSError:
            if attempt == 3:
                raise
            time.sleep(0.5 * (attempt + 1))
    if digest and hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError('SHA256 mismatch: ' + url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def release_hashes(text):
    result = {}
    in_sha = False
    for line in text.splitlines():
        if line == 'SHA256:':
            in_sha = True
        elif in_sha and not line.startswith(' '):
            break
        elif in_sha:
            digest, size, name = line.split()
            result[name] = digest
    return result


def paragraphs(text):
    for paragraph in text.split('\n\n'):
        fields = {}
        previous = None
        for line in paragraph.splitlines():
            if line.startswith(' ') and previous:
                fields[previous] += ' ' + line.strip()
            elif ': ' in line:
                previous, value = line.split(': ', 1)
                fields[previous] = value
        if 'Package' in fields:
            yield fields


def order(char):
    if char == '~':
        return -1
    if not char:
        return 0
    if char.isalpha():
        return ord(char)
    return ord(char) + 256


def revision_compare(left, right):
    li = ri = 0
    while li < len(left) or ri < len(right):
        while ((li < len(left) and not left[li].isdigit()) or
               (ri < len(right) and not right[ri].isdigit())):
            lc = left[li] if li < len(left) else ''
            rc = right[ri] if ri < len(right) else ''
            delta = order(lc) - order(rc)
            if delta:
                return 1 if delta > 0 else -1
            li += bool(lc)
            ri += bool(rc)
        while li < len(left) and left[li] == '0':
            li += 1
        while ri < len(right) and right[ri] == '0':
            ri += 1
        le, re_ = li, ri
        while le < len(left) and left[le].isdigit():
            le += 1
        while re_ < len(right) and right[re_].isdigit():
            re_ += 1
        if le - li != re_ - ri:
            return 1 if le - li > re_ - ri else -1
        if left[li:le] != right[ri:re_]:
            return 1 if left[li:le] > right[ri:re_] else -1
        li, ri = le, re_
    return 0


def version_compare(left, right):
    def split(version):
        epoch, sep, rest = version.partition(':')
        if not sep:
            epoch, rest = '0', version
        upstream, sep, revision = rest.rpartition('-')
        if not sep:
            upstream, revision = rest, '0'
        return int(epoch), upstream, revision
    le, lu, lr = split(left)
    re_, ru, rr = split(right)
    return ((le > re_) - (le < re_) or revision_compare(lu, ru) or revision_compare(lr, rr))


def main():
    INDEX.mkdir(parents=True, exist_ok=True)
    DEBS.mkdir(parents=True, exist_ok=True)
    available = {}
    origins = []
    for suite in ['bionic', 'bionic-updates', 'bionic-security']:
        base = ('https://security.ubuntu.com/ubuntu' if suite.endswith('security')
                else 'https://archive.ubuntu.com/ubuntu')
        release = fetch(base + '/dists/' + suite + '/Release', INDEX / (suite + '-Release'))
        hashes = release_hashes(release.decode('utf-8'))
        for component in ['main', 'universe']:
            relative = component + '/binary-amd64/Packages.xz'
            digest = hashes[relative]
            index_path = INDEX / (suite + '-' + component + '-Packages.xz')
            compressed = fetch(base + '/dists/' + suite + '/' + relative, index_path, digest)
            count = 0
            for fields in paragraphs(lzma.decompress(compressed).decode('utf-8')):
                count += 1
                name = fields['Package']
                previous = available.get(name)
                if previous is None or version_compare(fields['Version'], previous['Version']) > 0:
                    keep = {key: fields[key] for key in ['Package', 'Version', 'Architecture',
                            'Filename', 'SHA256', 'Size', 'Depends', 'Pre-Depends'] if key in fields}
                    keep['origin_base'] = base
                    available[name] = keep
            origins.append({'suite': suite, 'component': component,
                            'index_url': base + '/dists/' + suite + '/' + relative, 'sha256': digest})
            print('INDEX_READY:', suite, component, count, flush=True)

    selected = {}
    def add(name):
        if name in SYSTEM or name in selected:
            return
        fields = available[name]
        selected[name] = fields
        dependencies = ','.join(fields.get(key, '') for key in ['Pre-Depends', 'Depends'])
        for clause in dependencies.split(','):
            if not clause.strip():
                continue
            options = []
            for alternative in clause.split('|'):
                match = re.match(r'\s*([a-z0-9+.-]+)', alternative)
                if match:
                    options.append(match.group(1))
            choice = next((n for n in options if n in SYSTEM), None)
            if choice is None:
                choice = next((n for n in options if n in available), None)
            if choice is None:
                raise RuntimeError('Cannot resolve: ' + clause)
            add(choice)
    for name in TARGETS:
        add(name)
    total = sum(int(p['Size']) for p in selected.values())
    print('SELECTED:', len(selected), 'packages,', total, 'bytes', flush=True)
    for name in sorted(selected):
        print('PACKAGE:', name, selected[name]['Version'], flush=True)

    def download(fields):
        filename = Path(fields['Filename']).name
        fetch(fields['origin_base'] + '/' + fields['Filename'], DEBS / filename, fields['SHA256'])
        return filename
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for name in pool.map(download, [selected[n] for n in sorted(selected)]):
            print('DEB_READY:', name, flush=True)
    manifest = {'targets': TARGETS, 'system_prerequisites': sorted(SYSTEM),
                'indexes': origins, 'packages': [selected[n] for n in sorted(selected)]}
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('OFFLINE_DEPS_COMPLETE:', ROOT, flush=True)


if __name__ == '__main__':
    main()
