"""Prometheus metrics and a small ASGI middleware.

Exposes `/metrics` (Prometheus text format) with HTTP RED counters derived from a
thin middleware. Cheap, standard, and feeds the AIOps/observability story on a
self-hosted box.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REQUEST_COUNT = Counter(
    "hivestack_http_requests_total",
    "Total HTTP requests processed",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "hivestack_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)
ACTIVE_REQUESTS = Gauge("hivestack_http_inflight", "In-flight HTTP requests")


class MetricsMiddleware:
    """Record method/path/status counters + latency for every HTTP response."""

    def __init__(self, app: Callable[..., Any]) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = (scope.get("method") or "GET").upper()
        # Collapse dynamic route ids into the route template if present.
        path = (scope.get("path") or "/")
        try:
            route = scope.get("route")
            if route is not None and route.path_format is not None:
                path = route.path_format
        except Exception:  # noqa: BLE001
            pass

        ACTIVE_REQUESTS.inc()
        sent_status: dict[str, int] = {"code": 200}
        start = time.perf_counter()

        async def wrapped_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                sent_status["code"] = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            REQUEST_LATENCY.labels(method=method, path=path).observe(time.perf_counter() - start)
            REQUEST_COUNT.labels(method=method, path=path, status=sent_status["code"]).inc()
            ACTIVE_REQUESTS.dec()


def metrics_payload() -> bytes:
    """Return the Prometheus scrape payload (GB encoded bytes)."""
    return generate_latest()
