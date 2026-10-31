"""Tests for profileforge.profile.snapshot."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from profileforge.github.client import GitHubClient
from profileforge.profile.snapshot import ProfileSnapshot, fetch_profile_snapshot


class _StubClient(GitHubClient):
    """Stub client with canned API payloads (no network)."""

    def __init__(self) -> None:
        pass

    def fetch_user(self, username: str) -> dict[str, Any]:
        return {
            "login": "octocat",
            "name": "Octo",
            "bio": "bio",
            "html_url": "https://github.com/octocat",
            "avatar_url": "https://avatars.example/u/1",
            "public_repos": 2,
            "followers": 30,
            "following": 1,
        }

    def fetch_repos(
        self, username: str, *, per_page: int = 100, repo_type: str = "owner"
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": "b",
                "full_name": "octocat/b",
                "html_url": "https://github.com/octocat/b",
                "description": "B project",
                "stargazers_count": 7,
                "language": "Rust",
                "fork": False,
                "archived": False,
                "forks_count": 1,
                "topics": ["cli"],
                "updated_at": "2026-09-01T00:00:00Z",
            },
        ]

    def fetch_public_events(
        self, username: str, per_page: int = 50, max_pages: int = 1
    ) -> list[dict[str, Any]]:
        return [
            {
                "type": "PushEvent",
                "repo": {"name": "octocat/b"},
                "created_at": "2026-10-07T10:00:00Z",
                "payload": {"ref": "refs/heads/main", "commits": [{"sha": "x"}]},
            }
        ]


def test_fetch_profile_snapshot() -> None:
    now = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    snapshot = fetch_profile_snapshot(
        _StubClient(), "octocat", max_lines=5, sparkline_days=7, now=now
    )
    assert isinstance(snapshot, ProfileSnapshot)
    assert snapshot.user.login == "octocat"
    assert [repo.name for repo in snapshot.repos] == ["b"]
    assert len(snapshot.events) == 1
    assert snapshot.activity_lines == (
        "📦 Pushed to [`octocat/b`](https://github.com/octocat/b) on `main` — Oct 07, 2026",
    )
    # The push lands on the last (newest) day of the 7-day window.
    assert snapshot.daily_counts == (0, 0, 0, 0, 0, 0, 1)
    assert snapshot.window_start.isoformat() == "2026-10-01"
