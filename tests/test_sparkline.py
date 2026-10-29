"""Tests for profileforge.profile.sparkline."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from profileforge.github.models import GitHubEvent, PushPayload
from profileforge.profile.sparkline import (
    build_daily_counts,
    render_sparkline_svg,
    sparkline_start,
)

_NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def _event(day: int, hour: int = 10) -> GitHubEvent:
    return GitHubEvent(
        type="PushEvent",
        repo_name="octocat/proj",
        created_at=datetime(2026, 10, day, hour, tzinfo=UTC),
        created_at_raw="",
        payload=PushPayload(branch="main", commits=()),
    )


def test_build_daily_counts() -> None:
    events = [
        _event(7),
        _event(7, 15),
        _event(5),
        _event(1),  # first covered day
        _event(30, 10),  # outside the window (September)
    ]
    # Undated events are ignored.
    events.append(
        GitHubEvent(
            type="PushEvent",
            repo_name="o/p",
            created_at=None,
            created_at_raw="",
            payload=PushPayload(),
        )
    )
    assert build_daily_counts(events, 7, now=_NOW) == [1, 0, 0, 0, 1, 0, 2]


def test_build_daily_counts_rejects_non_positive_days() -> None:
    with pytest.raises(ValueError, match="days"):
        build_daily_counts([], 0, now=_NOW)


def test_sparkline_start() -> None:
    assert sparkline_start(7, now=_NOW) == date(2026, 10, 1)
    with pytest.raises(ValueError, match="days"):
        sparkline_start(0, now=_NOW)


def test_render_sparkline_svg() -> None:
    svg = render_sparkline_svg([0, 2, 4], date(2026, 10, 5))
    assert svg.startswith("<svg ")
    assert svg.count("<rect") == 3
    assert 'width="22"' in svg  # 3 * (6 + 2) - 2
    assert 'height="40"' in svg  # peak bar fills the height
    assert 'height="20"' in svg  # half-peak bar
    assert 'height="2"' in svg  # empty day gets a stub bar
    assert 'fill="#39d353"' in svg
    assert 'fill="#30363d"' in svg
    assert "<title>2026-10-05: 0 event(s)</title>" in svg
    assert "<title>2026-10-07: 4 event(s)</title>" in svg
    assert 'role="img"' in svg


def test_render_sparkline_svg_empty() -> None:
    svg = render_sparkline_svg([], date(2026, 10, 7))
    assert "<rect" not in svg
    assert svg.startswith("<svg ")


def test_render_sparkline_svg_all_zero() -> None:
    svg = render_sparkline_svg([0, 0], date(2026, 10, 6))
    assert svg.count("<rect") == 2
    assert "#39d353" not in svg
