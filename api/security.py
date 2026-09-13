"""
api/security.py
Passwords, session tokens and rate limits. Pure helpers with no HTTP
in them, so each can be tested on its own.

Passwords are hashed with argon2id; the plain password is never
stored, logged or returned. A session token is 32 random bytes; the
database keeps only its SHA-256, so a copied database holds nothing a
client could present. Tokens expire after SESSION_DAYS of inactivity.
"""

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

SESSION_DAYS = 30
MIN_PASSWORD_LENGTH = 8

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:            # a malformed or foreign hash never verifies
        return False


def new_token() -> str:
    """A fresh opaque session token for a client to hold."""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """What the database stores for a token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(now: datetime | None = None) -> str:
    """The expiry an active session gets: SESSION_DAYS from now, ISO seconds."""
    return ((now or datetime.now()) + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")


class RateLimiter:
    """
    A sliding-window limit per key, in memory: `limit` hits per
    `window_seconds`. Enough for one backend process; a shared store
    can replace it later without changing the callers.
    """

    def __init__(self, limit: int = 10, window_seconds: int = 15 * 60):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        """Record a hit for `key` and say whether it is still within the limit."""
        now = time.time() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
