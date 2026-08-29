"""Per-IP sliding-window rate limiting as ASGI middleware.

Global default limit (e.g. 120 req/min) with a small in-memory window per client
IP. Sensitive endpoints can be exempted by path prefix. Optionally locks login
and auth-ish routes tighter so brute-forcing is impractical.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Callable

from slowapi.util import get_remote_address


class Bucket:
    __slots__ = ("hits", "reset_at")

    def __init__(self) -> None:
        self.hits = deque()
        self.reset_at = 0.0


class RateLimit:
    """A sliding-window counter: allow `limit` requests per `window` seconds."""

    def __init__(self, limit: int, window: float = 60.0) -> None:
        self.limit = limit
        self.window = window
        self._buckets: dict[str, Bucket] = {}
        self._lock = threading.Lock()
        _ALL_LIMITERS.add(self)

    def _key(self, scope: dict) -> str:
        try:
            return get_remote_address(type("R", (), {"client": scope.get("client"), "headers": scope.get("headers")})())
        except Exception:  # noqa: BLE001
            return "unknown"

    def allow(self, scope: dict) -> bool:
        key = self._key(scope)
        now = time.monotonic()
        with self._lock:
            b = self._buckets.get(key)
            if b is None or now > b.reset_at:
                b = self._buckets[key] = Bucket()
                b.reset_at = now + self.window
            # keep only hits still inside the sliding window
            b.hits = deque(h for h in b.hits if h > now - self.window)
            if len(b.hits) >= self.limit:
                return False
            b.hits.append(now)
            return True

    def reset(self) -> None:
        """Drop all tracked buckets (used by tests and manual ops resets)."""
        with self._lock:
            self._buckets.clear()


class RateLimitMiddleware:
    def __init__(
        self,
        app: Callable[..., Any],
        *,
        limit: int = 120,
        window: float = 60.0,
        exempt_prefixes: tuple[str, ...] = ("/metrics", "/health"),
        strict_prefixes: tuple[str, ...] = ("/api/auth",),
        strict_limit: int = 10,
    ) -> None:
        self.app = app
        self.default = RateLimit(limit, window)
        self.strict = RateLimit(strict_limit, window)
        self.exempt = exempt_prefixes
        self.strict_pre = strict_prefixes

    def reset(self) -> None:
        """Clear in-process buckets (tests / ops reset)."""
        self.default.reset()
        self.strict.reset()

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path.startswith(self.exempt):
            await self.app(scope, receive, send)
            return
        limiter = self.strict if path.startswith(self.strict_pre) else self.default
        if not limiter.allow(scope):
            from starlette.responses import PlainTextResponse

            response = PlainTextResponse("429 Too Many Requests", status_code=429)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


# All live limiter instances, so ops/tests can clear buckets without holding a
# reference to the (Starlette-wired) middleware instance.
_ALL_LIMITERS: set[RateLimit] = set()


def reset_all() -> None:
    """Reset every registered limiter (used by tests and manual ops resets)."""
    for limiter in list(_ALL_LIMITERS):
        limiter.reset()

