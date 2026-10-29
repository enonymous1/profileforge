"""Tests for the profileforge typer CLI."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import profileforge.cli as cli_module
from profileforge import __version__
from profileforge.cli import app
from profileforge.github.client import GitHubAPIError
from tests.test_activity import RAW_ACTIVITY_FEED

runner = CliRunner()

_README_TEMPLATE = (
    "# My Profile\n\n"
    "Intro.\n\n"
    "<!--START_SECTION:activity-->\n"
    "<!--END_SECTION:activity-->\n\n"
    "Footer.\n"
)


def _set_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GH_USERNAME", "octocat")
    monkeypatch.setenv("TARGET_FILE", str(tmp_path / "README.md"))


def _write_readme(path: Path) -> Path:
    path.write_text(_README_TEMPLATE, encoding="utf-8")
    return path


def _fake_client_class(
    events: list[dict[str, Any]] | None = None,
    error: Exception | None = None,
) -> type:
    """Build a fake GitHubClient with canned events or a canned error."""

    class _FakeGitHubClient:
        @classmethod
        def from_settings(cls, settings: object) -> _FakeGitHubClient:
            return cls()

        def __enter__(self) -> _FakeGitHubClient:
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def fetch_public_events(
            self, username: str, per_page: int = 50, max_pages: int = 1
        ) -> list[dict[str, Any]]:
            if error is not None:
                raise error
            assert username == "octocat"
            return copy.deepcopy(events or [])

        def fetch_user(self, username: str) -> dict[str, Any]:
            if error is not None:
                raise error
            return {
                "login": "octocat",
                "name": "Octo",
                "bio": "Test bio",
                "html_url": "https://github.com/octocat",
                "avatar_url": "",
                "public_repos": 2,
                "followers": 3,
                "following": 1,
            }

        def fetch_repos(
            self, username: str, *, per_page: int = 100, repo_type: str = "owner"
        ) -> list[dict[str, Any]]:
            if error is not None:
                raise error
            return [
                {
                    "name": "a",
                    "full_name": "octocat/a",
                    "html_url": "https://github.com/octocat/a",
                    "description": "",
                    "stargazers_count": 5,
                    "language": "Python",
                    "fork": False,
                    "archived": False,
                }
            ]

    return _FakeGitHubClient


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_config_show(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    result = runner.invoke(app, ["config-show"])
    assert result.exit_code == 0
    assert "gh_username=octocat" in result.output
    assert "secret" not in result.output.lower()


def test_config_show_missing_username(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GH_USERNAME", raising=False)
    result = runner.invoke(app, ["config-show"])
    assert result.exit_code == 2
    assert "GH_USERNAME" in result.output


def test_export_docs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    src = tmp_path / "proj"
    src.mkdir()
    (src / "a.py").write_text("A = 1\n", encoding="utf-8")
    dest = tmp_path / "docs"
    result = runner.invoke(app, ["export-docs", str(src), "--dest", str(dest)])
    assert result.exit_code == 0, result.output
    assert (dest / "project_structure.md").exists()
    assert (dest / "proj.md").exists()
    assert "Markdown file(s)" in result.output


def test_export_docs_no_rollup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    src = tmp_path / "proj"
    src.mkdir()
    (src / "a.py").write_text("A = 1\n", encoding="utf-8")
    dest = tmp_path / "docs"
    result = runner.invoke(app, ["export-docs", str(src), "--dest", str(dest), "--no-rollup"])
    assert result.exit_code == 0, result.output
    assert (dest / "a.md").exists()
    assert not (dest / "proj.md").exists()


def test_export_docs_missing_src(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    result = runner.invoke(app, ["export-docs", str(tmp_path / "nope")])
    assert result.exit_code != 0


def test_sync_activity_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    readme = _write_readme(tmp_path / "README.md")
    before = readme.read_text(encoding="utf-8")
    monkeypatch.setattr(cli_module, "GitHubClient", _fake_client_class(events=RAW_ACTIVITY_FEED))
    result = runner.invoke(app, ["sync-activity", "--target", str(readme), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert readme.read_text(encoding="utf-8") == before
    assert "Would update" in result.output
    assert (
        "📦 Pushed to [`octocat/proj`](https://github.com/octocat/proj)"
        " on `main` — Oct 07, 2026" in result.output
    )


def test_sync_activity_writes_readme(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    readme = _write_readme(tmp_path / "README.md")
    monkeypatch.setattr(cli_module, "GitHubClient", _fake_client_class(events=RAW_ACTIVITY_FEED))
    result = runner.invoke(app, ["sync-activity", "--target", str(readme)])
    assert result.exit_code == 0, result.output
    content = readme.read_text(encoding="utf-8")
    assert (
        "📦 Pushed to [`octocat/proj`](https://github.com/octocat/proj)"
        " on `main` — Oct 07, 2026" in content
    )
    assert "Updated" in result.output


def test_sync_activity_already_up_to_date(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    readme = _write_readme(tmp_path / "README.md")
    monkeypatch.setattr(cli_module, "GitHubClient", _fake_client_class(events=RAW_ACTIVITY_FEED))
    assert runner.invoke(app, ["sync-activity", "--target", str(readme)]).exit_code == 0
    result = runner.invoke(app, ["sync-activity", "--target", str(readme)])
    assert result.exit_code == 0
    assert "already up to date" in result.output


def test_sync_activity_no_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    readme = _write_readme(tmp_path / "README.md")
    monkeypatch.setattr(cli_module, "GitHubClient", _fake_client_class(events=[]))
    result = runner.invoke(app, ["sync-activity", "--target", str(readme)])
    assert result.exit_code == 0
    assert "No displayable activity" in result.output


def test_sync_activity_api_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    readme = _write_readme(tmp_path / "README.md")
    monkeypatch.setattr(
        cli_module, "GitHubClient", _fake_client_class(error=GitHubAPIError("down"))
    )
    result = runner.invoke(app, ["sync-activity", "--target", str(readme)])
    assert result.exit_code == 1


def test_sync_activity_missing_markers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("# No markers\n", encoding="utf-8")
    monkeypatch.setattr(cli_module, "GitHubClient", _fake_client_class(events=RAW_ACTIVITY_FEED))
    result = runner.invoke(app, ["sync-activity", "--target", str(readme)])
    assert result.exit_code == 1


def test_sync_activity_bad_max_lines(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    readme = _write_readme(tmp_path / "README.md")
    result = runner.invoke(app, ["sync-activity", "--target", str(readme), "--max-lines", "0"])
    assert result.exit_code == 2


_STATS_README = "# My Profile\n\n<!--START_SECTION:stats-->\nold stats\n<!--END_SECTION:stats-->\n"


def test_sync_stats_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text(_STATS_README, encoding="utf-8")
    monkeypatch.setattr(cli_module, "GitHubClient", _fake_client_class(events=RAW_ACTIVITY_FEED))
    result = runner.invoke(app, ["sync-stats", "--target", str(readme), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert readme.read_text(encoding="utf-8") == _STATS_README
    assert "Would update stats section" in result.output


def test_sync_stats_writes_svg_and_languages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_env(monkeypatch, tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text(_STATS_README, encoding="utf-8")
    monkeypatch.setattr(cli_module, "GitHubClient", _fake_client_class(events=RAW_ACTIVITY_FEED))
    result = runner.invoke(app, ["sync-stats", "--target", str(readme)])
    assert result.exit_code == 0, result.output
    content = readme.read_text(encoding="utf-8")
    assert "<svg " in content
    assert "Python" in content
    assert "old stats" not in content
    assert "Updated stats section" in result.output


def test_sync_stats_already_up_to_date(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text(_STATS_README, encoding="utf-8")
    monkeypatch.setattr(cli_module, "GitHubClient", _fake_client_class(events=RAW_ACTIVITY_FEED))
    assert runner.invoke(app, ["sync-stats", "--target", str(readme)]).exit_code == 0
    result = runner.invoke(app, ["sync-stats", "--target", str(readme)])
    assert result.exit_code == 0
    assert "already up to date" in result.output


def test_sync_stats_missing_markers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("# No markers\n", encoding="utf-8")
    monkeypatch.setattr(cli_module, "GitHubClient", _fake_client_class(events=RAW_ACTIVITY_FEED))
    result = runner.invoke(app, ["sync-stats", "--target", str(readme)])
    assert result.exit_code == 1


def test_sync_stats_api_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text(_STATS_README, encoding="utf-8")
    monkeypatch.setattr(
        cli_module, "GitHubClient", _fake_client_class(error=GitHubAPIError("down"))
    )
    result = runner.invoke(app, ["sync-stats", "--target", str(readme)])
    assert result.exit_code == 1


def test_render_readme_to_stdout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    monkeypatch.setattr(cli_module, "GitHubClient", _fake_client_class(events=RAW_ACTIVITY_FEED))
    result = runner.invoke(app, ["render-readme"])
    assert result.exit_code == 0, result.output
    assert "# Hi there, I'm Octo 👋" in result.output
    assert "Test bio" in result.output
    assert "<!--START_SECTION:activity-->" in result.output
    assert "<!--START_SECTION:stats-->" in result.output
    assert "<svg " in result.output


def test_render_readme_to_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    monkeypatch.setattr(cli_module, "GitHubClient", _fake_client_class(events=RAW_ACTIVITY_FEED))
    output = tmp_path / "rendered.md"
    result = runner.invoke(app, ["render-readme", "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert output.exists()
    assert "Last refreshed" in output.read_text(encoding="utf-8")


def test_render_readme_api_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cli_module, "GitHubClient", _fake_client_class(error=GitHubAPIError("down"))
    )
    result = runner.invoke(app, ["render-readme"])
    assert result.exit_code == 1


def test_build_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    monkeypatch.setattr(cli_module, "GitHubClient", _fake_client_class(events=RAW_ACTIVITY_FEED))
    output = tmp_path / "dist"
    result = runner.invoke(app, ["build-page", "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert (output / "index.html").exists()
    assert (output / "profile.json").exists()
    assert (output / "styles.css").exists()
    assert (output / "badges" / "stars.svg").exists()
    page = (output / "index.html").read_text(encoding="utf-8")
    assert "Octo" in page
    assert "Built 6 files" in result.output


def test_build_page_rejects_bad_projects(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    monkeypatch.setattr(cli_module, "GitHubClient", _fake_client_class(events=RAW_ACTIVITY_FEED))
    result = runner.invoke(app, ["build-page", "--output", str(tmp_path / "d"), "--projects", "0"])
    assert result.exit_code == 2


def test_build_page_api_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cli_module, "GitHubClient", _fake_client_class(error=GitHubAPIError("down"))
    )
    result = runner.invoke(app, ["build-page", "--output", str(tmp_path / "d")])
    assert result.exit_code == 1
