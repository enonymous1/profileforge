"""Tests for profileforge.github.models."""

from __future__ import annotations

from profileforge.github.models import (
    CreatePayload,
    ForkPayload,
    GitHubEvent,
    IssueCommentPayload,
    IssuePayload,
    PullRequestPayload,
    PushPayload,
    ReleasePayload,
    UnknownPayload,
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
    RAW_SPARSE_PUSH,
    RAW_UNKNOWN_TYPE,
)


def test_parse_push() -> None:
    event = parse_event(RAW_PUSH)
    assert isinstance(event, GitHubEvent)
    assert event.type == "PushEvent"
    assert event.repo_name == "octocat/hello-world"
    assert event.repo_url == "https://github.com/octocat/hello-world"
    assert event.date_str == "Oct 06, 2026"
    assert event.created_at is not None
    payload = event.payload
    assert isinstance(payload, PushPayload)
    assert payload.branch == "main"
    assert len(payload.commits) == 2
    assert payload.commits[0].sha == "abc123"


def test_parse_push_strips_refs_heads() -> None:
    event = parse_event(
        {
            "type": "PushEvent",
            "repo": {"name": "octocat/hello-world"},
            "created_at": "2026-10-06T14:23:11Z",
            "payload": {"ref": "refs/heads/feature-x", "commits": []},
        }
    )
    payload = event.payload
    assert isinstance(payload, PushPayload)
    assert payload.branch == "feature-x"


def test_parse_push_live_shape_without_commits() -> None:
    """Live events-API shape: no ``commits`` array, no ``size`` — still parses."""
    event = parse_event(
        {
            "type": "PushEvent",
            "repo": {"name": "octocat/hello-world"},
            "created_at": "2026-10-28T10:00:00Z",
            "payload": {
                "ref": "refs/heads/main",
                "head": "abc123",
                "before": "def456",
                "push_id": 1,
            },
        }
    )
    payload = event.payload
    assert isinstance(payload, PushPayload)
    assert payload.branch == "main"
    assert payload.commits == ()


def test_parse_create_repo() -> None:
    payload = parse_event(RAW_CREATE_REPO).payload
    assert isinstance(payload, CreatePayload)
    assert payload.ref_type == "repository"


def test_parse_create_branch() -> None:
    payload = parse_event(RAW_CREATE_BRANCH).payload
    assert isinstance(payload, CreatePayload)
    assert payload.ref_type == "branch"
    assert payload.ref == "feature-x"


def test_parse_fork() -> None:
    payload = parse_event(RAW_FORK).payload
    assert isinstance(payload, ForkPayload)
    assert payload.forkee_full_name == "octocat/forked-repo"


def test_parse_fork_defaults_to_repo() -> None:
    payload = parse_event(
        {
            "type": "ForkEvent",
            "repo": {"name": "octocat/hello-world"},
            "created_at": "2026-10-06T14:23:11Z",
            "payload": {},
        }
    ).payload
    assert isinstance(payload, ForkPayload)
    assert payload.forkee_full_name == "octocat/hello-world"


def test_parse_issues() -> None:
    payload = parse_event(RAW_ISSUES).payload
    assert isinstance(payload, IssuePayload)
    assert payload.action == "opened"
    assert payload.title == "Bug report"
    assert payload.url == "https://github.com/octocat/hello-world/issues/1"


def test_parse_issue_comment() -> None:
    payload = parse_event(RAW_ISSUE_COMMENT).payload
    assert isinstance(payload, IssueCommentPayload)
    assert payload.title == "Bug report"
    assert "issuecomment-1" in payload.url


def test_parse_pull_request() -> None:
    payload = parse_event(RAW_PULL_REQUEST).payload
    assert isinstance(payload, PullRequestPayload)
    assert payload.action == "closed"
    assert payload.title == "Add feature"


def test_parse_release() -> None:
    payload = parse_event(RAW_RELEASE).payload
    assert isinstance(payload, ReleasePayload)
    assert payload.tag_name == "v1.2.0"


def test_parse_unknown_type_never_raises() -> None:
    event = parse_event(RAW_UNKNOWN_TYPE)
    assert isinstance(event.payload, UnknownPayload)


def test_parse_sparse_event_uses_defaults() -> None:
    event = parse_event(RAW_SPARSE_PUSH)
    assert event.repo_name == "unknown/unknown"
    assert event.created_at is None
    assert event.date_str == ""
    payload = event.payload
    assert isinstance(payload, PushPayload)
    assert payload.branch == "main"
    assert payload.commits == ()


def test_parse_tolerates_null_nesting() -> None:
    event = parse_event(
        {
            "type": "IssuesEvent",
            "repo": None,
            "created_at": "2026-10-03T08:30:00Z",
            "payload": {"issue": None},
        }
    )
    assert event.repo_name == "unknown/unknown"
    payload = event.payload
    assert isinstance(payload, IssuePayload)
    assert payload.title == "an issue"


def test_bad_date_falls_back_to_raw_prefix() -> None:
    event = parse_event({**RAW_PUSH, "created_at": "not-a-date"})
    assert event.created_at is None
    assert event.date_str == "not-a-date"
