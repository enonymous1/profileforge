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

# The handler this module installed, if any. Tracked so reconfiguration
# removes only our own handler — never a host application's.
_owned_handler: logging.Handler | None = None


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


def setup_logging(level: str = "INFO", *, json_output: bool = False, force: bool = False) -> None:
    """Configure the root logger. Safe to call multiple times.

    With ``force=False`` (the default), a root logger that already has
    handlers from somewhere else is left alone apart from its level —
    importing profileforge into a larger app must never wipe the host's
    handlers. A previous call by this module reconfigures normally (its
    own handler is replaced), and ``force=True`` restores the old
    remove-everything behavior for the CLI.

    Args:
        level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
        json_output: Emit one JSON object per line instead of human text.
        force: Remove all existing root handlers before configuring.
    """
    global _owned_handler
    root = logging.getLogger()
    root.setLevel(level.upper())
    if _owned_handler is not None:
        root.removeHandler(_owned_handler)
        _owned_handler = None
    if force:
        for handler in list(root.handlers):
            root.removeHandler(handler)
    elif root.handlers:
        # Foreign handlers (a host application's) stay untouched.
        return
    handler = logging.StreamHandler(sys.stderr)
    if json_output:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT, _DATE_FORMAT))
    root.addHandler(handler)
    _owned_handler = handler
