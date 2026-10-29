"""Tests for profileforge.github.activity."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from profileforge.github.activity import (
    DEFAULT_SKIP_EVENT_TYPES,
    build_activity_lines,
)
from tests import _legacy

RAW_ACTIVITY_FEED: list[dict[str, Any]] = [
    {
        "type": "PushEvent",
        "repo": {"name": "octocat/proj"},
        "created_at": "2026-10-07T10:00:00Z",
        "payload": {
            "ref": "refs/heads/main",
            "commits": [{"sha": "a1", "message": "one"}],
        },
    },
    {
        "type": "WatchEvent",
        "repo": {"name": "octocat/proj"},
        "created_at": "2026-10-07T09:00:00Z",
        "payload": {"action": "started"},
    },
    {
        "type": "PushEvent",
        "repo": {"name": "octocat/proj"},
        "created_at": "2026-10-06T10:00:00Z",
        "payload": {
            "ref": "refs/heads/main",
            "commits": [
                {"sha": "a2", "message": "two"},
                {"sha": "a3", "message": "three"},
            ],
        },
    },
    {
        "type": "PushEvent",
        "repo": {"name": "octocat/proj"},
        "created_at": "2026-10-05T10:00:00Z",
        "payload": {
            "ref": "refs/heads/dev",
            "commits": [{"sha": "b1", "message": "dev work"}],
        },
    },
    {
        "type": "IssuesEvent",
        "repo": {"name": "octocat/other"},
        "created_at": "2026-10-04T10:00:00Z",
        "payload": {
            "action": "opened",
            "issue": {
                "title": "Bug!",
                "html_url": "https://github.com/octocat/other/issues/9",
            },
        },
    },
    {
        "type": "PushEvent",
        "repo": {"name": "octocat/octocat"},
        "created_at": "2026-10-03T10:00:00Z",
        "payload": {
            "ref": "refs/heads/main",
            "commits": [{"sha": "c1", "message": "profile edit"}],
        },
    },
    {
        "type": "CreateEvent",
        "repo": {"name": "octocat/new"},
        "created_at": "2026-10-02T10:00:00Z",
        "payload": {"ref_type": "repository"},
    },
    {
        "type": "GollumEvent",
        "repo": {"name": "octocat/proj"},
        "created_at": "2026-10-01T10:00:00Z",
        "payload": {"pages": []},
    },
    {
        "type": "ReleaseEvent",
        "repo": {"name": "octocat/proj"},
        "created_at": "2026-09-30T10:00:00Z",
        "payload": {
            "release": {
                "tag_name": "v2.0",
                "html_url": "https://github.com/octocat/proj/releases/tag/v2.0",
            }
        },
    },
]


def _legacy_lines(raw: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setattr(_legacy, "USERNAME", "octocat")
    monkeypatch.setattr(_legacy, "SKIP_REPO", "octocat/octocat")
    monkeypatch.setattr(_legacy, "MAX_LINES", 5)
    return _legacy.build_activity_lines(raw)


def test_build_activity_lines_matches_legacy_except_push_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parity with legacy on every event type except pushes.

    Push lines are excluded deliberately: the legacy formatter printed a
    commit count, but the public events API supplies no per-push count, so
    the new formatter omits it. (Feeds *with* duplicate pushes are covered
    by test_push_collapse_keeps_newest_push_per_branch: the legacy
    "collapse" never took effect in its output, so asserting parity there
    would enshrine the bug.)
    """
    feed = [event for event in RAW_ACTIVITY_FEED if event["type"] != "PushEvent"]
    legacy_result = _legacy_lines(copy.deepcopy(feed), monkeypatch)
    new_result = build_activity_lines(copy.deepcopy(feed), username="octocat", max_lines=5)
    assert new_result == legacy_result
    assert new_result == [
        "🐛 Opened issue [Bug!](https://github.com/octocat/other/issues/9) in "
        "[`octocat/other`](https://github.com/octocat/other) — Oct 04, 2026",
        "🌱 Created repository [`octocat/new`](https://github.com/octocat/new) — Oct 02, 2026",
        "🚀 Released [`v2.0`](https://github.com/octocat/proj/releases/tag/v2.0)"
        " in [`octocat/proj`](https://github.com/octocat/proj) — Sep 30, 2026",
    ]


