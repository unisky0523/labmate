"""Freeze only the required Python sources from the user-selected ASR baseline."""
import hashlib
import json
from pathlib import Path
import shutil

workspace = Path(__file__).resolve().parents[1]
source = workspace / 'labmate_b_board_20261015(1)' / 'labmate_b_board_20261015'
target = workspace / 'work/labmate_ui/asr_runtime'
names = ('asr_cli asr_grammar asr_backend vosk_lite board_audio board_mic '
         'board_listen text_cli main wave chunk').split()
names = [name + '.py' for name in names] + ['PYTHON_STDLIB_LICENSE.txt', 'PYTHON_STDLIB_SOURCE.md']
target.mkdir(parents=True, exist_ok=True)
hashes = {}
for name in names:
    shutil.copy2(str(source / name), str(target / name))
    hashes[name] = hashlib.sha256((target / name).read_bytes()).hexdigest()
manifest = dict(source=str(source), files=hashes,
                asset_note='Reuse model/libvosk from /home/root/labmate_b_audio_test; do not copy its Python sources.')
(target / 'baseline.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Frozen %d baseline source/license files.' % len(names))
