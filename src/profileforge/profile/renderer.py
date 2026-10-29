"""Jinja2 README rendering and the stats marker-section body."""

from __future__ import annotations

import html
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import jinja2

from profileforge.github.activity import build_activity_lines
from profileforge.github.client import GitHubClient
from profileforge.github.models import parse_event
from profileforge.profile.sparkline import (
    build_daily_counts,
    render_sparkline_svg,
    sparkline_start,
)
from profileforge.profile.stats import (
    LanguageStat,
    fetch_repo_summaries,
    fetch_user_summary,
    summarize_languages,
    total_stars,
)

logger = logging.getLogger(__name__)

_TEMPLATE_ENV = jinja2.Environment(
    loader=jinja2.PackageLoader("profileforge.profile", "templates"),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_top_languages(languages: Sequence[LanguageStat]) -> str:
    """Render top languages as inline HTML bars (no external image service)."""
    lines = []
    for lang in languages:
        bar_width = round(lang.share * 2)  # 100% -> 200px
        lines.append(
            f"<div><code>{html.escape(lang.name)}</code> "
            f'<span style="display:inline-block;background:#0969da;height:8px;'
            f'width:{bar_width}px;border-radius:4px;vertical-align:middle;"></span> '
            f"{lang.share:.0f}%</div>"
        )
    return "\n".join(lines)


def render_stats_body(
    languages: Sequence[LanguageStat], sparkline_svg: str, sparkline_days: int
) -> str:
    """Render the ``stats`` marker section: sparkline + top languages."""
    return (
        f"{sparkline_svg}\n"
        f"\n"
        f"<sub>Activity over the last {sparkline_days} days</sub>\n"
        f"\n"
        f"#### Top languages\n"
        f"\n"
        f"{render_top_languages(languages)}"
    )


def build_profile_context(
    client: GitHubClient,
    username: str,
    *,
    max_lines: int,
    sparkline_days: int = 30,
) -> dict[str, Any]:
    """Fetch live data and assemble the README template context."""
    user = fetch_user_summary(client, username)
    repos = fetch_repo_summaries(client, username)
    raw_events = client.fetch_public_events(username, per_page=100, max_pages=3)
    events = [parse_event(raw) for raw in raw_events]
    languages = summarize_languages(repos)
    start = sparkline_start(sparkline_days)
    sparkline_svg = render_sparkline_svg(build_daily_counts(events, sparkline_days), start)
    activity_lines = build_activity_lines(raw_events, username=username, max_lines=max_lines)
    context: dict[str, Any] = {
        "user": user,
        "total_stars": total_stars(repos),
        "languages": languages,
        "activity_lines": activity_lines,
        "sparkline_svg": sparkline_svg,
        "render_stats_body": render_stats_body,
        "sparkline_days": sparkline_days,
        "refreshed_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
    }
    logger.info(
        "Built profile context for %s: %d repos, %d languages, %d activity lines",
        username,
        len(repos),
        len(languages),
        len(activity_lines),
    )
    return context


def render_readme(context: Mapping[str, Any]) -> str:
    """Render the profile README template with the given context."""
    return _TEMPLATE_ENV.get_template("readme.md.j2").render(context)
