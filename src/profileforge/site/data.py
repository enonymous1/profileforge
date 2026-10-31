"""Site data model assembled from the shared profile pipeline."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from profileforge.github.client import GitHubClient
from profileforge.profile.snapshot import fetch_profile_snapshot
from profileforge.profile.sparkline import render_sparkline_svg
from profileforge.profile.stats import (
    LanguageStat,
    RepoSummary,
    UserSummary,
    summarize_languages,
    total_stars,
)
from profileforge.site.html import markdown_inline_to_html

logger = logging.getLogger(__name__)

# GitHub linguist-ish colors for the most common languages; anything else
# falls back to a neutral gray.
LANGUAGE_COLORS: dict[str, str] = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Rust": "#dea584",
    "Go": "#00ADD8",
    "Java": "#b07219",
    "C": "#555555",
    "C++": "#f34b7d",
    "C#": "#178600",
    "Ruby": "#701516",
    "PHP": "#4F5D95",
    "Swift": "#F05138",
    "Kotlin": "#A97BFF",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Shell": "#89e051",
    "Jupyter Notebook": "#DA5B0B",
    "Vue": "#41b883",
    "Dart": "#00B4AB",
}

_DEFAULT_LANGUAGE_COLOR = "#8b949e"


def language_color(language: str | None) -> str:
    """Dot color for a language name."""
    if language is None:
        return _DEFAULT_LANGUAGE_COLOR
    return LANGUAGE_COLORS.get(language, _DEFAULT_LANGUAGE_COLOR)


@dataclass(frozen=True)
class ProjectCard:
    """One repository showcased on the portfolio page."""

    name: str
    full_name: str
    html_url: str
    description: str
    language: str | None
    language_color: str
    stargazers_count: int
    forks_count: int
    topics: tuple[str, ...]
    updated_at: str


@dataclass(frozen=True)
class SiteData:
    """Everything the site builder needs (also serialized to profile.json)."""

    user: UserSummary
    total_stars: int
    languages: tuple[LanguageStat, ...]
    projects: tuple[ProjectCard, ...]
    activity_lines: tuple[str, ...]
    activity_html: tuple[str, ...]
    sparkline_svg: str
    sparkline_days: int
    generated_at: str


def select_projects(repos: Sequence[RepoSummary], *, limit: int = 6) -> list[ProjectCard]:
    """Pick showcase repos: no forks/archived, ranked by stars.

    Raises:
        ValueError: ``limit`` is not positive.
    """
    if limit < 1:
        raise ValueError("limit must be positive")
    showcase = [repo for repo in repos if not repo.fork and not repo.archived]
    showcase.sort(key=lambda repo: (-repo.stargazers_count, repo.name))
    return [
        ProjectCard(
            name=repo.name,
            full_name=repo.full_name,
            html_url=repo.html_url,
            description=repo.description,
            language=repo.language,
            language_color=language_color(repo.language),
            stargazers_count=repo.stargazers_count,
            forks_count=repo.forks_count,
            topics=repo.topics,
            updated_at=repo.updated_at,
        )
        for repo in showcase[:limit]
    ]


def assemble_site_data(
    client: GitHubClient,
    username: str,
    *,
    max_lines: int,
    sparkline_days: int = 30,
    projects_limit: int = 6,
) -> SiteData:
    """Fetch live data and assemble the site model.

    The fetch pipeline is shared with the README renderer via
    ``fetch_profile_snapshot``; this function adds only site presentation
    (project cards, language ranking, activity HTML, SVG sparkline).
    """
    snapshot = fetch_profile_snapshot(
        client, username, max_lines=max_lines, sparkline_days=sparkline_days
    )
    data = SiteData(
        user=snapshot.user,
        total_stars=total_stars(snapshot.repos),
        languages=tuple(summarize_languages(snapshot.repos)),
        projects=tuple(select_projects(snapshot.repos, limit=projects_limit)),
        activity_lines=snapshot.activity_lines,
        activity_html=tuple(markdown_inline_to_html(line) for line in snapshot.activity_lines),
        sparkline_svg=render_sparkline_svg(snapshot.daily_counts, snapshot.window_start),
        sparkline_days=sparkline_days,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
    )
    logger.info(
        "Assembled site data for %s: %d projects, %d activity lines",
        username,
        len(data.projects),
        len(data.activity_lines),
    )
    return data
