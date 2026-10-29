"""Tests for profileforge.profile.stats."""

from __future__ import annotations

import pytest

from profileforge.profile.stats import (
    CodeShare,
    LanguageStat,
    RepoSummary,
    UserSummary,
    parse_repo_summary,
    parse_user_summary,
    summarize_code_share,
    summarize_languages,
    total_stars,
)

_RAW_USER = {
    "login": "octocat",
    "name": "Octo Cat",
    "bio": "I build things",
    "html_url": "https://github.com/octocat",
    "avatar_url": "https://avatars.example/u/1",
    "public_repos": 8,
    "followers": 100,
    "following": 5,
}


def _repo(name: str, language: str | None, stars: int) -> RepoSummary:
    return RepoSummary(
        name=name,
        full_name=f"octocat/{name}",
        html_url=f"https://github.com/octocat/{name}",
        description="",
        stargazers_count=stars,
        language=language,
        fork=False,
        archived=False,
    )


def test_parse_user_summary() -> None:
    user = parse_user_summary(_RAW_USER)
    assert isinstance(user, UserSummary)
    assert user.login == "octocat"
    assert user.name == "Octo Cat"
    assert user.bio == "I build things"
    assert user.public_repos == 8
    assert user.followers == 100


def test_parse_user_summary_defaults() -> None:
    user = parse_user_summary({"login": "octocat"})
    assert user.name == "octocat"
    assert user.bio == ""
    assert user.public_repos == 0


def test_parse_repo_summary() -> None:
    repo = parse_repo_summary(
        {
            "name": "hello",
            "full_name": "octocat/hello",
            "html_url": "https://github.com/octocat/hello",
            "description": None,
            "stargazers_count": 42,
            "language": "Python",
            "fork": False,
            "archived": False,
        }
    )
    assert repo.language == "Python"
    assert repo.stargazers_count == 42
    assert repo.description == ""


def test_summarize_languages() -> None:
    repos = [
        _repo("a", "Python", 10),
        _repo("b", "Python", 5),
        _repo("c", "Rust", 100),
        _repo("d", None, 3),
    ]
    stats = summarize_languages(repos)
    assert [s.name for s in stats] == ["Python", "Rust"]
    python = stats[0]
    assert isinstance(python, LanguageStat)
    assert python.repos == 2
    assert python.stars == 15
    assert python.share == pytest.approx(200 / 3)
    assert stats[1].share == pytest.approx(100 / 3)


def test_summarize_languages_empty() -> None:
    assert summarize_languages([]) == []
    assert summarize_languages([_repo("a", None, 0)]) == []


def test_summarize_languages_limit() -> None:
    repos = [_repo(f"r{i}", f"Lang{i}", i) for i in range(20)]
    assert len(summarize_languages(repos)) == 8


def test_total_stars() -> None:
    repos = [_repo("a", "Python", 10), _repo("b", "Rust", 5)]
    assert total_stars(repos) == 15
    assert total_stars([]) == 0


def test_summarize_code_share() -> None:
    share = summarize_code_share(
        [
            {"Python": 800, "Go": 100},
            {"Python": 200},
            {"Go": 100, "Rust": 50},
        ],
        excluded_forks=1,
    )
    assert isinstance(share, CodeShare)
    assert share.total_bytes == 1250
    assert share.repo_count == 3
    assert share.excluded_forks == 1
    assert share.language_count == 3
    assert [(lang.name, lang.bytes, lang.repos) for lang in share.languages] == [
        ("Python", 1000, 2),
        ("Go", 200, 2),
        ("Rust", 50, 1),
    ]
    assert share.languages[0].share == pytest.approx(80.0)
    assert share.languages[2].share == pytest.approx(4.0)


def test_summarize_code_share_collapses_tail_into_other() -> None:
    per_repo = [{f"Lang{i}": 100 - i} for i in range(12)]
    share = summarize_code_share(per_repo, limit=10)
    assert [lang.name for lang in share.languages] == [f"Lang{i}" for i in range(10)] + ["Other"]
    other = share.languages[-1]
    assert other.bytes == 100 - 10 + 100 - 11
    assert other.repos == 2
    assert other.share == pytest.approx(100.0 * other.bytes / share.total_bytes)
    assert share.language_count == 12


def test_summarize_code_share_ties_break_alphabetically() -> None:
    share = summarize_code_share([{"Zeta": 100, "Alpha": 100}])
    assert [lang.name for lang in share.languages] == ["Alpha", "Zeta"]


def test_summarize_code_share_ignores_non_positive_bytes() -> None:
    share = summarize_code_share([{"Python": 100, "Empty": 0, "Neg": -5}])
    assert [lang.name for lang in share.languages] == ["Python"]
    assert share.total_bytes == 100
    assert share.language_count == 1


def test_summarize_code_share_empty() -> None:
    share = summarize_code_share([])
    assert share.total_bytes == 0
    assert share.repo_count == 0
    assert share.language_count == 0
    assert share.languages == ()
