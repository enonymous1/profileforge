"""Activity-feed pipeline: raw GitHub events become formatted activity lines.

Parsing, filtering, push-collapsing, and formatting live here; the
``sync-activity`` CLI command wires this to the API client and README updater.

Deliberate differences from the legacy ``build_activity_lines``:
- Push lines carry no commit count. The legacy code printed one, but the
  public events API supplies no per-push count (neither a ``commits`` array
  nor ``size``), so the legacy line read "Pushed 0 commits" on live data.
  Rendering no count stays true; a count would have to come from a separate
  compare-API call per push.
- Collapse keeps one line per repo+branch: the newest push. The legacy code
  formatted each push *before* merging later pushes into it, so its
  "collapse" never took effect in the output and older pushes were silently
  dropped. This pipeline never mutates the raw API payloads in place.
- The collapse key uses the *rendered* branch name, so a PushEvent without a
  ``ref`` groups with ``main``. (The legacy key used ``""`` while rendering
  ``main`` — an inconsistency that could split one logical push stream.)
- Skip lists and the profile-repo exclusion are parameters, not globals.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping, Sequence
from typing import Any

from profileforge.github.formatters import format_event
from profileforge.github.models import GitHubEvent, PushPayload, parse_event

logger = logging.getLogger(__name__)

DEFAULT_SKIP_EVENT_TYPES: frozenset[str] = frozenset({"WatchEvent", "DeleteEvent", "MemberEvent"})


def build_activity_lines(
    raw_events: Sequence[Mapping[str, Any]],
    *,
    username: str,
    max_lines: int,
    skip_event_types: Collection[str] = DEFAULT_SKIP_EVENT_TYPES,
) -> list[str]:
    """Build formatted activity lines from raw GitHub event dicts.

    Events are parsed, filtered (skipped types, the user's own profile repo),
    collapsed (multiple pushes to one repo+branch become a single line), and
    formatted, newest first, capped at ``max_lines``.

    Raises:
        ValueError: ``username`` is blank or ``max_lines`` is not positive.
    """
    if not username or not username.strip():
        raise ValueError("username must be a non-empty string")
    if max_lines < 1:
        raise ValueError("max_lines must be positive")
    profile_repo = f"{username}/{username}"

    events: list[GitHubEvent] = []
    for raw in raw_events:
        event = parse_event(raw)
        if event.type in skip_event_types:
            continue
        if event.repo_name == profile_repo:
            continue
        events.append(event)

    lines: list[str] = []
    for event in _collapse_pushes(events):
        line = format_event(event)
        if line is not None:
            lines.append(line)
        if len(lines) >= max_lines:
            break
    logger.debug("Built %d activity line(s) from %d raw event(s)", len(lines), len(raw_events))
    return lines


def _collapse_pushes(events: list[GitHubEvent]) -> list[GitHubEvent]:
    """Keep only the newest push per repo+branch; other events pass through.

    Callers must pass events newest-first (the public events API returns
    them that way); the first push seen per repo+branch wins. Passing
    unsorted events silently changes which push survives.
    """
    collapsed: list[GitHubEvent] = []
    seen_push_keys: set[str] = set()
    for event in events:
        payload = event.payload
        if event.type == "PushEvent" and isinstance(payload, PushPayload):
            key = f"{event.repo_name}:{payload.branch}"
            if key in seen_push_keys:
                continue
            seen_push_keys.add(key)
        collapsed.append(event)
    return collapsed
