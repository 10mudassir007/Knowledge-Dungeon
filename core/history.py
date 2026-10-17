"""Question history persistence: capped, atomic, thread-safe."""

import json
import logging
import os
import threading

from core.text import normalize_answer

HISTORY_LIMIT = 50

logger = logging.getLogger(__name__)


class HistoryStore:
    """Append-only history of asked questions, kept in a JSON file.

    The file holds at most `limit` entries (the most recent). Writes go to a
    temp file and are moved into place with os.replace, so a crash mid-write
    can never leave a half-written file behind. When the filesystem is not
    writable (serverless), history is kept in memory for the life of the
    process instead.
    """

    def __init__(self, path: str, limit: int = HISTORY_LIMIT):
        self.path = path
        self.limit = limit
        self._lock = threading.Lock()
        self._memory: list | None = None

    def load(self) -> list:
        """Return stored entries; any unreadable/corrupt file reads as empty."""
        if self._memory is not None:
            return list(self._memory)
        try:
            if not os.path.exists(self.path):
                return []
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def save(self, entries: list) -> None:
        """Atomically write `entries` (already capped). Never raises.

        A read-only filesystem must not take the game down, so failures are
        logged and the in-process mirror keeps serving history.
        """
        directory = os.path.dirname(self.path)
        tmp_path = f"{self.path}.{os.getpid()}.tmp"
        try:
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(entries[-self.limit:], handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.path)
        except OSError as exc:
            logger.warning("History persistence unavailable (%s); keeping it in memory.", exc)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    def append(self, entry: dict) -> list:
        """Append one entry, cap to the most recent `limit`, persist, return all."""
        with self._lock:
            entries = self.load()
            entries.append(entry)
            entries = entries[-self.limit:]
            self._memory = list(entries)
            self.save(entries)
            return entries

    def known_question_keys(self) -> set:
        """Normalized question texts already asked, for de-duplication."""
        return {
            normalize_answer(entry.get("question", ""))
            for entry in self.load()
            if isinstance(entry, dict)
        }
