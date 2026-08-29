"""Structured JSON-line logging.

A small stdlib wrapper that emits single-line JSON records so container logs and
the AIOps `telemetry_logs` ingestion are machine-parseable. Collects logs for this
module and a few high-signal sibling modules; any module can also use the stdlib
`logging` API (we attach a JSON handler to the root logger too).
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "run_id", "provider", "model", "status", "method", "path"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info and record.exc_info[0]:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [h for h in logger.handlers if isinstance(h, logging.Handler)]


def setup(level: int = logging.INFO) -> logging.Logger:
    """Install a JSON handler on the root logger and return it. Idempotent."""
    global _CONFIGURED
    root = logging.getLogger()
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
        root.setLevel(level)
        _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (JSON handler inherited from root after setup)."""
    if not _CONFIGURED:
        setup()
    logger = logging.getLogger(name)
    logger.propagate = True
    return logger
