#!/usr/bin/env python3
"""Fetch the pinned public Vosk model into an external prepared workspace."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',required=True)
    p.add_argument('--model-archive',help='Optional already downloaded official model ZIP')
    p.add_argument('--from-full',help='Optional original full LabMate directory; reuse its model without network')
    a=p.parse_args()
    workspace=Path(a.workspace).expanduser().resolve()
    try:workspace.relative_to(ROOT)
    except ValueError:pass
    else:p.error('Choose a workspace outside the submission directory.')
    manifest=json.loads((ROOT/'data/dependencies/vosk_model_manifest.json').read_text(encoding='utf-8'))
    target=workspace/'arm/assets/voice/models'
    target.mkdir(parents=True,exist_ok=True)
    entries=manifest['files']
    for entry in entries:
        rel=PurePosixPath(entry['path'])
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('Unsafe model path')
    existing=all((target/e['path']).is_file() and digest(target/e['path'])==e['sha256'] for e in entries)
    if existing:
        print('MODEL_VERIFIED {} files: {}'.format(len(entries),target/manifest['model']))
        return
    temporary=Path(tempfile.mkdtemp(prefix='model_stage_',dir=str(workspace)))
    try:
        if a.from_full:
            full=Path(a.from_full).expanduser().resolve()
            for entry in entries:
                dst=temporary/entry['path'];dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(full/entry['packaged_full'],dst)
        else:
            archive=Path(a.model_archive).resolve() if a.model_archive else temporary/'model.zip'
            if not a.model_archive:
                print('Downloading pinned model from '+manifest['url'],flush=True)
                with urllib.request.urlopen(manifest['url'],timeout=60) as source,archive.open('wb') as destination:
                    shutil.copyfileobj(source,destination)
            with zipfile.ZipFile(archive) as source:
                for entry in entries:
                    dst=temporary/entry['path'];dst.parent.mkdir(parents=True,exist_ok=True)
                    with source.open(entry['path']) as data,dst.open('wb') as output:shutil.copyfileobj(data,output)
        for entry in entries:
            if digest(temporary/entry['path'])!=entry['sha256']:
                raise ValueError('Downloaded model differs from the recorded version: '+entry['path'])
        for entry in entries:
            dst=target/entry['path']
            if dst.exists() and digest(dst)!=entry['sha256']:
                raise ValueError('Different existing model file preserved: '+str(dst))
        for entry in entries:
            dst=target/entry['path'];dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(temporary/entry['path'],dst)
        print('MODEL_VERIFIED {} files: {}'.format(len(entries),target/manifest['model']))
    finally:
        # This known, newly created staging directory is confined to the explicit workspace.
        if temporary.resolve().parent!=workspace:raise ValueError('Unsafe temporary cleanup target')
        shutil.rmtree(str(temporary))


if __name__=='__main__':main()
