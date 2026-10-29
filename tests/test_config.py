"""Tests for profileforge.config.Settings."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from profileforge.config import Settings, get_settings


def _valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_USERNAME", "octocat")


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid_env(monkeypatch)
    settings = Settings()
    assert settings.max_lines == 5
    assert settings.events_per_page == 50
    assert settings.api_base_url == "https://api.github.com"
    assert settings.github_token is None
    assert settings.rollup_dirs is True
    assert settings.log_level == "INFO"
    assert settings.rate_limit_max_wait == 300.0
    assert ".venv" in settings.excluded_dirs
    assert ".git" in settings.excluded_dirs


def test_missing_username_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_USERNAME", raising=False)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("bad_value", ["not-a-number", "0", "-3"])
def test_invalid_max_lines_rejected(monkeypatch: pytest.MonkeyPatch, bad_value: str) -> None:
    _valid_env(monkeypatch)
    monkeypatch.setenv("MAX_LINES", bad_value)
    with pytest.raises(ValidationError):
        Settings()


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_USERNAME", "octocat")
    monkeypatch.setenv("MAX_LINES", "10")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    settings = Settings()
    assert settings.max_lines == 10
    assert settings.github_token is not None
    assert settings.github_token.get_secret_value() == "secret-token"
    assert settings.log_level == "DEBUG"


def test_empty_token_becomes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid_env(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "   ")
    assert Settings().github_token is None


def test_api_base_url_trailing_slash_stripped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _valid_env(monkeypatch)
    monkeypatch.setenv("GITHUB_API_BASE_URL", "https://ghe.example.com/api/v3/")
    assert Settings().api_base_url == "https://ghe.example.com/api/v3"


def test_invalid_log_level_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
    with pytest.raises(ValidationError):
        Settings()


def test_masked_dump_hides_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_USERNAME", "octocat")
    monkeypatch.setenv("GITHUB_TOKEN", "super-secret")
    dumped = Settings().masked_dump()
    assert dumped["github_token"] == "***"
    assert "super-secret" not in str(dumped)


def test_get_settings_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_USERNAME", "octocat")
    assert get_settings() is get_settings()


def test_excluded_dirs_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: .env.example ships EXCLUDED_DIRS comma-separated.

    pydantic-settings JSON-decodes list fields by default, so the shipped
    example used to crash Settings() with a SettingsError before any
    validation ran (found live by the user, 2026-10-23).
    """
    _valid_env(monkeypatch)
    monkeypatch.setenv("EXCLUDED_DIRS", ".venv, custom_dir ,__pycache__")
    assert Settings().excluded_dirs == [".venv", "custom_dir", "__pycache__"]


def test_excluded_dirs_json_array_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid_env(monkeypatch)
    monkeypatch.setenv("EXCLUDED_DIRS", '[".venv", "node_modules"]')
    assert Settings().excluded_dirs == [".venv", "node_modules"]


def test_excluded_dirs_from_dotenv_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The exact user path: settings loaded from a copied .env.example."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "GH_USERNAME=octocat\nEXCLUDED_DIRS=.venv,venv,.git\n", encoding="utf-8"
    )
    monkeypatch.delenv("GH_USERNAME", raising=False)
    monkeypatch.delenv("EXCLUDED_DIRS", raising=False)
    settings = Settings()
    assert settings.gh_username == "octocat"
    assert settings.excluded_dirs == [".venv", "venv", ".git"]


def test_excluded_dirs_direct_string() -> None:
    settings = Settings(gh_username="octocat", excluded_dirs="a, b")  # type: ignore[arg-type]
    assert settings.excluded_dirs == ["a", "b"]
