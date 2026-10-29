"""Tests for profileforge.profile.renderer."""

from __future__ import annotations

from typing import Any

from profileforge.github.client import GitHubClient
from profileforge.profile.renderer import (
    build_profile_context,
    render_readme,
    render_stats_body,
    render_top_languages,
)
from profileforge.profile.stats import LanguageStat, UserSummary


def _context() -> dict[str, Any]:
    return {
        "user": UserSummary(
            login="octocat",
            name="Octo Cat",
            bio="I build things",
            html_url="https://github.com/octocat",
            avatar_url="https://avatars.example/u/1",
            public_repos=8,
            followers=100,
            following=5,
        ),
        "total_stars": 42,
        "languages": [LanguageStat(name="Python", repos=3, stars=10, share=60.0)],
        "activity_lines": ["📦 Pushed 1 commit to [`o/p`](https://github.com/o/p)"],
        "sparkline_svg": "<svg>fake</svg>",
        "render_stats_body": render_stats_body,
        "sparkline_days": 30,
        "refreshed_at": "2026-10-07 12:00",
    }


def test_render_readme() -> None:
    rendered = render_readme(_context())
    assert "# Hi there, I'm Octo Cat 👋" in rendered
    assert "I build things" in rendered
    assert "**42**" in rendered
    assert "**8**" in rendered
    assert "<!--START_SECTION:activity-->\n- 📦 Pushed 1 commit" in rendered
    assert "<!--END_SECTION:activity-->" in rendered
    assert "<!--START_SECTION:stats-->" in rendered
    assert "<svg>fake</svg>" in rendered
    assert "<!--END_SECTION:stats-->" in rendered
    assert "Python" in rendered
    assert "Last refreshed 2026-10-07 12:00 UTC" in rendered


def test_render_readme_without_bio() -> None:
    context = _context()
    user = context["user"]
    context["user"] = UserSummary(
        login=user.login,
        name=user.name,
        bio="",
        html_url=user.html_url,
        avatar_url=user.avatar_url,
        public_repos=user.public_repos,
        followers=user.followers,
        following=user.following,
    )
    rendered = render_readme(context)
    assert "# Hi there, I'm Octo Cat 👋" in rendered
    assert "## 📊 GitHub stats" in rendered


def test_render_top_languages_escapes_names() -> None:
    html = render_top_languages([LanguageStat(name="<C++>", repos=1, stars=1, share=50.0)])
    assert "&lt;C++&gt;" in html
    assert "<C++>" not in html


def test_render_stats_body() -> None:
    body = render_stats_body(
        [LanguageStat(name="Python", repos=2, stars=3, share=66.7)],
        "<svg>s</svg>",
        30,
    )
    assert body.startswith("<svg>s</svg>\n")
    assert "last 30 days" in body
    assert "Top languages" in body
    assert "Python" in body


class _StubClient(GitHubClient):
    """Stub client with canned API payloads (no network)."""

    def __init__(self) -> None:
        pass

    def fetch_user(self, username: str) -> dict[str, Any]:
        assert username == "octocat"
        return {
            "login": "octocat",
            "name": "Octo",
            "bio": "",
            "html_url": "https://github.com/octocat",
            "avatar_url": "",
            "public_repos": 2,
            "followers": 3,
            "following": 1,
        }

    def fetch_repos(
        self, username: str, *, per_page: int = 100, repo_type: str = "owner"
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": "a",
                "full_name": "octocat/a",
                "html_url": "https://github.com/octocat/a",
                "description": "",
                "stargazers_count": 5,
                "language": "Python",
                "fork": False,
                "archived": False,
            }
        ]

    def fetch_public_events(
        self, username: str, per_page: int = 50, max_pages: int = 1
    ) -> list[dict[str, Any]]:
        return [
            {
                "type": "PushEvent",
                "repo": {"name": "octocat/a"},
                "created_at": "2026-10-07T10:00:00Z",
                "payload": {"ref": "refs/heads/main", "commits": [{"sha": "x"}]},
            }
        ]


def test_build_profile_context() -> None:
    context = build_profile_context(_StubClient(), "octocat", max_lines=5, sparkline_days=7)
    user = context["user"]
    assert user.login == "octocat"
    assert context["total_stars"] == 5
    assert [lang.name for lang in context["languages"]] == ["Python"]
    assert len(context["activity_lines"]) == 1
    assert context["sparkline_svg"].startswith("<svg ")
    assert context["sparkline_days"] == 7
    assert "refreshed_at" in context
