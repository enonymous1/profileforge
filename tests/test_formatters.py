"""Tests for profileforge.github.formatters."""

from __future__ import annotations

import copy

import pytest

from profileforge.github.formatters import (
    FORMATTERS,
    format_event,
    register_formatter,
)
from profileforge.github.models import (
    GitHubEvent,
    PushPayload,
    ReleasePayload,
    parse_event,
)
from tests.github_fixtures import (
    RAW_CREATE_BRANCH,
    RAW_CREATE_REPO,
    RAW_FORK,
    RAW_ISSUE_COMMENT,
    RAW_ISSUES,
    RAW_PULL_REQUEST,
    RAW_PUSH,
    RAW_RELEASE,
    RAW_UNKNOWN_TYPE,
    RAW_WATCH,
)


def test_format_push() -> None:
    assert (
        format_event(parse_event(RAW_PUSH)) == "📦 Pushed to [`octocat/hello-world`]"
        "(https://github.com/octocat/hello-world) on `main` — Oct 06, 2026"
    )


def test_format_push_omits_commit_count() -> None:
    """Push lines carry no count even when the payload supplies one.

    The live events API provides no per-push count, so the format omits it
    unconditionally rather than printing 0 (or a number) only sometimes.
    """
    raw = {
        "type": "PushEvent",
        "repo": {"name": "octocat/hello-world"},
        "created_at": "2026-10-06T14:23:11Z",
        "payload": {
            "ref": "refs/heads/main",
            "size": 3,
            "commits": [
                {"sha": "abc123", "message": "fix: thing"},
                {"sha": "def456", "message": "feat: other"},
            ],
        },
    }
    assert (
        format_event(parse_event(raw)) == "📦 Pushed to [`octocat/hello-world`]"
        "(https://github.com/octocat/hello-world) on `main` — Oct 06, 2026"
    )


def test_format_create_repository() -> None:
    assert (
        format_event(parse_event(RAW_CREATE_REPO)) == "🌱 Created repository [`octocat/new-repo`]"
        "(https://github.com/octocat/new-repo) — Oct 05, 2026"
    )


def test_format_create_branch() -> None:
    assert (
        format_event(parse_event(RAW_CREATE_BRANCH))
        == "🌱 Created branch `feature-x` in [`octocat/hello-world`]"
        "(https://github.com/octocat/hello-world) — Oct 06, 2026"
    )


def test_format_fork() -> None:
    assert (
        format_event(parse_event(RAW_FORK)) == "🍴 Forked [`octocat/forked-repo`]"
        "(https://github.com/octocat/forked-repo) — Oct 04, 2026"
    )


def test_format_issues() -> None:
    assert (
        format_event(parse_event(RAW_ISSUES)) == "🐛 Opened issue [Bug report]"
        "(https://github.com/octocat/hello-world/issues/1) in "
        "[`octocat/hello-world`](https://github.com/octocat/hello-world) — Oct 03, 2026"
    )


def test_format_issues_escapes_markdown_in_title() -> None:
    """A title containing a Markdown link must not inject a live link."""
    raw = copy.deepcopy(RAW_ISSUES)
    raw["payload"]["issue"]["title"] = "click [here](https://evil.example)"
    assert (
        format_event(parse_event(raw)) == "🐛 Opened issue [click \\[here\\](https://evil.example)]"
        "(https://github.com/octocat/hello-world/issues/1) in "
        "[`octocat/hello-world`](https://github.com/octocat/hello-world) — Oct 03, 2026"
    )


def test_format_issue_comment() -> None:
    assert (
        format_event(parse_event(RAW_ISSUE_COMMENT)) == "💬 Commented on [Bug report]"
        "(https://github.com/octocat/hello-world/issues/1#issuecomment-1) in "
        "[`octocat/hello-world`](https://github.com/octocat/hello-world) — Oct 02, 2026"
    )


def test_format_pull_request() -> None:
    assert (
        format_event(parse_event(RAW_PULL_REQUEST)) == "🔀 Closed PR [Add feature]"
        "(https://github.com/octocat/hello-world/pull/5) in "
        "[`octocat/hello-world`](https://github.com/octocat/hello-world) — Oct 01, 2026"
    )


def test_format_release() -> None:
    assert (
        format_event(parse_event(RAW_RELEASE)) == "🚀 Released [`v1.2.0`]"
        "(https://github.com/octocat/hello-world/releases/tag/v1.2.0) in "
        "[`octocat/hello-world`](https://github.com/octocat/hello-world) — Sep 30, 2026"
    )


def test_unformattable_types_return_none() -> None:
    assert format_event(parse_event(RAW_WATCH)) is None
    assert format_event(parse_event(RAW_UNKNOWN_TYPE)) is None


def test_register_formatter_adds_new_type() -> None:
    try:
        register_formatter("WatchEvent", lambda event: f"⭐ starred {event.repo_name}")
        assert format_event(parse_event(RAW_WATCH)) == "⭐ starred octocat/hello-world"
    finally:
        del FORMATTERS["WatchEvent"]
    assert format_event(parse_event(RAW_WATCH)) is None


def test_register_formatter_rejects_empty_type() -> None:
    with pytest.raises(ValueError):
        register_formatter("", lambda event: "x")


def test_formatter_with_wrong_payload_raises_type_error() -> None:
    event = GitHubEvent(
        type="PushEvent",
        repo_name="octocat/hello-world",
        created_at=None,
        created_at_raw="",
        payload=PushPayload(),
    )
    # Sanity: correct payload type works; a mismatched one raises clearly.
    assert format_event(event) is not None
    bad = GitHubEvent(
        type="PushEvent",
        repo_name="octocat/hello-world",
        created_at=None,
        created_at_raw="",
        payload=PushPayload(),  # placeholder replaced below
    )
    object.__setattr__(bad, "payload", ReleasePayload(tag_name="v1"))
    with pytest.raises(TypeError, match="expected PushPayload"):
        FORMATTERS["PushEvent"](bad)
