"""Byte-parity: new formatters must match the legacy implementation exactly.

The legacy `format_event` is kept verbatim in `tests/_legacy.py` as the
golden master. If this test fails, the refactor changed user-visible output.

PushEvent is excluded deliberately: the legacy formatter printed a commit
count, but the public events API supplies no per-push count, so the new
formatter omits it (see test_format_push_omits_commit_count). That
divergence is specified, not a regression.
"""

from __future__ import annotations

from typing import Any

import pytest

from profileforge.github.formatters import format_event as new_format_event
from profileforge.github.models import parse_event
from tests._legacy import format_event as legacy_format_event
from tests.github_fixtures import ALL_RAW_EVENTS

NON_PUSH_EVENTS = [raw for raw in ALL_RAW_EVENTS if raw.get("type") != "PushEvent"]


@pytest.mark.parametrize("raw", NON_PUSH_EVENTS, ids=lambda r: r.get("type", "?"))
def test_formatter_matches_legacy_byte_for_byte(raw: dict[str, Any]) -> None:
    assert new_format_event(parse_event(raw)) == legacy_format_event(raw)
