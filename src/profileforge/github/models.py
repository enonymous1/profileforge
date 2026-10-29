"""Typed models for GitHub public events.

Parsing is defensive: the GitHub API occasionally omits fields, so every
payload parser degrades to the same defaults the legacy script used instead
of raising.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

UNKNOWN_REPO = "unknown/unknown"


@dataclass(frozen=True)
class CommitRef:
    """A single commit inside a PushEvent payload."""

    sha: str = ""
    message: str = ""


@dataclass(frozen=True)
class PushPayload:
    branch: str = "main"
    commits: tuple[CommitRef, ...] = ()


@dataclass(frozen=True)
class CreatePayload:
    ref_type: str = "repository"
    ref: str = ""


@dataclass(frozen=True)
class ForkPayload:
    forkee_full_name: str = ""


@dataclass(frozen=True)
class IssuePayload:
    action: str = "opened"
    title: str = "an issue"
    url: str = ""


@dataclass(frozen=True)
class IssueCommentPayload:
    title: str = "an issue"
    url: str = ""


@dataclass(frozen=True)
class PullRequestPayload:
    action: str = "opened"
    title: str = "a pull request"
    url: str = ""


@dataclass(frozen=True)
class ReleasePayload:
    tag_name: str = ""
    url: str = ""


@dataclass(frozen=True)
class UnknownPayload:
    raw: Mapping[str, Any] = field(default_factory=dict)


PayloadT = (
    PushPayload
    | CreatePayload
    | ForkPayload
    | IssuePayload
    | IssueCommentPayload
    | PullRequestPayload
    | ReleasePayload
    | UnknownPayload
)


@dataclass(frozen=True)
class GitHubEvent:
    """One GitHub public event with a typed payload."""

    type: str
    repo_name: str
    created_at: datetime | None
    created_at_raw: str
    payload: PayloadT

    @property
    def repo_url(self) -> str:
        return f"https://github.com/{self.repo_name}"

    @property
    def date_str(self) -> str:
        """Human date exactly as the legacy script produced (``Oct 07, 2026``)."""
        if self.created_at is not None:
            return self.created_at.strftime("%b %d, %Y")
        return self.created_at_raw[:10]


def _str(mapping: Mapping[str, Any], key: str, default: str = "") -> str:
    """Read a string field, falling back to ``default`` for missing/None."""
    value = mapping.get(key, default)
    return str(value) if value is not None else default


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _repo_url(repo_name: str) -> str:
    return f"https://github.com/{repo_name}"


def _parse_push(payload: Mapping[str, Any], _repo_name: str) -> PushPayload:
    raw_commits = payload.get("commits") or []
    commits = tuple(
        CommitRef(sha=_str(commit, "sha"), message=_str(commit, "message"))
        for commit in raw_commits
        if isinstance(commit, Mapping)
    )
    branch = _str(payload, "ref", "refs/heads/main").replace("refs/heads/", "")
    return PushPayload(branch=branch, commits=commits)


def _parse_create(payload: Mapping[str, Any], _repo_name: str) -> CreatePayload:
    return CreatePayload(
        ref_type=_str(payload, "ref_type", "repository"),
        ref=_str(payload, "ref"),
    )


def _parse_fork(payload: Mapping[str, Any], repo_name: str) -> ForkPayload:
    forkee = payload.get("forkee") or {}
    return ForkPayload(forkee_full_name=_str(forkee, "full_name", repo_name))


def _parse_issue(payload: Mapping[str, Any], repo_name: str) -> IssuePayload:
    issue = payload.get("issue") or {}
    return IssuePayload(
        action=_str(payload, "action", "opened"),
        title=_str(issue, "title", "an issue"),
        url=_str(issue, "html_url", _repo_url(repo_name)),
    )


def _parse_issue_comment(payload: Mapping[str, Any], repo_name: str) -> IssueCommentPayload:
    issue = payload.get("issue") or {}
    comment = payload.get("comment") or {}
    return IssueCommentPayload(
        title=_str(issue, "title", "an issue"),
        url=_str(comment, "html_url", _repo_url(repo_name)),
    )


def _parse_pull_request(payload: Mapping[str, Any], repo_name: str) -> PullRequestPayload:
    pr = payload.get("pull_request") or {}
    return PullRequestPayload(
        action=_str(payload, "action", "opened"),
        title=_str(pr, "title", "a pull request"),
        url=_str(pr, "html_url", _repo_url(repo_name)),
    )


def _parse_release(payload: Mapping[str, Any], repo_name: str) -> ReleasePayload:
    release = payload.get("release") or {}
    return ReleasePayload(
        tag_name=_str(release, "tag_name"),
        url=_str(release, "html_url", _repo_url(repo_name)),
    )


def _parse_unknown(payload: Mapping[str, Any], _repo_name: str) -> UnknownPayload:
    return UnknownPayload(raw=dict(payload))


_PAYLOAD_PARSERS: dict[str, Callable[[Mapping[str, Any], str], PayloadT]] = {
    "PushEvent": _parse_push,
    "CreateEvent": _parse_create,
    "ForkEvent": _parse_fork,
    "IssuesEvent": _parse_issue,
    "IssueCommentEvent": _parse_issue_comment,
    "PullRequestEvent": _parse_pull_request,
    "ReleaseEvent": _parse_release,
}


def parse_event(raw: Mapping[str, Any]) -> GitHubEvent:
    """Parse a raw GitHub API event dict into a typed :class:`GitHubEvent`.

    Unknown event types parse into :class:`UnknownPayload` rather than
    raising, so a new GitHub event type can never crash the sync.
    """
    event_type = _str(raw, "type")
    repo = raw.get("repo") or {}
    repo_name = _str(repo, "name", UNKNOWN_REPO)
    created_raw = _str(raw, "created_at")
    payload_raw = raw.get("payload") or {}
    if not isinstance(payload_raw, Mapping):
        payload_raw = {}
    parser = _PAYLOAD_PARSERS.get(event_type, _parse_unknown)
    return GitHubEvent(
        type=event_type,
        repo_name=repo_name,
        created_at=_parse_datetime(created_raw),
        created_at_raw=created_raw,
        payload=parser(payload_raw, repo_name),
    )
