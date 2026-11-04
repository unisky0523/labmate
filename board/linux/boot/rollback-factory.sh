#!/bin/sh
set -eu
backup=/home/root/spi_boot_backup_20261104
python3 -c 'import hashlib,json,pathlib; p=pathlib.Path("/home/root/spi_boot_backup_20261104"); h=json.loads((p/"SHA256.json").read_text()); assert hashlib.sha256((p/"mtd3.bin").read_bytes()).hexdigest()==h["mtd3"]; assert (p/"mtd3.bin").stat().st_size==0x20000; assert "\"boot.scr\"" in pathlib.Path("/proc/mtd").read_text().splitlines()[4]; print("FACTORY_SCRIPT_BACKUP_VERIFIED")'
flashcp -v "$backup/mtd3.bin" /dev/mtd3
python3 -c 'import hashlib,pathlib; a=pathlib.Path("/home/root/spi_boot_backup_20261104/mtd3.bin").read_bytes(); b=pathlib.Path("/dev/mtd3").read_bytes(); assert hashlib.sha256(a).digest()==hashlib.sha256(b).digest(); p=pathlib.Path("/etc/rcS.d/S40labmate-spi"); p.unlink() if p.is_symlink() else None; print("FACTORY_SCRIPT_RESTORED_REBOOT_REQUIRED")'
sync
