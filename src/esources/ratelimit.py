"""Login-attempt throttling, backed by Firestore.

Cloud Run scales to multiple stateless instances, so an in-memory counter
would not hold. A small `login_attempts` collection gives every instance a
shared view.

Each library-card login POST is counted against two keys — the client IP and
the submitted barcode — so neither a single noisy IP nor a single targeted
barcode can be hammered. Exceeding LOGIN_RATE_MAX within LOGIN_RATE_WINDOW_MIN
blocks further attempts until the window rolls over. A successful login clears
both counters, so an honest patron who mistypes is not left locked out.

Documents carry an `expire_at` timestamp; enabling a Firestore TTL policy on
that field auto-purges stale counters (the code never relies on it for
correctness — the window age is always re-checked).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from google.cloud import firestore

COLLECTION = "login_attempts"
_SANITIZE = re.compile(r"[^A-Za-z0-9]+")


@dataclass
class RateResult:
    blocked: bool
    retry_after_seconds: int = 0


def _doc_id(key: str) -> str:
    """Firestore-safe document id for an arbitrary key (IP or barcode)."""
    return _SANITIZE.sub("_", key)[:200] or "_"


class RateLimiter:
    def __init__(self, client: firestore.Client, max_attempts: int, window_minutes: int):
        self._db = client
        self.max_attempts = max(1, int(max_attempts))
        self.window_seconds = max(60, int(window_minutes) * 60)

    def _col(self):
        return self._db.collection(COLLECTION)

    def check(self, key: str) -> RateResult:
        """Read-only: is this key currently blocked?"""
        snap = self._col().document(_doc_id(key)).get()
        if not snap.exists:
            return RateResult(blocked=False)
        data = snap.to_dict() or {}
        started = float(data.get("window_start", 0))
        count = int(data.get("count", 0))
        age = time.time() - started
        if age >= self.window_seconds:
            return RateResult(blocked=False)  # window rolled over
        if count >= self.max_attempts:
            return RateResult(blocked=True, retry_after_seconds=int(self.window_seconds - age))
        return RateResult(blocked=False)

    def record(self, key: str) -> None:
        """Count one attempt against `key`, opening a new window if needed."""
        ref = self._col().document(_doc_id(key))
        now = time.time()
        snap = ref.get()
        data = snap.to_dict() if snap.exists else None
        if data and (now - float(data.get("window_start", 0))) < self.window_seconds:
            count = int(data.get("count", 0)) + 1
            window_start = float(data["window_start"])
        else:
            count = 1
            window_start = now
        expire_at = datetime.now(timezone.utc) + timedelta(seconds=self.window_seconds)
        ref.set({"count": count, "window_start": window_start, "expire_at": expire_at})

    def clear(self, key: str) -> None:
        """Drop a key's counter — called after a successful login."""
        try:
            self._col().document(_doc_id(key)).delete()
        except Exception:  # noqa: BLE001 — clearing is best-effort
            pass

    def any_blocked(self, keys: list) -> RateResult:
        """Return the first blocking RateResult among `keys`, else not-blocked."""
        worst = RateResult(blocked=False)
        for key in keys:
            res = self.check(key)
            if res.blocked and res.retry_after_seconds > worst.retry_after_seconds:
                worst = res
        return worst
