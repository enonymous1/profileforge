"""Typed summaries derived from the GitHub API for profile rendering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from profileforge.github.client import GitHubClient


@dataclass(frozen=True)
class UserSummary:
    """The fields of a GitHub user profile that the README shows."""

    login: str
    name: str
    bio: str
    html_url: str
    avatar_url: str
    public_repos: int
    followers: int
    following: int


@dataclass(frozen=True)
class RepoSummary:
    """The fields of a GitHub repo that feed stars/language stats."""

    name: str
    full_name: str
    html_url: str
    description: str
    stargazers_count: int
    language: str | None
    fork: bool
    archived: bool
    forks_count: int = 0
    topics: tuple[str, ...] = ()
    updated_at: str = ""


@dataclass(frozen=True)
class LanguageStat:
    """One language's share of a user's repos."""

    name: str
    repos: int
    stars: int
    share: float  # percentage of repos with a detected language


def _str(data: Mapping[str, Any], key: str, default: str = "") -> str:
    value = data.get(key, default)
    return str(value) if value is not None else default


def _int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key, 0)
    return value if isinstance(value, int) else 0


def parse_user_summary(data: Mapping[str, Any]) -> UserSummary:
    """Parse a ``GET /users/{username}`` response body."""
    login = _str(data, "login")
    return UserSummary(
        login=login,
        name=_str(data, "name") or login,
        bio=_str(data, "bio"),
        html_url=_str(data, "html_url"),
        avatar_url=_str(data, "avatar_url"),
        public_repos=_int(data, "public_repos"),
        followers=_int(data, "followers"),
        following=_int(data, "following"),
    )


def parse_repo_summary(data: Mapping[str, Any]) -> RepoSummary:
    """Parse one entry of a ``GET /users/{username}/repos`` response."""
    language = data.get("language")
    topics = data.get("topics") or ()
    return RepoSummary(
        name=_str(data, "name"),
        full_name=_str(data, "full_name"),
        html_url=_str(data, "html_url"),
        description=_str(data, "description"),
        stargazers_count=_int(data, "stargazers_count"),
        language=str(language) if language is not None else None,
        fork=bool(data.get("fork", False)),
        archived=bool(data.get("archived", False)),
        forks_count=_int(data, "forks_count"),
        topics=tuple(str(topic) for topic in topics),
        updated_at=_str(data, "updated_at"),
    )


def fetch_user_summary(client: GitHubClient, username: str) -> UserSummary:
    """Fetch and parse a user's public profile."""
    return parse_user_summary(client.fetch_user(username))


def fetch_repo_summaries(client: GitHubClient, username: str) -> list[RepoSummary]:
    """Fetch and parse a user's repos (most recently updated first)."""
    return [parse_repo_summary(raw) for raw in client.fetch_repos(username)]


def fetch_code_share(
    client: GitHubClient, username: str, repos: Sequence[RepoSummary]
) -> CodeShare:
    """Aggregate language bytes across a user's non-fork repos.

    Takes already-fetched repo summaries so callers fetch the repo list
    once; forks are excluded from the count and reported separately.
    """
    counted = [repo for repo in repos if not repo.fork]
    per_repo = [client.fetch_repo_languages(username, repo.name) for repo in counted]
    return summarize_code_share(per_repo, excluded_forks=len(repos) - len(counted))


def total_stars(repos: Sequence[RepoSummary]) -> int:
    """Sum stargazers across repos (including forks, like GitHub's own total)."""
    return sum(repo.stargazers_count for repo in repos)


def summarize_languages(repos: Sequence[RepoSummary], *, limit: int = 8) -> list[LanguageStat]:
    """Rank primary languages by repo count (stars break ties).

    Only repos with a detected primary language count toward shares.
    """
    counts: dict[str, dict[str, int]] = {}
    for repo in repos:
        if not repo.language:
            continue
        entry = counts.setdefault(repo.language, {"repos": 0, "stars": 0})
        entry["repos"] += 1
        entry["stars"] += repo.stargazers_count
    total = sum(entry["repos"] for entry in counts.values())
    stats = [
        LanguageStat(
            name=name,
            repos=entry["repos"],
            stars=entry["stars"],
            share=100.0 * entry["repos"] / total if total else 0.0,
        )
        for name, entry in counts.items()
    ]
    stats.sort(key=lambda stat: (-stat.repos, -stat.stars, stat.name))
    return stats[:limit]


@dataclass(frozen=True)
class LanguageBytes:
    """One language's share of code by bytes across the counted repos."""

    name: str
    bytes: int
    repos: int  # repos containing code in this language
    share: float  # percentage of total bytes


@dataclass(frozen=True)
class CodeShare:
    """A user's code footprint: language bytes summed across repos."""

    total_bytes: int
    repo_count: int
    excluded_forks: int
    language_count: int  # distinct languages before top-N + Other collapsing
    languages: tuple[LanguageBytes, ...]  # ranked by bytes, tail as "Other"


def summarize_code_share(
    languages_by_repo: Sequence[Mapping[str, int]],
    *,
    excluded_forks: int = 0,
    limit: int = 10,
) -> CodeShare:
    """Aggregate per-repo language bytes into a code share.

    Each mapping is one counted repo's ``{language: bytes}`` (as returned by
    :meth:`GitHubClient.fetch_repo_languages`); the caller filters forks.
    A repo counts toward a language when it holds more than zero bytes of
    it, so repos routinely count toward several languages. Languages past
    ``limit`` collapse into a single ``"Other"`` row; shares are percentages
    of total bytes.
    """
    totals: dict[str, int] = {}
    repo_counts: dict[str, int] = {}
    for per_repo in languages_by_repo:
        for name, value in per_repo.items():
            if value <= 0:
                continue
            totals[name] = totals.get(name, 0) + value
            repo_counts[name] = repo_counts.get(name, 0) + 1
    total_bytes = sum(totals.values())
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    head, tail = ranked[:limit], ranked[limit:]

    def _stat(name: str, nbytes: int, repos: int) -> LanguageBytes:
        return LanguageBytes(
            name=name,
            bytes=nbytes,
            repos=repos,
            share=100.0 * nbytes / total_bytes if total_bytes else 0.0,
        )

    languages = [_stat(name, nbytes, repo_counts[name]) for name, nbytes in head]
    if tail:
        tail_repos = {
            index
            for index, per_repo in enumerate(languages_by_repo)
            if any(per_repo.get(name, 0) > 0 for name, _ in tail)
        }
        languages.append(_stat("Other", sum(nbytes for _, nbytes in tail), len(tail_repos)))
    return CodeShare(
        total_bytes=total_bytes,
        repo_count=len(languages_by_repo),
        excluded_forks=excluded_forks,
        language_count=len(totals),
        languages=tuple(languages),
    )
