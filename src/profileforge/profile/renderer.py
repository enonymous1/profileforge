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
    render_sparkline_text,
    sparkline_start,
)
from profileforge.profile.stats import (
    CodeShare,
    LanguageBytes,
    LanguageStat,
    fetch_code_share,
    fetch_repo_summaries,
    fetch_user_summary,
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


_BAR_SCALE_DIVISOR = 5  # one block per 5 share points, so 100% renders 20 blocks


def _bar_blocks(share: float) -> int:
    """Block count for a language bar: at least one block when present."""
    return max(1, round(share / _BAR_SCALE_DIVISOR))


def render_language_line(stat: LanguageBytes) -> str:
    """One fixed-width language row: name, bar, share, bytes, repo count."""
    bar = "█" * _bar_blocks(stat.share)
    repos_noun = "repo" if stat.repos == 1 else "repos"
    return (
        f"{stat.name:<12}{bar:<21}{stat.share:>4.1f}%  "
        f"{stat.bytes:,} bytes · {stat.repos} {repos_noun}"
    )


def render_stats_body(share: CodeShare, sparkline_text: str, as_of: str) -> str:
    """Render the ``stats`` marker section as plain text.

    GitHub strips inline SVG and styled HTML from READMEs, so the section
    is fenced code blocks only: an as-of header, the activity sparkline,
    and the top-languages bars. Line counts are not available from the API,
    so the header claims bytes, repos, and languages only.
    """
    fork_note = (
        f" ({share.excluded_forks} fork{'s' if share.excluded_forks != 1 else ''} excluded)"
        if share.excluded_forks
        else ""
    )
    repo_noun = "repo" if share.repo_count == 1 else "repos"
    lang_noun = "language" if share.language_count == 1 else "languages"
    header = (
        f"As of {as_of}: **{share.repo_count} public {repo_noun} counted**{fork_note} · "
        f"**{share.total_bytes:,} bytes of code** across "
        f"**{share.language_count} {lang_noun}**. "
        f"Shares below are share of code by bytes — not share of repos."
    )
    if share.languages:
        lang_lines = "\n".join(render_language_line(lang) for lang in share.languages)
    else:
        lang_lines = "No language data available."
    return f"{header}\n\n```\n{sparkline_text}\n```\n\n#### Top languages\n\n```\n{lang_lines}\n```"


def build_profile_context(
    client: GitHubClient,
    username: str,
    *,
    max_lines: int,
    sparkline_days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fetch live data and assemble the README template context."""
    moment = now or datetime.now(UTC)
    user = fetch_user_summary(client, username)
    repos = fetch_repo_summaries(client, username)
    share = fetch_code_share(client, username, repos)
    raw_events = client.fetch_public_events(username, per_page=100, max_pages=3)
    events = [parse_event(raw) for raw in raw_events]
    start = sparkline_start(sparkline_days, now=moment)
    sparkline_text = render_sparkline_text(
        build_daily_counts(events, sparkline_days, now=moment), start
    )
    activity_lines = build_activity_lines(raw_events, username=username, max_lines=max_lines)
    context: dict[str, Any] = {
        "user": user,
        "total_stars": total_stars(repos),
        "code_share": share,
        "activity_lines": activity_lines,
        "sparkline_text": sparkline_text,
        "stats_as_of": moment.strftime("%b %d, %Y"),
        "render_stats_body": render_stats_body,
        "sparkline_days": sparkline_days,
        "refreshed_at": moment.strftime("%Y-%m-%d %H:%M"),
    }
    logger.info(
        "Built profile context for %s: %d repos, %d languages, %d activity lines",
        username,
        len(repos),
        share.language_count,
        len(activity_lines),
    )
    return context


def render_readme(context: Mapping[str, Any]) -> str:
    """Render the profile README template with the given context."""
    return _TEMPLATE_ENV.get_template("readme.md.j2").render(context)
