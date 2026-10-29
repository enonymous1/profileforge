"""Tests for profileforge.site.data."""

from __future__ import annotations

from typing import Any

import pytest

from profileforge.github.client import GitHubClient
from profileforge.profile.stats import RepoSummary
from profileforge.site.data import (
    SiteData,
    assemble_site_data,
    language_color,
    select_projects,
)


def _repo(
    name: str,
    stars: int,
    *,
    language: str | None = "Python",
    fork: bool = False,
    archived: bool = False,
) -> RepoSummary:
    return RepoSummary(
        name=name,
        full_name=f"octocat/{name}",
        html_url=f"https://github.com/octocat/{name}",
        description=f"{name} does things",
        stargazers_count=stars,
        language=language,
        fork=fork,
        archived=archived,
        forks_count=2,
        topics=("demo",),
        updated_at="2026-10-01T00:00:00Z",
    )


def test_select_projects_ranks_by_stars() -> None:
    repos = [_repo("c", 1), _repo("a", 10), _repo("b", 5)]
    cards = select_projects(repos, limit=2)
    assert [card.name for card in cards] == ["a", "b"]
    assert cards[0].language_color == "#3572A5"
    assert cards[0].topics == ("demo",)
    assert cards[0].forks_count == 2


def test_select_projects_skips_forks_and_archived() -> None:
    repos = [
        _repo("fork", 100, fork=True),
        _repo("old", 50, archived=True),
        _repo("real", 1),
    ]
    assert [card.name for card in select_projects(repos)] == ["real"]


def test_select_projects_unknown_language_color() -> None:
    cards = select_projects([_repo("x", 1, language="Brainfuck")])
    assert cards[0].language_color == "#8b949e"


def test_select_projects_rejects_bad_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        select_projects([], limit=0)


def test_language_color_none() -> None:
    assert language_color(None) == "#8b949e"
    assert language_color("Rust") == "#dea584"


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
            {
                "name": "a",
                "full_name": "octocat/a",
                "html_url": "https://github.com/octocat/a",
                "description": "",
                "stargazers_count": 3,
                "language": "Python",
                "fork": False,
                "archived": False,
                "forks_count": 0,
                "topics": [],
                "updated_at": "2026-08-01T00:00:00Z",
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


def test_assemble_site_data() -> None:
    data = assemble_site_data(
        _StubClient(), "octocat", max_lines=5, sparkline_days=7, projects_limit=1
    )
    assert isinstance(data, SiteData)
    assert data.user.login == "octocat"
    assert data.total_stars == 10
    assert [card.name for card in data.projects] == ["b"]  # ranked by stars
    assert len(data.activity_lines) == 1
    assert data.activity_html[0] == (
        '📦 Pushed to <a href="https://github.com/octocat/b">'
        "<code>octocat/b</code></a> on <code>main</code> — Oct 07, 2026"
    )
    assert data.sparkline_svg.startswith("<svg ")
    assert data.sparkline_days == 7
    assert len(data.languages) == 2
