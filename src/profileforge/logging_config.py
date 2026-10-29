"""Deterministic logging setup for profileforge (stdlib only).

Call :func:`setup_logging` once at startup (the CLI does this from settings).
Library code just does ``logging.getLogger(__name__)`` — no ``print()``.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_CONSOLE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


class _JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter without extra dependencies."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    """Configure the root logger. Safe to call multiple times.

    Args:
        level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
        json_output: Emit one JSON object per line instead of human text.
    """
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    if json_output:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT, _DATE_FORMAT))
    root.addHandler(handler)
