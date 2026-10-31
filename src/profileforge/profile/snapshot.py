"""One shared fetch for the README renderer and the site builder.

Both consumers used to fetch user + repos + events independently and
derive activity lines and a sparkline from them — and had already
drifted (the README path fetched per-repo language bytes; the site path
did not). A new data source is fetched here, exactly once, and each
consumer adds only its own presentation on top.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from profileforge.github.activity import build_activity_lines
from profileforge.github.client import GitHubClient
from profileforge.github.models import GitHubEvent, parse_event
from profileforge.profile.sparkline import build_daily_counts, sparkline_start
from profileforge.profile.stats import (
    RepoSummary,
    UserSummary,
    fetch_repo_summaries,
    fetch_user_summary,
)


@dataclass(frozen=True)
class ProfileSnapshot:
    """Live data both the README renderer and the site builder consume."""

    user: UserSummary
    repos: tuple[RepoSummary, ...]
    events: tuple[GitHubEvent, ...]
    activity_lines: tuple[str, ...]
    daily_counts: tuple[int, ...]
    window_start: date


def fetch_profile_snapshot(
    client: GitHubClient,
    username: str,
    *,
    max_lines: int,
    sparkline_days: int = 30,
    now: datetime | None = None,
) -> ProfileSnapshot:
    """Fetch user, repos, and events once; derive activity + sparkline."""
    moment = now or datetime.now(UTC)
    user = fetch_user_summary(client, username)
    repos = tuple(fetch_repo_summaries(client, username))
    raw_events = client.fetch_public_events(username, per_page=100, max_pages=3)
    events = tuple(parse_event(raw) for raw in raw_events)
    start = sparkline_start(sparkline_days, now=moment)
    return ProfileSnapshot(
        user=user,
        repos=repos,
        events=events,
        activity_lines=tuple(
            build_activity_lines(raw_events, username=username, max_lines=max_lines)
        ),
        daily_counts=tuple(build_daily_counts(events, sparkline_days, now=moment)),
        window_start=start,
    )
