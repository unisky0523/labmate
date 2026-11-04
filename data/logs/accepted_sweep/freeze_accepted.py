"""Freeze the user-accepted version without restarting audio or operating USB."""
from datetime import datetime, timezone
import glob
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile

root=Path('/home/root/labmate_ui_test')
release='labmate_ui_voice_sweep_20261103_v1'
parent=root.parent/'labmate_releases'
target=parent/release
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def atomic(p,data):
    tmp=p.with_name(p.name+'.freeze_tmp')
    with tmp.open('wb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(str(tmp),str(p))
assert sha(root/'labassistant')=='37b47558efc29e484cb9db575719f6cbff73af3869c9b011fa81ae0cc921bfff'
calibration=json.loads((root/'data/audio_diagnostics/voice_calibration.json').read_text())
assert calibration['success'] is True and calibration['channel'] in (0,1)
assert calibration['profile']['byte_order'] in ('little','msb-first')
assert b'LABMATE_DESKTOP_ENTRY_V1' in Path('/opt/qt5/QMainApp').read_bytes()
assert sha(root/'QMainApp')==sha(Path('/opt/qt5/QMainApp'))
assert '/home/root/labmate_ui_test/run_ui_instruments.sh' in (root/'run_ui_desktop.sh').read_text()
assert 'LABMATE_ASR_ROOT=/home/root/labmate_ui_test/asr_runtime' in (root/'run_ui_voice.sh').read_text()
mounts=[]
for line in Path('/proc/mounts').read_text().splitlines():
    dev,mnt,kind=line.split()[:3]
    if str(root).startswith(mnt.rstrip('/')+'/'):
        mounts.append((len(mnt),dev,mnt,kind))
mount=max(mounts)
assert mount[3] not in ('tmpfs','ramfs','nfs','nfs4')
files={};links={}
for p in root.rglob('*'):
    n=p.relative_to(root).as_posix()
    if any(x in p.parts for x in ('__pycache__','backups')) or any(x in n for x in ('.bak.','.before_','.incoming.','.restore_tmp')):
        continue
    if n=='RELEASE.json' or n.startswith('RELEASE.') or p.suffix in ('.pyc','.log'):
        continue
    if n.startswith('data/') and not (n.startswith('data/records/') or n=='data/audio_diagnostics/voice_calibration.json'
            or n.startswith('data/instrument_jobs/generator/template_ch')):
        continue
    if p.is_symlink(): links[n]=os.readlink(str(p))
    elif p.is_file(): files[n]=sha(p)
fingerprint=hashlib.sha256(json.dumps(dict(files=files,links=links),sort_keys=True).encode()).hexdigest()
manifest=dict(release=release,status='frozen',date='2026-11-03',accepted_at=datetime.now(timezone.utc).isoformat(),
    fingerprint=fingerprint,files=files,symlinks=links,app_directory=str(root),
    launcher=str(root/'run_ui_desktop.sh'),desktop_entry='/opt/qt5/QMainApp',
    storage=dict(device=mount[1],mount=mount[2],filesystem=mount[3]),
    voice=dict(accepted_by_user=True,source_unchanged=True,channel=calibration['channel'],calibration_sha256=files['data/audio_diagnostics/voice_calibration.json']),
    verification=dict(local_tests=181,voice='user accepted after calibration restore',
                      sweep_curve='deployed; live curve acceptance not yet recorded',fpga_fft='pending'),
    history_files=sum(n.startswith('data/records/') for n in files),
    dependencies=dict(voice_assets='/home/root/labmate_b_audio_test',scope='/media/sd-mmcblk0p1/labmate_sds1202x_board',
                      meter='/media/sd-mmcblk0p1/labmate_sa5041_board'),
    boot_entries=glob.glob('/etc/rc*.d/*qtGUI*'))
if not target.exists():
    stage=Path(tempfile.mkdtemp(prefix=release+'.',dir=str(parent)))
    for name,h in files.items():
        dst=stage/name;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(str(root/name),str(dst));assert sha(dst)==h
    for name,link in links.items():
        dst=stage/name;dst.parent.mkdir(parents=True,exist_ok=True);os.symlink(link,str(dst))
    (stage/'RELEASE.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    os.rename(str(stage),str(target))
else:
    old=json.loads((target/'RELEASE.json').read_text())
    assert old['fingerprint']==fingerprint,'Existing accepted backup differs; kept intact'
    manifest=old
archive=parent/(release+'.tar.gz')
if not archive.exists():
    tmp=archive.with_name(archive.name+'.tmp')
    with tarfile.open(str(tmp),'w:gz') as out: out.add(str(target),arcname=release)
    with tarfile.open(str(tmp),'r:gz') as check: assert check.getmember(release+'/RELEASE.json').isfile()
    os.replace(str(tmp),str(archive))
assert all(sha(root/n)==h for n,h in files.items()),'Files changed during snapshot'
atomic(root/'RELEASE.json',(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())
atomic(parent/'CURRENT',(release+'\n').encode())
report=dict(release=release,program_files=len(files),history_files=manifest['history_files'],
            backup=str(archive),backup_bytes=archive.stat().st_size,backup_sha256=sha(archive),
            fingerprint=fingerprint,storage=manifest['storage'],voice=manifest['voice'],boot_entries=manifest['boot_entries'])
atomic(root/'data/frozen_sweep_report.json',(json.dumps(report,indent=2)+'\n').encode())
os.sync()
print('__SWEEP_FROZEN__'+json.dumps(report),flush=True)
