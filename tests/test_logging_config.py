"""Tests for profileforge.logging_config."""

from __future__ import annotations

import json
import logging

from profileforge.logging_config import setup_logging


def test_setup_logging_console(capsys: object) -> None:
    setup_logging("INFO")
    logging.getLogger("profileforge.test").info("hello console")
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "hello console" in captured.err
    assert "INFO" in captured.err


def test_setup_logging_json(capsys: object) -> None:
    setup_logging("DEBUG", json_output=True)
    logging.getLogger("profileforge.test").warning("hello json")
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.err.strip().splitlines()[-1])
    assert payload["level"] == "WARNING"
    assert payload["message"] == "hello json"
    assert payload["logger"] == "profileforge.test"
    assert "timestamp" in payload


def test_setup_logging_respects_level(capsys: object) -> None:
    setup_logging("ERROR")
    logging.getLogger("profileforge.test").info("too quiet")
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "too quiet" not in captured.err
