#!/usr/bin/env python3
"""Verify every retained kernel source file without extracting it to disk."""
import hashlib
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'build/kernel_source_manifest.json').read_text(encoding='utf-8'))
expected={r['path']:r for r in manifest['files']}
seen=set();errors=[]
with tarfile.open(ROOT/'src/linux/kernel/atk-zynq-linux-xlnx.tar.xz',mode='r|xz') as archive:
    for member in archive:
        if not member.isfile():continue
        h=hashlib.sha256()
        with archive.extractfile(member) as source:
            for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
        record=expected.get(member.name)
        if not record or record['sha256']!=h.hexdigest() or record['bytes']!=member.size:
            errors.append(member.name)
        seen.add(member.name)
errors.extend(sorted(set(expected)-seen))
print(json.dumps({'passed':not errors,'retained_source_files':len(seen),'errors':errors},indent=2))
raise SystemExit(0 if not errors else 1)
