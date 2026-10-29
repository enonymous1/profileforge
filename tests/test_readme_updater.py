"""Tests for profileforge.readme.updater."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from profileforge.readme.updater import (
    MarkerNotFoundError,
    SectionUpdate,
    build_section_body,
    markers,
    update_section,
)
from tests import _legacy

_TEMPLATE = (
    "# Profile\n\n"
    "Some intro text.\n\n"
    "<!--START_SECTION:activity-->\n"
    "{section_body}"
    "<!--END_SECTION:activity-->\n\n"
    "Footer text.\n"
)

_LINES = [
    "📦 Pushed 2 commits to [`a/b`](https://github.com/a/b) on `main` — Oct 06, 2026",
    "🌱 Created repository [`a/c`](https://github.com/a/c) — Oct 05, 2026",
]


def _write_readme(path: Path, section_body: str) -> Path:
    path.write_text(_TEMPLATE.format(section_body=section_body), encoding="utf-8")
    return path


def test_markers() -> None:
    assert markers("activity") == (
        "<!--START_SECTION:activity-->",
        "<!--END_SECTION:activity-->",
    )


def test_build_section_body() -> None:
    assert build_section_body(_LINES) == (
        f"<!--START_SECTION:activity-->\n- {_LINES[0]}\n- {_LINES[1]}\n<!--END_SECTION:activity-->"
    )


def test_build_section_body_empty() -> None:
    assert build_section_body([]) == "<!--START_SECTION:activity-->\n<!--END_SECTION:activity-->"


def test_update_section_replaces_content(tmp_path: Path) -> None:
    readme = _write_readme(tmp_path / "README.md", "- old line\n")
    result = update_section(readme, _LINES)
    assert isinstance(result, SectionUpdate)
    assert result.changed is True
    assert result.line_count == 2
    assert result.section == "activity"
    content = readme.read_text(encoding="utf-8")
    assert f"- {_LINES[0]}\n- {_LINES[1]}\n" in content
    assert "- old line" not in content
    assert content.startswith("# Profile\n\nSome intro text.\n\n")
    assert content.endswith("Footer text.\n")


def test_update_section_no_change_second_run(tmp_path: Path) -> None:
    readme = _write_readme(tmp_path / "README.md", "- old line\n")
    first = update_section(readme, _LINES)
    assert first.changed is True
    second = update_section(readme, _LINES)
    assert second.changed is False
    assert second.line_count == 2


def test_update_section_empty_lines_clears_section(tmp_path: Path) -> None:
    readme = _write_readme(tmp_path / "README.md", "- old line\n")
    result = update_section(readme, [])
    assert result.changed is True
    content = readme.read_text(encoding="utf-8")
    assert "<!--START_SECTION:activity-->\n<!--END_SECTION:activity-->" in content


def test_update_section_dry_run_writes_nothing(tmp_path: Path) -> None:
    readme = _write_readme(tmp_path / "README.md", "- old line\n")
    before = readme.read_text(encoding="utf-8")
    result = update_section(readme, _LINES, dry_run=True)
    assert result.changed is True
    assert readme.read_text(encoding="utf-8") == before


def test_backslash_lines_survive_verbatim(tmp_path: Path) -> None:
    """The legacy re.sub approach mangled backslashes; splicing must not."""
    tricky = [r"fix \1 regression", r"path C:\new\thing", "100% \\ done"]
    readme = _write_readme(tmp_path / "README.md", "- old\n")
    update_section(readme, tricky)
    content = readme.read_text(encoding="utf-8")
    for line in tricky:
        assert f"- {line}\n" in content


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        update_section(tmp_path / "nope.md", _LINES)


def test_missing_markers_raise(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# No markers here\n", encoding="utf-8")
    with pytest.raises(MarkerNotFoundError, match="Start marker"):
        update_section(readme, _LINES)


def test_missing_end_marker_raises(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Title\n<!--START_SECTION:activity-->\n", encoding="utf-8")
    with pytest.raises(MarkerNotFoundError, match="End marker"):
        update_section(readme, _LINES)


def test_end_before_start_raises(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "<!--END_SECTION:activity-->\n<!--START_SECTION:activity-->\n",
        encoding="utf-8",
    )
    with pytest.raises(MarkerNotFoundError, match="End marker"):
        update_section(readme, _LINES)


def test_marker_error_is_value_error(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# No markers\n", encoding="utf-8")
    with pytest.raises(ValueError):
        update_section(readme, _LINES)


def test_custom_section_name(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "<!--START_SECTION:stats-->\nold\n<!--END_SECTION:stats-->\n",
        encoding="utf-8",
    )
    result = update_section(readme, ["a", "b"], section="stats")
    assert result.changed is True
    assert result.section == "stats"
    content = readme.read_text(encoding="utf-8")
    assert "<!--START_SECTION:stats-->\n- a\n- b\n<!--END_SECTION:stats-->" in content


def test_atomic_write_preserves_permissions(tmp_path: Path) -> None:
    readme = _write_readme(tmp_path / "README.md", "- old\n")
    os.chmod(readme, 0o600)
    update_section(readme, _LINES)
    assert stat.S_IMODE(os.stat(readme).st_mode) == 0o600


def test_no_temp_files_left_behind(tmp_path: Path) -> None:
    readme = _write_readme(tmp_path / "README.md", "- old\n")
    update_section(readme, _LINES)
    leftovers = list(tmp_path.glob("README.md.*.tmp"))
    assert leftovers == []


def test_update_section_no_bullets(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "<!--START_SECTION:stats-->\nold\n<!--END_SECTION:stats-->\n",
        encoding="utf-8",
    )
    result = update_section(
        readme, ["<svg>line1</svg>", "<div>line2</div>"], section="stats", bullets=False
    )
    assert result.changed is True
    content = readme.read_text(encoding="utf-8")
    assert (
        "<!--START_SECTION:stats-->\n<svg>line1</svg>\n<div>line2</div>\n"
        "<!--END_SECTION:stats-->" in content
    )
    assert "- <svg>" not in content


@pytest.mark.parametrize(
    ("section_body", "lines"),
    [
        ("- old line\n", ["new line"]),
        ("", []),
        ("- same line\n", ["same line"]),  # already up to date
    ],
)
def test_update_matches_legacy_byte_for_byte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, section_body: str, lines: list[str]
) -> None:
    """New updater must produce byte-identical files to the legacy function."""
    template = _TEMPLATE.format(section_body=section_body)
    legacy_path = tmp_path / "legacy_README.md"
    new_path = tmp_path / "new_README.md"
    legacy_path.write_text(template, encoding="utf-8")
    new_path.write_text(template, encoding="utf-8")

    monkeypatch.setattr(_legacy, "README_PATH", str(legacy_path))
    legacy_changed = _legacy.update_readme(lines)
    new_result = update_section(new_path, lines)

    assert legacy_path.read_text(encoding="utf-8") == new_path.read_text(encoding="utf-8")
    assert legacy_changed == new_result.changed
