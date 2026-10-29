"""Render typed GitHub events as Markdown activity lines.

Each event type maps to exactly one formatter function in :data:`FORMATTERS`.
To support a new event type, write a small function and register it with
:func:`register_formatter` — the dispatch logic never changes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from profileforge.github.models import (
    CreatePayload,
    ForkPayload,
    GitHubEvent,
    IssueCommentPayload,
    IssuePayload,
    PullRequestPayload,
    PushPayload,
    ReleasePayload,
)

EVENT_ICONS: dict[str, str] = {
    "PushEvent": "📦",
    "CreateEvent": "🌱",
    "ForkEvent": "🍴",
    "WatchEvent": "⭐",
    "IssuesEvent": "🐛",
    "IssueCommentEvent": "💬",
    "PullRequestEvent": "🔀",
    "ReleaseEvent": "🚀",
    "DeleteEvent": "🗑️",
    "PublicEvent": "📢",
}

DEFAULT_ICON = "🔧"

Formatter = Callable[[GitHubEvent], str]

_P = TypeVar("_P")


def _payload(event: GitHubEvent, kind: type[_P]) -> _P:
    """Narrow an event's payload, raising a clear error on mismatch."""
    payload = event.payload
    if not isinstance(payload, kind):
        raise TypeError(
            f"Formatter for {event.type!r} received "
            f"{type(payload).__name__}, expected {kind.__name__}"
        )
    return payload


def _format_push(event: GitHubEvent) -> str:
    # Deliberately no commit count: the public events API carries no
    # per-push count (neither a ``commits`` array nor ``size``), so any
    # number rendered here would be fabricated. The legacy script printed
    # one and showed 0 on live data; this format stays true instead.
    payload = _payload(event, PushPayload)
    return (
        f"📦 Pushed to [`{event.repo_name}`]({event.repo_url}) "
        f"on `{payload.branch}` — {event.date_str}"
    )


def _format_create(event: GitHubEvent) -> str:
    payload = _payload(event, CreatePayload)
    if payload.ref_type == "repository":
        return f"🌱 Created repository [`{event.repo_name}`]({event.repo_url}) — {event.date_str}"
    return (
        f"🌱 Created {payload.ref_type} `{payload.ref}` in "
        f"[`{event.repo_name}`]({event.repo_url}) — {event.date_str}"
    )


def _format_fork(event: GitHubEvent) -> str:
    payload = _payload(event, ForkPayload)
    return (
        f"🍴 Forked [`{payload.forkee_full_name}`]"
        f"(https://github.com/{payload.forkee_full_name}) — {event.date_str}"
    )


def _format_issues(event: GitHubEvent) -> str:
    payload = _payload(event, IssuePayload)
    return (
        f"🐛 {payload.action.capitalize()} issue [{payload.title}]({payload.url}) "
        f"in [`{event.repo_name}`]({event.repo_url}) — {event.date_str}"
    )


def _format_issue_comment(event: GitHubEvent) -> str:
    payload = _payload(event, IssueCommentPayload)
    return (
        f"💬 Commented on [{payload.title}]({payload.url}) "
        f"in [`{event.repo_name}`]({event.repo_url}) — {event.date_str}"
    )


def _format_pull_request(event: GitHubEvent) -> str:
    payload = _payload(event, PullRequestPayload)
    return (
        f"🔀 {payload.action.capitalize()} PR [{payload.title}]({payload.url}) "
        f"in [`{event.repo_name}`]({event.repo_url}) — {event.date_str}"
    )


def _format_release(event: GitHubEvent) -> str:
    payload = _payload(event, ReleasePayload)
    return (
        f"🚀 Released [`{payload.tag_name}`]({payload.url}) "
        f"in [`{event.repo_name}`]({event.repo_url}) — {event.date_str}"
    )


FORMATTERS: dict[str, Formatter] = {
    "PushEvent": _format_push,
    "CreateEvent": _format_create,
    "ForkEvent": _format_fork,
    "IssuesEvent": _format_issues,
    "IssueCommentEvent": _format_issue_comment,
    "PullRequestEvent": _format_pull_request,
    "ReleaseEvent": _format_release,
}


def format_event(event: GitHubEvent) -> str | None:
    """Render one event as a Markdown line, or None if unformattable."""
    formatter = FORMATTERS.get(event.type)
    if formatter is None:
        return None
    return formatter(event)


def register_formatter(event_type: str, formatter: Formatter) -> None:
    """Register (or override) the formatter for a GitHub event type."""
    if not event_type:
        raise ValueError("event_type must be a non-empty string")
    FORMATTERS[event_type] = formatter
