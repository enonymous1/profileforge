"""Centralized, validated configuration for profileforge.

All tunables come from the environment (optionally via a ``.env`` file).
Importing this module has no side effects; call :func:`get_settings` once
at startup and pass the resulting object around.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import AliasChoices, Field, PositiveFloat, PositiveInt, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_DEFAULT_EXCLUDED_DIRS: tuple[str, ...] = (
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    ".idea",
    ".vscode",
)

_VALID_LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class Settings(BaseSettings):
    """Every knob the profile tooling shares, validated once at startup.

    Environment variable names are the UPPER_SNAKE_CASE form of each field
    (e.g. ``gh_username`` <- ``GH_USERNAME``). See ``.env.example``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- GitHub identity -------------------------------------------------
    gh_username: str = Field(
        default="",
        description="GitHub username whose profile is being served (required).",
    )
    github_token: SecretStr | None = Field(
        default=None,
        description="Personal access token; raises API rate limits when set.",
    )

    # --- Activity sync ----------------------------------------------------
    target_file: Path = Field(
        default=Path("README.md"),
        description="README file receiving the activity section.",
    )
    max_lines: PositiveInt = Field(
        default=5, description="Max activity lines written to the README."
    )
    events_per_page: PositiveInt = Field(
        default=50, description="Events requested per GitHub API page."
    )
    api_base_url: str = Field(
        default="https://api.github.com",
        validation_alias=AliasChoices("GITHUB_API_BASE_URL", "API_BASE_URL"),
        description="GitHub API base URL (override for GHES).",
    )
    request_timeout: PositiveFloat = Field(
        default=15.0, description="Per-request timeout in seconds."
    )
    max_retries: PositiveInt = Field(default=3, description="Retries per request before giving up.")
    rate_limit_max_wait: PositiveFloat = Field(
        default=300.0, description="Longest to wait out a GitHub rate limit before failing."
    )

    # --- Markdown exporter -------------------------------------------------
    # NoDecode: pydantic-settings would otherwise demand JSON for this list
    # field; a hand-edited .env naturally uses the comma-separated form.
    excluded_dirs: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(_DEFAULT_EXCLUDED_DIRS),
        description="Directory names skipped during source discovery "
        "(comma-separated or JSON array in env/.env).",
    )
    rollup_dirs: bool = Field(
        default=True,
        description="Roll each directory's .py files into one Markdown file.",
    )

    # --- Logging -----------------------------------------------------------
    log_level: str = Field(default="INFO", description="Console log level.")
    log_json: bool = Field(default=False, description="Emit JSON log lines.")

    @field_validator("gh_username")
    @classmethod
    def _require_username(cls, value: str) -> str:
        """Fail fast when no username was provided (no silent wrong default)."""
        username = value.strip()
        if not username:
            raise ValueError("GH_USERNAME must be set to a non-empty GitHub username")
        return username

    @field_validator("github_token", mode="before")
    @classmethod
    def _empty_token_to_none(cls, value: Any) -> Any:
        """Treat an empty/blank token exactly like an unset one."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("excluded_dirs", mode="before")
    @classmethod
    def _split_excluded_dirs(cls, value: Any) -> Any:
        """Accept ``.venv,venv`` or ``[".venv", "venv"]`` for EXCLUDED_DIRS."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError("EXCLUDED_DIRS JSON value must be an array of names")
                return [str(item) for item in parsed]
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return value

    @field_validator("api_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in _VALID_LOG_LEVELS:
            raise ValueError(f"log_level must be one of {_VALID_LOG_LEVELS}, got {value!r}")
        return normalized

    def masked_dump(self) -> dict[str, Any]:
        """Return settings as a plain dict with secrets replaced by ``***``."""
        data = self.model_dump(mode="json")
        if self.github_token is not None:
            data["github_token"] = "***"
        return data


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load (once) and return the validated application settings."""
    return Settings()
