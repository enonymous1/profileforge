"""Tests for profileforge.github.client (httpx.MockTransport; no network)."""

from __future__ import annotations

import logging
import ssl
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from profileforge.config import Settings
from profileforge.github.client import (
    _PROXY_ENV_VARS,
    GitHubAPIError,
    GitHubAuthError,
    GitHubClient,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServerError,
    _resolve_proxy_url,
    _resolve_verify,
)

_EVENTS = [{"type": "PushEvent", "id": "1"}, {"type": "CreateEvent", "id": "2"}]


def _clear_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _PROXY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _json_response(
    status: int,
    body: Any = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    if body is None:
        return httpx.Response(status, headers=headers or {})
    return httpx.Response(status, headers=headers or {}, json=body)


class _MockAPI:
    """Queues httpx responses/exceptions; records requests and sleeps."""

    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        assert isinstance(item, httpx.Response)
        return item

    def client(self, **kwargs: Any) -> GitHubClient:
        return GitHubClient(
            transport=httpx.MockTransport(self.handler),
            sleep=self.sleeps.append,
            **kwargs,
        )


def test_fetch_success_sends_expected_request() -> None:
    api = _MockAPI([_json_response(200, _EVENTS)])
    client = api.client(token=SecretStr("tok123"))
    try:
        events = client.fetch_public_events("octocat")
    finally:
        client.close()
    assert events == _EVENTS
    assert len(api.requests) == 1
    request = api.requests[0]
    assert request.url.path == "/users/octocat/events/public"
    assert request.url.params["per_page"] == "50"
    assert request.headers["authorization"] == "Bearer tok123"
    assert request.headers["accept"] == "application/vnd.github.v3+json"
    assert request.headers["user-agent"].startswith("profileforge/")
    assert api.sleeps == []


def test_no_token_sends_no_auth_header() -> None:
    api = _MockAPI([_json_response(200, _EVENTS)])
    with api.client() as client:
        client.fetch_public_events("octocat")
    assert "authorization" not in api.requests[0].headers


def test_retries_server_errors_then_succeeds() -> None:
    api = _MockAPI([_json_response(500, {"message": "boom"}), _json_response(200, _EVENTS)])
    with api.client(max_retries=3) as client:
        events = client.fetch_public_events("octocat")
    assert events == _EVENTS
    assert len(api.requests) == 2
    assert len(api.sleeps) == 1
    assert api.sleeps[0] > 0


def test_server_errors_exhausted_raises() -> None:
    api = _MockAPI([_json_response(503, {"message": "down"})] * 4)
    with api.client(max_retries=3) as client:
        with pytest.raises(GitHubServerError) as exc_info:
            client.fetch_public_events("octocat")
    assert exc_info.value.status_code == 503
    assert "down" in str(exc_info.value)
    assert len(api.requests) == 4
    assert len(api.sleeps) == 3


def test_retries_connect_errors() -> None:
    api = _MockAPI([httpx.ConnectError("dns down"), _json_response(200, _EVENTS)])
    with api.client(max_retries=2) as client:
        events = client.fetch_public_events("octocat")
    assert events == _EVENTS
    assert len(api.sleeps) == 1


def test_connect_errors_exhausted_raises_api_error() -> None:
    api = _MockAPI([httpx.ConnectError("down")] * 3)
    with api.client(max_retries=2) as client:
        with pytest.raises(GitHubAPIError, match="after 3 attempts"):
            client.fetch_public_events("octocat")
    assert len(api.sleeps) == 2


def test_unauthorized_raises_without_retry() -> None:
    api = _MockAPI([_json_response(401, {"message": "Bad credentials"})])
    with api.client() as client:
        with pytest.raises(GitHubAuthError, match="Bad credentials"):
            client.fetch_public_events("octocat")
    assert api.sleeps == []
    assert len(api.requests) == 1


def test_forbidden_without_rate_limit_headers_is_auth_error() -> None:
    api = _MockAPI([_json_response(403, {"message": "Forbidden"})])
    with api.client() as client:
        with pytest.raises(GitHubAuthError):
            client.fetch_public_events("octocat")
    assert api.sleeps == []


def test_not_found_raises() -> None:
    api = _MockAPI([_json_response(404, {"message": "Not Found"})])
    with api.client() as client:
        with pytest.raises(GitHubNotFoundError):
            client.fetch_public_events("octocat")


def test_429_honors_retry_after() -> None:
    api = _MockAPI(
        [
            _json_response(429, {"message": "slow down"}, {"Retry-After": "2"}),
            _json_response(200, _EVENTS),
        ]
    )
    with api.client() as client:
        events = client.fetch_public_events("octocat")
    assert events == _EVENTS
    assert api.sleeps == [2.0]


def test_403_rate_limit_waits_until_reset() -> None:
    reset = int(time.time()) + 30
    api = _MockAPI(
        [
            _json_response(
                403,
                {"message": "API rate limit exceeded"},
                {
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset),
                },
            ),
            _json_response(200, _EVENTS),
        ]
    )
    with api.client(rate_limit_max_wait=300.0) as client:
        events = client.fetch_public_events("octocat")
    assert events == _EVENTS
    assert len(api.sleeps) == 1
    assert 25.0 < api.sleeps[0] < 35.0


