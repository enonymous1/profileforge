"""Tests for profileforge.profile.renderer."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from profileforge.github.client import GitHubClient
from profileforge.profile.renderer import (
    build_profile_context,
    render_readme,
    render_stats_body,
    render_top_languages,
)
from profileforge.profile.stats import CodeShare, LanguageBytes, LanguageStat, UserSummary


def _code_share_fixture() -> CodeShare:
    """The Oct 29, 2026 clone audit's numbers, as API-shaped aggregates."""
    total = 5_475_378
    rows = [
        ("Python", 3_389_611, 34),
        ("JavaScript", 527_963, 10),
        ("Kotlin", 431_793, 11),
        ("HTML", 249_015, 14),
        ("Swift", 185_544, 6),
        ("CSS", 176_483, 8),
        ("PowerShell", 164_948, 3),
        ("XML", 160_777, 12),
        ("TypeScript", 81_877, 2),
        ("Svelte", 34_583, 1),
        ("Other", 72_784, 6),
    ]
    return CodeShare(
        total_bytes=total,
        repo_count=61,
        excluded_forks=1,
        language_count=16,
        languages=tuple(
            LanguageBytes(name=name, bytes=nbytes, repos=repos, share=100.0 * nbytes / total)
            for name, nbytes, repos in rows
        ),
    )


_SPARKLINE_TEXT = (
    "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▃▂█▄▁▁\n"
    "Sep 30 - Oct 29, 2026 · 81 public events · busiest day Oct 26 (46)"
)


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
        "code_share": _code_share_fixture(),
        "activity_lines": ["📦 Pushed 1 commit to [`o/p`](https://github.com/o/p)"],
        "sparkline_text": _SPARKLINE_TEXT,
        "stats_as_of": "Oct 29, 2026",
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
    assert "#### Top languages" in rendered
    assert "Python      ████████████" in rendered
    assert "<svg" not in rendered
    assert "<!--END_SECTION:stats-->" in rendered
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


def test_render_stats_body_matches_profile_readme_format() -> None:
    """Golden test: the generated body matches the profile README's section."""
    body = render_stats_body(_code_share_fixture(), _SPARKLINE_TEXT, "Oct 29, 2026")
    assert body == (
        "As of Oct 29, 2026: **61 public repos counted** (1 fork excluded) · "
        "**5,475,378 bytes of code** across **16 languages**. "
        "Shares below are share of code by bytes — not share of repos.\n"
        "\n"
        "```\n"
        "▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▃▂█▄▁▁\n"
        "Sep 30 - Oct 29, 2026 · 81 public events · busiest day Oct 26 (46)\n"
        "```\n"
        "\n"
        "#### Top languages\n"
        "\n"
        "```\n"
        "Python      ████████████         61.9%  3,389,611 bytes · 34 repos\n"
        "JavaScript  ██                    9.6%  527,963 bytes · 10 repos\n"
        "Kotlin      ██                    7.9%  431,793 bytes · 11 repos\n"
        "HTML        █                     4.5%  249,015 bytes · 14 repos\n"
        "Swift       █                     3.4%  185,544 bytes · 6 repos\n"
        "CSS         █                     3.2%  176,483 bytes · 8 repos\n"
        "PowerShell  █                     3.0%  164,948 bytes · 3 repos\n"
        "XML         █                     2.9%  160,777 bytes · 12 repos\n"
        "TypeScript  █                     1.5%  81,877 bytes · 2 repos\n"
        "Svelte      █                     0.6%  34,583 bytes · 1 repo\n"
        "Other       █                     1.3%  72,784 bytes · 6 repos\n"
        "```"
    )


def test_render_stats_body_empty_share() -> None:
    body = render_stats_body(
        CodeShare(
            total_bytes=0,
            repo_count=0,
            excluded_forks=0,
            language_count=0,
            languages=(),
        ),
        "▁▁▁\nOct 05 - Oct 07, 2026 · 0 public events",
        "Oct 07, 2026",
    )
    assert "0 public repos counted" in body
    assert "No language data available." in body
    assert "<svg" not in body


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

    def fetch_repo_languages(self, owner: str, repo: str) -> dict[str, int]:
        assert owner == "octocat"
        assert repo == "a"
        return {"Python": 100}


def test_build_profile_context() -> None:
    now = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    context = build_profile_context(
        _StubClient(), "octocat", max_lines=5, sparkline_days=7, now=now
    )
    user = context["user"]
    assert user.login == "octocat"
    assert context["total_stars"] == 5
    share = context["code_share"]
    assert isinstance(share, CodeShare)
    assert share.total_bytes == 100
    assert share.repo_count == 1
    assert share.language_count == 1
    assert [lang.name for lang in share.languages] == ["Python"]
    assert len(context["activity_lines"]) == 1
    assert context["sparkline_text"].startswith("▁▁▁▁▁▁█")
    assert "1 public event" in context["sparkline_text"]
    assert context["stats_as_of"] == "Oct 07, 2026"
    assert context["sparkline_days"] == 7
    assert "refreshed_at" in context
