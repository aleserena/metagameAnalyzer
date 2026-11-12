"""Small thread-safe, in-memory sliding-window rate limiter (single-instance deploys)."""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request


class RateLimiter:
    """Allow at most ``max_events`` recorded events per key within ``window_seconds``.

    ``allow`` does not record; callers ``record`` only the events they want counted.
    Expired events and empty keys are dropped on every call so memory stays bounded.
    """

    def __init__(self, max_events: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        for key in list(self._events):
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                del self._events[key]

    def allow(self, key: str) -> bool:
        with self._lock:
            self._prune(self._clock())
            return len(self._events.get(key, ())) < self.max_events

    def record(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            self._prune(now)
            self._events.setdefault(key, deque()).append(now)

    def retry_after(self, key: str) -> int:
        """Whole seconds until ``key`` is allowed again (0 when allowed now)."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            events = self._events.get(key)
            if not events or len(events) < self.max_events:
                return 0
            # The event that frees a slot is the one ``max_events`` from the newest.
            oldest_relevant = events[len(events) - self.max_events]
            return max(1, math.ceil(oldest_relevant + self.window_seconds - now))

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)


def client_ip(request: Request) -> str:
    """Client IP: Railway's ``X-Real-IP`` when present, else the socket peer, else "unknown".

    Railway's edge overwrites a client-supplied ``X-Real-IP`` (and ``X-Forwarded-For``), so the
    rate limiters keyed on this cannot be sidestepped by forging the header. Verified on staging
    2026-11-12: a request sent with ``X-Real-IP: 203.0.113.9`` was logged with the real address.
    Re-check if the app moves behind a different proxy.
    """
    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def rate_limited(limiter: RateLimiter) -> Callable[[Request], None]:
    """FastAPI dependency: count every request per client IP against ``limiter``; 429 when over."""

    def dependency(request: Request) -> None:
        ip = client_ip(request)
        if not limiter.allow(ip):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Try again later.",
                headers={"Retry-After": str(limiter.retry_after(ip))},
            )
        limiter.record(ip)

    return dependency