def test_push_collapse_keeps_newest_push_per_branch() -> None:
    """Duplicate pushes collapse to one line: the newest push, no count."""
    lines = build_activity_lines(copy.deepcopy(RAW_ACTIVITY_FEED), username="octocat", max_lines=10)
    assert lines[0] == (
        "📦 Pushed to [`octocat/proj`](https://github.com/octocat/proj) on `main` — Oct 07, 2026"
    )
    # The dev-branch push stays its own line.
    assert lines[1].endswith("on `dev` — Oct 05, 2026")


def test_push_collapse_keeps_newest_date() -> None:
    lines = build_activity_lines(copy.deepcopy(RAW_ACTIVITY_FEED), username="octocat", max_lines=10)
    assert lines[0].startswith("📦 Pushed to")
    assert lines[0].endswith("Oct 07, 2026")


def test_push_collapse_drops_older_live_shape_pushes() -> None:
    """Live-shape pushes (no ``commits``/``size``) collapse to the newest line."""
    feed = [
        {
            "type": "PushEvent",
            "repo": {"name": "octocat/proj"},
            "created_at": "2026-10-28T10:00:00Z",
            "payload": {"ref": "refs/heads/main", "head": "abc123", "before": "def456"},
        },
        {
            "type": "PushEvent",
            "repo": {"name": "octocat/proj"},
            "created_at": "2026-10-27T10:00:00Z",
            "payload": {"ref": "refs/heads/main", "head": "ghi789", "before": "jkl012"},
        },
    ]
    lines = build_activity_lines(feed, username="octocat", max_lines=10)
    assert lines == [
        "📦 Pushed to [`octocat/proj`](https://github.com/octocat/proj) on `main` — Oct 28, 2026"
    ]


def test_max_lines_caps_output() -> None:
    lines = build_activity_lines(copy.deepcopy(RAW_ACTIVITY_FEED), username="octocat", max_lines=2)
    assert len(lines) == 2


def test_empty_input_gives_empty_output() -> None:
    assert build_activity_lines([], username="octocat", max_lines=5) == []


def test_all_filtered_gives_empty_output() -> None:
    raw = [
        {
            "type": "WatchEvent",
            "repo": {"name": "octocat/x"},
            "created_at": "2026-10-07T10:00:00Z",
            "payload": {},
        }
    ]
    assert build_activity_lines(raw, username="octocat", max_lines=5) == []


def test_custom_skip_types() -> None:
    lines = build_activity_lines(
        copy.deepcopy(RAW_ACTIVITY_FEED),
        username="octocat",
        max_lines=10,
        skip_event_types={"PushEvent"},
    )
    assert not any(line.startswith("📦") for line in lines)
    assert any(line.startswith("🐛") for line in lines)


def test_default_skip_types() -> None:
    assert DEFAULT_SKIP_EVENT_TYPES == {"WatchEvent", "DeleteEvent", "MemberEvent"}


def test_blank_username_rejected() -> None:
    with pytest.raises(ValueError, match="username"):
        build_activity_lines([], username="  ", max_lines=5)


def test_non_positive_max_lines_rejected() -> None:
    with pytest.raises(ValueError, match="max_lines"):
        build_activity_lines([], username="octocat", max_lines=0)


def test_does_not_mutate_input() -> None:
    raw = copy.deepcopy(RAW_ACTIVITY_FEED)
    snapshot = copy.deepcopy(raw)
    build_activity_lines(raw, username="octocat", max_lines=10)
    assert raw == snapshot
