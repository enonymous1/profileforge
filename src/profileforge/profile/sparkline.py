"""Locally generated activity sparklines (no third-party image service).

SVG bars for the portfolio site, plain-text block characters for READMEs,
where GitHub strips inline SVG.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from profileforge.github.models import GitHubEvent

_BAR_WIDTH = 6
_BAR_GAP = 2
_HEIGHT = 40
_BAR_COLOR = "#39d353"
_EMPTY_COLOR = "#30363d"


def build_daily_counts(
    events: Sequence[GitHubEvent],
    days: int,
    *,
    now: datetime | None = None,
) -> list[int]:
    """Bucket events per UTC day over the trailing ``days`` days.

    Returns oldest-first counts; events without a timestamp or outside the
    window are ignored.

    Raises:
        ValueError: ``days`` is not positive.
    """
    if days < 1:
        raise ValueError("days must be positive")
    today = (now or datetime.now(UTC)).date()
    start = today - timedelta(days=days - 1)
    counts = [0] * days
    for event in events:
        if event.created_at is None:
            continue
        day = event.created_at.astimezone(UTC).date()
        index = (day - start).days
        if 0 <= index < days:
            counts[index] += 1
    return counts


def sparkline_start(days: int, *, now: datetime | None = None) -> date:
    """First date covered by :func:`build_daily_counts` (for bar labels)."""
    if days < 1:
        raise ValueError("days must be positive")
    today = (now or datetime.now(UTC)).date()
    return today - timedelta(days=days - 1)


def render_sparkline_svg(
    counts: Sequence[int],
    start: date,
    *,
    label: str = "GitHub activity",
) -> str:
    """Render daily counts as an accessible SVG bar chart.

    Args:
        counts: Oldest-first per-day counts.
        start: Date of the first count (for per-bar tooltips).
        label: Accessible name for the chart.
    """
    total_width = len(counts) * (_BAR_WIDTH + _BAR_GAP) - _BAR_GAP if counts else 0
    peak = max(counts) if counts else 0
    bars: list[str] = []
    for index, count in enumerate(counts):
        day = (start + timedelta(days=index)).isoformat()
        if peak:
            bar_height = max(2, round(count / peak * _HEIGHT)) if count else 2
            color = _BAR_COLOR if count else _EMPTY_COLOR
        else:
            bar_height = 2
            color = _EMPTY_COLOR
        x = index * (_BAR_WIDTH + _BAR_GAP)
        y = _HEIGHT - bar_height
        bars.append(
            f'<rect x="{x}" y="{y}" width="{_BAR_WIDTH}" height="{bar_height}" '
            f'rx="1.5" fill="{color}"><title>{day}: {count} event(s)</title></rect>'
        )
    bars_svg = "".join(bars)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" '
        f'height="{_HEIGHT}" role="img" aria-label="{label}">'
        f"<title>{label}</title>{bars_svg}</svg>"
    )


_TEXT_LEVELS = "▁▂▃▄▅▆▇█"


def render_sparkline_text(counts: Sequence[int], start: date) -> str:
    """Render daily counts as plain-text block characters plus a summary line.

    The two returned lines are meant for a fenced code block in a README,
    where GitHub strips the inline-SVG equivalent. Each character is one
    day, oldest first, scaled against the busiest day; empty days are the
    lowest block. The summary names the window, the total event count, and
    the busiest day (earliest on ties); with no events at all the busiest
    clause is omitted.
    """
    peak = max(counts) if counts else 0
    if peak:
        chars = "".join(
            _TEXT_LEVELS[min(len(_TEXT_LEVELS) - 1, round(count / peak * 7))] for count in counts
        )
    else:
        chars = _TEXT_LEVELS[0] * len(counts)
    total = sum(counts)
    end = start + timedelta(days=len(counts) - 1) if counts else start
    window = f"{start:%b %d} - {end:%b %d, %Y}"
    if not counts or total == 0:
        return f"{chars}\n{window} · 0 public events"
    busiest_index = counts.index(peak)
    busiest = start + timedelta(days=busiest_index)
    noun = "event" if total == 1 else "events"
    return f"{chars}\n{window} · {total} public {noun} · busiest day {busiest:%b %d} ({peak})"
