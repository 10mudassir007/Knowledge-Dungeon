"""Question history persistence: capped, atomic, thread-safe."""

import json
import os
import threading

from core.text import normalize_answer

HISTORY_LIMIT = 50


class HistoryStore:
    """Append-only history of asked questions, kept in a JSON file.

    The file holds at most `limit` entries (the most recent). Writes go to a
    temp file and are moved into place with os.replace, so a crash mid-write
    can never leave a half-written file behind.
    """

    def __init__(self, path: str, limit: int = HISTORY_LIMIT):
        self.path = path
        self.limit = limit
        self._lock = threading.Lock()

    def load(self) -> list:
        """Return stored entries; any unreadable/corrupt file reads as empty."""
        try:
            if not os.path.exists(self.path):
                return []
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def save(self, entries: list) -> None:
        """Atomically write `entries` (already capped) to disk."""
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        tmp_path = f"{self.path}.{os.getpid()}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(entries[-self.limit:], handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def append(self, entry: dict) -> list:
        """Append one entry, cap to the most recent `limit`, persist, return all."""
        with self._lock:
            entries = self.load()
            entries.append(entry)
            entries = entries[-self.limit:]
            self.save(entries)
            return entries

    def known_question_keys(self) -> set:
        """Normalized question texts already asked, for de-duplication."""
        return {
            normalize_answer(entry.get("question", ""))
            for entry in self.load()
            if isinstance(entry, dict)
        }
