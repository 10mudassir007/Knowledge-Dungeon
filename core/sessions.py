"""In-memory session store with a TTL and a lock around every access."""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from core.rules import GameState, new_state

SESSION_TTL_SECONDS = 2 * 60 * 60


@dataclass
class ActiveQuestion:
    """The one question a session may currently answer."""

    question: str
    answer: str
    accepted_alternatives: list = field(default_factory=list)
    asked_at: float = 0.0


@dataclass
class Session:
    session_id: str
    age: int
    interest: str
    state: GameState
    current: Optional[ActiveQuestion] = None
    history: list = field(default_factory=list)
    # Serializes "check current -> generate -> store" so two requests racing
    # on the same session cannot both generate (and replace) a question.
    question_lock: threading.Lock = field(default_factory=threading.Lock)
    created_at: float = 0.0
    last_seen: float = 0.0


class SessionStore:
    """Sessions live in memory only and are dropped after `ttl_seconds` idle.

    Expired sessions are evicted on every access, and a single lock guards all
    reads and writes.
    """

    def __init__(self, ttl_seconds: int = SESSION_TTL_SECONDS, time_func=time.time):
        self.ttl_seconds = ttl_seconds
        self._time = time_func
        self._sessions: dict = {}
        self._lock = threading.Lock()

    def create(self, age: int, interest: str) -> Session:
        now = self._time()
        session = Session(
            session_id=str(uuid.uuid4()),
            age=age,
            interest=interest,
            state=new_state(),
            created_at=now,
            last_seen=now,
        )
        with self._lock:
            self._evict_expired_locked(now)
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        """Return a live session, or None if unknown or expired. Marks it seen."""
        now = self._time()
        with self._lock:
            self._evict_expired_locked(now)
            session = self._sessions.get(session_id)
            if session is not None:
                session.last_seen = now
            return session

    def active_count(self) -> int:
        now = self._time()
        with self._lock:
            self._evict_expired_locked(now)
            return len(self._sessions)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def _evict_expired_locked(self, now: float) -> int:
        expired = [
            sid
            for sid, session in self._sessions.items()
            if now - session.last_seen > self.ttl_seconds
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)
