"""Resilient GitHub API client.

Replaces the legacy one-shot ``urllib`` fetch with an httpx-based client that
retries transient failures with exponential backoff, honors rate-limit
signals (``Retry-After`` / ``X-RateLimit-Reset``), and uses ETag conditional
requests so unchanged data costs no rate-limit budget.
"""

from __future__ import annotations

import logging
import os
import random
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import httpx
from pydantic import SecretStr

from profileforge import __version__
from profileforge.config import Settings

logger = logging.getLogger(__name__)

_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 30.0
_RATE_LIMIT_FALLBACK_WAIT_SECONDS = 60.0

# Env vars consulted (in order) when no explicit proxy is given.
_PROXY_ENV_VARS = (
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "ALL_PROXY",
    "all_proxy",
)


class GitHubAPIError(Exception):
    """Base error for GitHub API failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url

    @classmethod
    def from_response(cls, response: httpx.Response, default_message: str) -> Self:
        """Build an error, preferring the message GitHub put in the body."""
        message = default_message
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            detail = body.get("message")
            if isinstance(detail, str) and detail:
                message = detail
        return cls(
            f"{message} (HTTP {response.status_code})",
            status_code=response.status_code,
            url=str(response.url),
        )


class GitHubAuthError(GitHubAPIError):
    """401, or a 403 that is not a rate limit (bad token, forbidden)."""


class GitHubNotFoundError(GitHubAPIError):
    """The requested GitHub resource does not exist (404)."""


class GitHubRateLimitError(GitHubAPIError):
    """Rate limit hit and the required wait exceeded the configured cap."""


class GitHubServerError(GitHubAPIError):
    """GitHub returned 5xx on every attempt."""


@dataclass
class _CachedResponse:
    etag: str
    body: list[dict[str, Any]]


def _is_rate_limited(response: httpx.Response) -> bool:
    """True when the response signals a rate limit (429, or 403 with quota 0)."""
    if response.status_code == 429:
        return True
    return response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0"


# Env vars consulted (in order) for a CA bundle file.
_CA_BUNDLE_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")


def _resolve_verify() -> ssl.SSLContext | bool:
    """TLS verification setting for outbound connections.

    Returns an SSL context built from a CA-bundle path taken from the
    environment when one exists, otherwise True for the system default store.
    Resolved explicitly instead of relying on the HTTP client's own
    environment handling, because some sandboxed environments ship
    proxy-related env vars that HTTP clients cannot parse.
    """
    for name in _CA_BUNDLE_ENV_VARS:
        path = os.environ.get(name)
        if path and os.path.isfile(path):
            return ssl.create_default_context(cafile=path)
    return True


def _resolve_proxy_url(explicit: str | None = None) -> str | None:
    """Resolve the proxy URL: an explicit value wins, else the environment.

    httpx's own environment parsing crashes on malformed values (notably IPv6
    entries in NO_PROXY, observed on real machines), so the proxy is resolved
    here and the client is built with ``trust_env=False``. Returns None for a
    direct connection.
    """
    if explicit is not None:
        try:
            url = httpx.URL(explicit)
        except httpx.InvalidURL as exc:
            raise ValueError(f"Invalid proxy URL: {explicit!r}") from exc
        if not url.host:
            raise ValueError(f"Invalid proxy URL (no host): {explicit!r}")
        return explicit
    for name in _PROXY_ENV_VARS:
        candidate = os.environ.get(name)
        if not candidate or not candidate.strip():
            continue
        try:
            url = httpx.URL(candidate)
        except httpx.InvalidURL:
            logger.warning("Ignoring malformed proxy URL in %s; connecting directly", name)
            continue
        if not url.host:
            logger.warning("Ignoring proxy value in %s with no host; connecting directly", name)
            continue
        return candidate
    return None


class GitHubClient:
    """httpx-based GitHub API client with retries, backoff, and ETag caching.

    Use as a context manager or call :meth:`close` when done.
    """

    def __init__(
        self,
        *,
        api_base_url: str = "https://api.github.com",
        token: SecretStr | None = None,
        timeout: float = 15.0,
        max_retries: int = 3,
        rate_limit_max_wait: float = 300.0,
        proxy: str | None = None,
        verify: ssl.SSLContext | bool | None = None,
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Create a client.

        Args:
            api_base_url: GitHub API base URL (override for GHES).
            token: Personal access token; sent as a Bearer header, never logged.
            timeout: Per-request timeout in seconds.
            max_retries: Retries for transient network/5xx failures.
            rate_limit_max_wait: Longest to wait out a rate limit before raising
                :class:`GitHubRateLimitError`.
            proxy: Explicit proxy URL. When omitted, the proxy environment
                variables are consulted (robustly); None means direct.
            verify: TLS verification: an SSL context, True for the system
                default store, False to disable (not recommended). None
                auto-resolves from the environment.
            sleep: Injectable sleep (tests record instead of waiting).
            transport: Injectable httpx transport (tests use MockTransport).
        """
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if rate_limit_max_wait < 0:
            raise ValueError("rate_limit_max_wait must be non-negative")
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"profileforge/{__version__}",
        }
        if token is not None:
            headers["Authorization"] = f"Bearer {token.get_secret_value()}"
        self._http = self._build_http_client(
            api_base_url=api_base_url,
            headers=headers,
            timeout=timeout,
            transport=transport,
            proxy_url=_resolve_proxy_url(proxy),
            verify=_resolve_verify() if verify is None else verify,
        )
        self._max_retries = max_retries
        self._rate_limit_max_wait = rate_limit_max_wait
        self._sleep = sleep
        self._etag_cache: dict[str, _CachedResponse] = {}

    @staticmethod
    def _build_http_client(
        *,
        api_base_url: str,
        headers: dict[str, str],
        timeout: float,
        transport: httpx.BaseTransport | None,
        proxy_url: str | None,
        verify: ssl.SSLContext | bool,
    ) -> httpx.Client:
        """Build the httpx client with an explicitly resolved proxy.

        ``trust_env=False`` because httpx's own environment parsing crashes on
        malformed values; :func:`_resolve_proxy_url` handles the environment
        robustly instead. A malformed ``api_base_url`` still raises loudly.
        """
        if transport is not None and proxy_url is not None:
            # An injected transport owns routing entirely (test seam); an
            # explicit proxy would shadow it via httpx's mount table.
            logger.debug("Ignoring proxy because a custom transport was given")
            proxy_url = None
        return httpx.Client(
            base_url=api_base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            proxy=proxy_url,
            trust_env=False,
            verify=verify,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> GitHubClient:
        """Build a client from the validated application settings."""
        return cls(
            api_base_url=settings.api_base_url,
            token=settings.github_token,
            timeout=settings.request_timeout,
            max_retries=settings.max_retries,
            rate_limit_max_wait=settings.rate_limit_max_wait,
        )

    def close(self) -> None:
        """Release the underlying connection pool."""
        self._http.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def fetch_public_events(
        self, username: str, per_page: int = 50, max_pages: int = 1
    ) -> list[dict[str, Any]]:
        """Fetch a user's public events, newest first.

        Uses ETag conditional requests: repeat calls with no new activity
        return the cached body on HTTP 304 without spending rate-limit budget.

        Args:
            username: GitHub username.
            per_page: Events per page (1-100).
            max_pages: How many pages to walk (stops early on a short page).
        """
        if not username or not username.strip():
            raise ValueError("username must be a non-empty string")
        if not 1 <= per_page <= 100:
            raise ValueError("per_page must be between 1 and 100")
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        path = f"/users/{username}/events/public"
        all_events: list[dict[str, Any]] = []
        pages_fetched = 0
        for page in range(1, max_pages + 1):
            params = {"per_page": str(per_page), "page": str(page)}
            cache_key = f"{path}?per_page={per_page}&page={page}"
            headers: dict[str, str] = {}
            cached = self._etag_cache.get(cache_key)
            if cached is not None:
                headers["If-None-Match"] = cached.etag

            response = self._request("GET", path, params=params, headers=headers)

            if response.status_code == 304:
                if cached is None:  # cannot happen; we only send the header when cached
                    raise GitHubAPIError("Unexpected HTTP 304 with no cached response")
                logger.debug(
                    "Events for %s page %d unchanged (304); returning %d cached events",
                    username,
                    page,
                    len(cached.body),
                )
                page_events = cached.body
            else:
                _raise_for_status(response)
                page_events = _parse_json_list(response)
                etag = response.headers.get("etag")
                if etag:
                    self._etag_cache[cache_key] = _CachedResponse(etag=etag, body=page_events)
            all_events.extend(page_events)
            pages_fetched = page
            if len(page_events) < per_page:
                break
        logger.info(
            "Fetched %d public events for %s (%d page(s))",
            len(all_events),
            username,
            pages_fetched,
        )
        return all_events

    def fetch_user(self, username: str) -> dict[str, Any]:
        """Fetch a user's public profile object."""
        if not username or not username.strip():
            raise ValueError("username must be a non-empty string")
        response = self._request("GET", f"/users/{username}")
        _raise_for_status(response)
        return _parse_json_object(response)

    def fetch_repos(
        self, username: str, *, per_page: int = 100, repo_type: str = "owner"
    ) -> list[dict[str, Any]]:
        """Fetch a user's repos, most recently updated first (all pages).

        Walks pages until a short page arrives. The previous single-page
        version silently truncated any user with more than ``per_page``
        repos, which made every downstream count (stars, projects, code
        share) wrong.
        """
        if not username or not username.strip():
            raise ValueError("username must be a non-empty string")
        if not 1 <= per_page <= 100:
            raise ValueError("per_page must be between 1 and 100")
        params = {
            "per_page": str(per_page),
            "type": repo_type,
            "sort": "updated",
            "direction": "desc",
        }
        repos: list[dict[str, Any]] = []
        page = 1
        while True:
            response = self._request(
                "GET", f"/users/{username}/repos", params={**params, "page": str(page)}
            )
            _raise_for_status(response)
            batch = _parse_json_list(response)
            repos.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        logger.info("Fetched %d repos for %s", len(repos), username)
        return repos

    def fetch_repo_languages(self, owner: str, repo: str) -> dict[str, int]:
        """Fetch one repo's language byte counts (``{language: bytes}``).

        Non-positive and non-integer values are dropped defensively: a
        language with no bytes must not count the repo toward that language.
        """
        if not owner or not owner.strip():
            raise ValueError("owner must be a non-empty string")
        if not repo or not repo.strip():
            raise ValueError("repo must be a non-empty string")
        response = self._request("GET", f"/repos/{owner}/{repo}/languages")
        _raise_for_status(response)
        body = _parse_json_object(response)
        languages = {
            name: value
            for name, value in body.items()
            if isinstance(value, int) and not isinstance(value, bool) and value > 0
        }
        logger.debug("Fetched %d languages for %s/%s", len(languages), owner, repo)
        return languages

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send one request with retries, backoff, and rate-limit handling."""
        for attempt in range(self._max_retries + 1):
            try:
                response = self._http.request(method, path, params=params, headers=headers)
            except (
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.PoolTimeout,
            ) as exc:
                if attempt >= self._max_retries:
                    raise GitHubAPIError(
                        f"GitHub request failed after {self._max_retries + 1} attempts: {exc}"
                    ) from exc
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "GitHub request failed (%s); retry %d/%d in %.1fs",
                    exc,
                    attempt + 1,
                    self._max_retries,
                    delay,
                )
                self._sleep(delay)
                continue

            if response.status_code == 304:
                return response

            if _is_rate_limited(response):
                wait = self._rate_limit_wait_seconds(response)
                if wait is None:
                    raise GitHubRateLimitError.from_response(
                        response,
                        "GitHub rate limit exceeded and reset is beyond "
                        f"{self._rate_limit_max_wait:.0f}s; try again later",
                    )
                if attempt >= self._max_retries:
                    # Previously the loop fell through to AssertionError
                    # here; a persistent rate limit is a typed error.
                    raise GitHubRateLimitError.from_response(
                        response,
                        f"GitHub rate limit persisted after {self._max_retries + 1} attempts",
                    )
                logger.warning("GitHub rate limit hit; waiting %.0fs before retry", wait)
                self._sleep(wait)
                continue

            if response.status_code >= 500:
                if attempt >= self._max_retries:
                    raise GitHubServerError.from_response(response, "GitHub server error")
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "GitHub server error %d; retry %d/%d in %.1fs",
                    response.status_code,
                    attempt + 1,
                    self._max_retries,
                    delay,
                )
                self._sleep(delay)
                continue

            return response

        raise AssertionError("unreachable")  # pragma: no cover

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with jitter for a 0-based retry attempt."""
        capped = min(_BACKOFF_BASE_SECONDS * (2.0**attempt), _BACKOFF_MAX_SECONDS)
        return capped + random.uniform(0, 1.0)

    def _rate_limit_wait_seconds(self, response: httpx.Response) -> float | None:
        """Seconds to wait for a rate-limited response.

        Returns None when the required wait exceeds the configured cap, so
        the caller raises instead of sleeping indefinitely.
        """
        if self._rate_limit_max_wait <= 0:
            return None

        retry_after = response.headers.get("retry-after")
        if retry_after is not None:
            try:
                wait = float(retry_after)
            except ValueError:
                wait = _RATE_LIMIT_FALLBACK_WAIT_SECONDS
            return wait if 0 < wait <= self._rate_limit_max_wait else None

        reset = response.headers.get("x-ratelimit-reset")
        if reset is not None:
            try:
                wait = int(reset) - time.time() + 1.0
            except ValueError:
                wait = _RATE_LIMIT_FALLBACK_WAIT_SECONDS
            if wait <= 0:
                return 1.0
            return wait if wait <= self._rate_limit_max_wait else None

        return min(_RATE_LIMIT_FALLBACK_WAIT_SECONDS, self._rate_limit_max_wait)


def _raise_for_status(response: httpx.Response) -> None:
    """Map 4xx responses to typed errors (5xx/429 handled in the retry loop)."""
    status = response.status_code
    if status == 401:
        raise GitHubAuthError.from_response(response, "GitHub authentication failed")
    if status == 403 and not _is_rate_limited(response):
        raise GitHubAuthError.from_response(response, "GitHub request forbidden")
    if status == 404:
        raise GitHubNotFoundError.from_response(response, "GitHub resource not found")
    if 400 <= status < 500:
        raise GitHubAPIError.from_response(response, "GitHub request failed")


def _parse_json_object(response: httpx.Response) -> dict[str, Any]:
    """Parse a JSON object response."""
    try:
        body = response.json()
    except ValueError as exc:
        raise GitHubAPIError(
            f"GitHub returned invalid JSON (HTTP {response.status_code})",
            status_code=response.status_code,
            url=str(response.url),
        ) from exc
    if not isinstance(body, dict):
        raise GitHubAPIError(
            f"GitHub returned an unexpected body (HTTP {response.status_code})",
            status_code=response.status_code,
            url=str(response.url),
        )
    return body


def _parse_json_list(response: httpx.Response) -> list[dict[str, Any]]:
    """Parse a JSON list response, dropping non-object items defensively."""
    try:
        body = response.json()
    except ValueError as exc:
        raise GitHubAPIError(
            f"GitHub returned invalid JSON (HTTP {response.status_code})",
            status_code=response.status_code,
            url=str(response.url),
        ) from exc
    if not isinstance(body, list):
        raise GitHubAPIError(
            f"GitHub returned an unexpected body (HTTP {response.status_code})",
            status_code=response.status_code,
            url=str(response.url),
        )
    items = [item for item in body if isinstance(item, dict)]
    if len(items) != len(body):
        logger.debug("Dropped %d non-object items from GitHub response", len(body) - len(items))
    return items