def test_rate_limit_reset_beyond_cap_raises() -> None:
    reset = int(time.time()) + 3600
    api = _MockAPI(
        [
            _json_response(
                403,
                {"message": "API rate limit exceeded"},
                {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)},
            )
        ]
    )
    with api.client(rate_limit_max_wait=300.0) as client:
        with pytest.raises(GitHubRateLimitError):
            client.fetch_public_events("octocat")
    assert api.sleeps == []


def test_rate_limit_zero_max_wait_fails_immediately() -> None:
    api = _MockAPI([_json_response(429, {"message": "slow down"}, {"Retry-After": "60"})])
    with api.client(rate_limit_max_wait=0) as client:
        with pytest.raises(GitHubRateLimitError):
            client.fetch_public_events("octocat")
    assert api.sleeps == []
    assert len(api.requests) == 1


def test_persistent_rate_limit_raises_typed_error() -> None:
    api = _MockAPI([_json_response(429, None, {"Retry-After": "1"})] * 4)
    with api.client() as client:
        with pytest.raises(GitHubRateLimitError, match="persisted"):
            client.fetch_public_events("octocat")
    assert api.sleeps == [1.0, 1.0, 1.0]
    assert len(api.requests) == 4


def test_etag_304_returns_cached_body() -> None:
    api = _MockAPI(
        [
            _json_response(200, _EVENTS, {"ETag": '"abc123"'}),
            httpx.Response(304),
        ]
    )
    with api.client() as client:
        first = client.fetch_public_events("octocat")
        second = client.fetch_public_events("octocat")
    assert first == second == _EVENTS
    assert len(api.requests) == 2
    assert api.requests[1].headers["if-none-match"] == '"abc123"'
    assert api.sleeps == []


def test_non_list_body_raises() -> None:
    api = _MockAPI([_json_response(200, {"message": "not a list"})])
    with api.client() as client:
        with pytest.raises(GitHubAPIError, match="unexpected body"):
            client.fetch_public_events("octocat")


def test_invalid_json_raises() -> None:
    api = _MockAPI([httpx.Response(200, content=b"not json")])
    with api.client() as client:
        with pytest.raises(GitHubAPIError, match="invalid JSON"):
            client.fetch_public_events("octocat")


@pytest.mark.parametrize("bad_username", ["", "   "])
def test_blank_username_rejected(bad_username: str) -> None:
    api = _MockAPI([])
    with api.client() as client:
        with pytest.raises(ValueError, match="non-empty"):
            client.fetch_public_events(bad_username)


@pytest.mark.parametrize("bad_per_page", [0, 101])
def test_per_page_bounds_enforced(bad_per_page: int) -> None:
    api = _MockAPI([])
    with api.client() as client:
        with pytest.raises(ValueError, match="per_page"):
            client.fetch_public_events("octocat", per_page=bad_per_page)


def test_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_USERNAME", "octocat")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("REQUEST_TIMEOUT", "7")
    monkeypatch.setenv("MAX_RETRIES", "5")
    monkeypatch.setenv("RATE_LIMIT_MAX_WAIT", "42")
    with GitHubClient.from_settings(Settings()) as client:
        assert str(client._http.base_url) == "https://api.github.com"
        assert client._max_retries == 5
        assert client._rate_limit_max_wait == 42.0
        assert client._http.headers["authorization"] == "Bearer tok"


