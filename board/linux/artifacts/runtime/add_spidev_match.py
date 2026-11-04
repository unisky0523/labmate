#!/usr/bin/env python3
"""Add our real peripheral compatible to the matching kernel source; then rebuild spidev."""
from pathlib import Path
import sys
p = Path(sys.argv[1]) / "drivers/spi/spidev.c"
s = p.read_text()
anchor = "static const struct of_device_id spidev_dt_ids[] = {"
line = '\n\t{ .compatible = "labmate,esp32-image-link" },'
if '"labmate,esp32-image-link"' in s:
    print("Already present")
else:
    if s.count(anchor) != 1:
        raise SystemExit("Expected spidev_dt_ids table not found; inspect this kernel version manually")
    p.with_suffix(".c.labmate-backup").write_text(s)
    p.write_text(s.replace(anchor, anchor + line, 1))
    print("Added DT match; rebuild and install spidev for the board's running kernel")
