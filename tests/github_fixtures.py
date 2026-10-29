"""Shared raw GitHub API event fixtures for the github test modules."""

from __future__ import annotations

from typing import Any

RAW_PUSH: dict[str, Any] = {
    "type": "PushEvent",
    "repo": {"name": "octocat/hello-world"},
    "created_at": "2026-10-06T14:23:11Z",
    "payload": {
        "ref": "refs/heads/main",
        "commits": [
            {"sha": "abc123", "message": "fix: thing"},
            {"sha": "def456", "message": "feat: other"},
        ],
    },
}

RAW_PUSH_SINGLE: dict[str, Any] = {
    "type": "PushEvent",
    "repo": {"name": "octocat/hello-world"},
    "created_at": "2026-10-06T14:23:11Z",
    "payload": {
        "ref": "refs/heads/feature-x",
        "commits": [{"sha": "abc123", "message": "fix: thing"}],
    },
}

RAW_CREATE_REPO: dict[str, Any] = {
    "type": "CreateEvent",
    "repo": {"name": "octocat/new-repo"},
    "created_at": "2026-10-05T09:00:00Z",
    "payload": {"ref_type": "repository"},
}

RAW_CREATE_BRANCH: dict[str, Any] = {
    "type": "CreateEvent",
    "repo": {"name": "octocat/hello-world"},
    "created_at": "2026-10-06T09:00:00Z",
    "payload": {"ref_type": "branch", "ref": "feature-x"},
}

RAW_FORK: dict[str, Any] = {
    "type": "ForkEvent",
    "repo": {"name": "octocat/hello-world"},
    "created_at": "2026-10-04T12:00:00Z",
    "payload": {"forkee": {"full_name": "octocat/forked-repo"}},
}

RAW_ISSUES: dict[str, Any] = {
    "type": "IssuesEvent",
    "repo": {"name": "octocat/hello-world"},
    "created_at": "2026-10-03T08:30:00Z",
    "payload": {
        "action": "opened",
        "issue": {
            "title": "Bug report",
            "html_url": "https://github.com/octocat/hello-world/issues/1",
        },
    },
}

RAW_ISSUE_COMMENT: dict[str, Any] = {
    "type": "IssueCommentEvent",
    "repo": {"name": "octocat/hello-world"},
    "created_at": "2026-10-02T18:45:00Z",
    "payload": {
        "issue": {"title": "Bug report"},
        "comment": {"html_url": "https://github.com/octocat/hello-world/issues/1#issuecomment-1"},
    },
}

RAW_PULL_REQUEST: dict[str, Any] = {
    "type": "PullRequestEvent",
    "repo": {"name": "octocat/hello-world"},
    "created_at": "2026-10-01T11:15:00Z",
    "payload": {
        "action": "closed",
        "pull_request": {
            "title": "Add feature",
            "html_url": "https://github.com/octocat/hello-world/pull/5",
        },
    },
}

RAW_RELEASE: dict[str, Any] = {
    "type": "ReleaseEvent",
    "repo": {"name": "octocat/hello-world"},
    "created_at": "2026-09-30T20:00:00Z",
    "payload": {
        "release": {
            "tag_name": "v1.2.0",
            "html_url": "https://github.com/octocat/hello-world/releases/tag/v1.2.0",
        }
    },
}

RAW_WATCH: dict[str, Any] = {
    "type": "WatchEvent",
    "repo": {"name": "octocat/hello-world"},
    "created_at": "2026-10-06T14:23:11Z",
    "payload": {"action": "started"},
}

RAW_UNKNOWN_TYPE: dict[str, Any] = {
    "type": "GollumEvent",
    "repo": {"name": "octocat/hello-world"},
    "created_at": "2026-10-06T14:23:11Z",
    "payload": {"pages": []},
}

RAW_BAD_DATE: dict[str, Any] = {
    **RAW_PUSH,
    "created_at": "not-a-date",
}

RAW_SPARSE_PUSH: dict[str, Any] = {"type": "PushEvent"}

ALL_RAW_EVENTS: list[dict[str, Any]] = [
    RAW_PUSH,
    RAW_PUSH_SINGLE,
    RAW_CREATE_REPO,
    RAW_CREATE_BRANCH,
    RAW_FORK,
    RAW_ISSUES,
    RAW_ISSUE_COMMENT,
    RAW_PULL_REQUEST,
    RAW_RELEASE,
    RAW_WATCH,
    RAW_UNKNOWN_TYPE,
    RAW_BAD_DATE,
    RAW_SPARSE_PUSH,
]
