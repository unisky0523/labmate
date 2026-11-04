"""Small status bridge for the existing RGB LCD UI.

The existing vendor UI can poll data/state/latest_status.json and render the
fields it needs. This keeps the B application independent from the UI toolkit.
"""

from datetime import datetime
import json
from pathlib import Path
import threading


ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "data" / "state"
STATUS_PATH = STATE_DIR / "latest_status.json"


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class StatusBus:
    def __init__(self, path=STATUS_PATH):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._state = {"state": "starting", "updated_at": now_iso()}

    def update(self, **fields):
        with self._lock:
            self._state.update(fields)
            self._state["updated_at"] = now_iso()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".json.tmp")
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(self._state, stream, ensure_ascii=False, indent=2, allow_nan=False)
            temporary.replace(self.path)

    def snapshot(self):
        with self._lock:
            return dict(self._state)


class ConsoleTee:
    def __init__(self, stream, status_bus):
        self.stream = stream
        self.status_bus = status_bus
        self.buffer = ""

    def write(self, text):
        text = str(text)
        self.stream.write(text)
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.strip()
            if line:
                self.status_bus.update(last_console_line=line)
        return len(text)

    def flush(self):
        self.stream.flush()