def test_malformed_proxy_env_falls_back_to_direct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Broken proxy env vars must not prevent the client from starting."""
    _clear_proxy_env(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://bad:1]/")
    with GitHubClient() as client:
        assert str(client._http.base_url) == "https://api.github.com"


def test_resolve_proxy_explicit_wins_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://env-proxy:3128")
    assert _resolve_proxy_url("http://explicit:9999") == "http://explicit:9999"


def test_resolve_proxy_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_proxy_env(monkeypatch)
    monkeypatch.setenv("https_proxy", "http://env-proxy:3128")
    assert _resolve_proxy_url() == "http://env-proxy:3128"


def test_resolve_proxy_prefers_https_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_proxy_env(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://secure-proxy:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://plain-proxy:3128")
    assert _resolve_proxy_url() == "http://secure-proxy:3128"


def test_resolve_proxy_none_when_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_proxy_env(monkeypatch)
    assert _resolve_proxy_url() is None


def test_resolve_proxy_malformed_env_ignored(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _clear_proxy_env(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://bad:1]/")
    with caplog.at_level(logging.WARNING):
        assert _resolve_proxy_url() is None
    assert "malformed proxy" in caplog.text


def test_resolve_proxy_explicit_malformed_raises() -> None:
    with pytest.raises(ValueError, match="Invalid proxy URL"):
        _resolve_proxy_url("http://bad:1]/")


def test_resolve_verify_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bundle = tmp_path / "ca-bundle.pem"
    bundle.write_text("fake")
    monkeypatch.setenv("SSL_CERT_FILE", str(bundle))
    captured: dict[str, object] = {}

    def fake_create_default_context(*, cafile: str | None = None, **kwargs: object) -> object:
        captured["cafile"] = cafile
        return ("context", cafile)

    monkeypatch.setattr(ssl, "create_default_context", fake_create_default_context)
    assert _resolve_verify() == ("context", str(bundle))
    assert captured["cafile"] == str(bundle)


def test_resolve_verify_ignores_missing_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/ca-bundle.pem")
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    assert _resolve_verify() is True


def test_resolve_verify_falls_back_to_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    assert _resolve_verify() is True


def test_fetch_user() -> None:
    api = _MockAPI([_json_response(200, {"login": "octocat", "public_repos": 8})])
    with api.client() as client:
        user = client.fetch_user("octocat")
    assert user["login"] == "octocat"
    assert user["public_repos"] == 8
    assert api.requests[0].url.path == "/users/octocat"


def test_fetch_user_not_found() -> None:
    api = _MockAPI([_json_response(404, {"message": "Not Found"})])
    with api.client() as client:
        with pytest.raises(GitHubNotFoundError):
            client.fetch_user("octocat")


def test_fetch_user_invalid_json() -> None:
    api = _MockAPI([httpx.Response(200, content=b"nope")])
    with api.client() as client:
        with pytest.raises(GitHubAPIError, match="invalid JSON"):
            client.fetch_user("octocat")


def test_fetch_user_unexpected_body() -> None:
    api = _MockAPI([_json_response(200, ["not", "an", "object"])])
    with api.client() as client:
        with pytest.raises(GitHubAPIError, match="unexpected body"):
            client.fetch_user("octocat")


def test_fetch_repo_languages() -> None:
    api = _MockAPI([_json_response(200, {"Python": 1200, "Go": 300})])
    with api.client() as client:
        languages = client.fetch_repo_languages("octocat", "hello-world")
    assert languages == {"Python": 1200, "Go": 300}
    assert api.requests[0].url.path == "/repos/octocat/hello-world/languages"


def test_fetch_repo_languages_drops_non_positive_values() -> None:
    api = _MockAPI(
        [_json_response(200, {"Python": 100, "Empty": 0, "Weird": -5, "Text": "12", "Flag": True})]
    )
    with api.client() as client:
        languages = client.fetch_repo_languages("octocat", "hello-world")
    assert languages == {"Python": 100}


def test_fetch_repo_languages_not_found() -> None:
    api = _MockAPI([_json_response(404, {"message": "Not Found"})])
    with api.client() as client:
        with pytest.raises(GitHubNotFoundError):
            client.fetch_repo_languages("octocat", "missing")


def test_fetch_repo_languages_blank_args_rejected() -> None:
    api = _MockAPI([_json_response(200, {})])
    with api.client() as client:
        with pytest.raises(ValueError, match="owner"):
            client.fetch_repo_languages("", "hello-world")
        with pytest.raises(ValueError, match="repo"):
            client.fetch_repo_languages("octocat", "  ")


def test_fetch_repos() -> None:
    api = _MockAPI(
        [_json_response(200, [{"name": "a", "stargazers_count": 3, "language": "Python"}])]
    )
    with api.client() as client:
        repos = client.fetch_repos("octocat")
    assert len(repos) == 1
    assert repos[0]["name"] == "a"
    request = api.requests[0]
    assert request.url.path == "/users/octocat/repos"
    assert request.url.params["per_page"] == "100"
    assert request.url.params["sort"] == "updated"


def test_fetch_repos_paginates() -> None:
    api = _MockAPI(
        [
            _json_response(200, [{"name": "a"}, {"name": "b"}]),
            _json_response(200, [{"name": "c"}]),
        ]
    )
    with api.client() as client:
        repos = client.fetch_repos("octocat", per_page=2)
    assert [repo["name"] for repo in repos] == ["a", "b", "c"]
    assert api.requests[0].url.params["page"] == "1"
    assert api.requests[1].url.params["page"] == "2"


def test_fetch_repos_blank_username_rejected() -> None:
    api = _MockAPI([])
    with api.client() as client:
        with pytest.raises(ValueError, match="non-empty"):
            client.fetch_repos("  ")


def test_fetch_public_events_paginates_until_short_page() -> None:
    page1 = [{"id": str(i)} for i in range(50)]
    page2 = [{"id": str(i)} for i in range(50, 60)]
    api = _MockAPI([_json_response(200, page1), _json_response(200, page2)])
    with api.client() as client:
        events = client.fetch_public_events("octocat", per_page=50, max_pages=3)
    assert len(events) == 60
    assert [request.url.params["page"] for request in api.requests] == ["1", "2"]


def test_fetch_public_events_respects_max_pages() -> None:
    api = _MockAPI([_json_response(200, [{"id": "1"}]), _json_response(200, [{"id": "2"}])])
    with api.client() as client:
        events = client.fetch_public_events("octocat", per_page=1, max_pages=2)
    assert len(events) == 2
    assert len(api.requests) == 2


def test_fetch_public_events_rejects_bad_max_pages() -> None:
    api = _MockAPI([])
    with api.client() as client:
        with pytest.raises(ValueError, match="max_pages"):
            client.fetch_public_events("octocat", max_pages=0)
