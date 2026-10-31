"""Tests for profileforge.exporter (scanner, tree, markdown, pipeline)."""

from __future__ import annotations

from pathlib import Path

import pytest

from profileforge.exporter.markdown import (
    render_code_section,
    render_rollup_document,
    render_single_file_document,
)
from profileforge.exporter.pipeline import (
    ExportResult,
    NoPythonFilesError,
    export_project,
)
from profileforge.exporter.scanner import discover_python_files
from profileforge.exporter.tree import render_tree_markdown
from tests import _legacy


def _make_source_tree(root: Path) -> Path:
    """Build a fixture source tree with nesting, junk dirs, and a bad file."""
    src = root / "demo_proj"
    (src / "pkg" / "sub").mkdir(parents=True)
    (src / "pkg" / "__init__.py").write_text('"""pkg"""\n', encoding="utf-8")
    (src / "pkg" / "core.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (src / "pkg" / "sub" / "deep.py").write_text("X = 1\n", encoding="utf-8")
    (src / "top.py").write_text("# top\n", encoding="utf-8")
    (src / "notes.txt").write_text("not python\n", encoding="utf-8")
    (src / ".venv" / "lib").mkdir(parents=True)
    (src / ".venv" / "lib" / "ignored.py").write_text("Y = 2\n", encoding="utf-8")
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "cached.py").write_text("Z = 3\n", encoding="utf-8")
    (src / "pkg" / "broken.py").write_bytes(b"\xff\xfe not utf-8 \x00")
    return src


# --- scanner -------------------------------------------------------------


def test_scanner_discovers_nested_files_sorted(tmp_path: Path) -> None:
    src = _make_source_tree(tmp_path)
    result = discover_python_files(src, excluded_dirs=set(_legacy.EXCLUDED_DIRS))
    names = [p.name for p in result.files]
    assert names == sorted(names)
    assert result.src_dir == src.resolve()
    assert {p.relative_to(src).as_posix() for p in result.files} == {
        "pkg/__init__.py",
        "pkg/core.py",
        "pkg/sub/deep.py",
        "top.py",
        "pkg/broken.py",
    }


def test_scanner_excludes_at_any_depth(tmp_path: Path) -> None:
    src = _make_source_tree(tmp_path)
    result = discover_python_files(src, excluded_dirs={"__pycache__"})
    assert not any("__pycache__" in p.parts for p in result.files)
    assert any(p.name == "ignored.py" for p in result.files)


def test_scanner_no_exclusions_by_default(tmp_path: Path) -> None:
    src = _make_source_tree(tmp_path)
    result = discover_python_files(src)
    assert any(p.name == "ignored.py" for p in result.files)


def test_scanner_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        discover_python_files(tmp_path / "nope")


def test_scanner_file_not_dir_raises(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        discover_python_files(target)


def test_scanner_src_under_excluded_parent_is_not_swallowed(
    tmp_path: Path,
) -> None:
    """Deliberate improvement: exclusion is relative to the source dir."""
    src = tmp_path / ".venv" / "real_src"
    src.mkdir(parents=True)
    (src / "a.py").write_text("A = 1\n", encoding="utf-8")
    result = discover_python_files(src, excluded_dirs={".venv"})
    assert [p.name for p in result.files] == ["a.py"]


# --- tree -----------------------------------------------------------------


def test_render_tree_markdown_exact() -> None:
    src_dir = Path("/x/proj")
    files = [
        src_dir / "a.py",
        src_dir / "pkg" / "b.py",
        src_dir / "pkg" / "sub" / "c.py",
    ]
    assert render_tree_markdown(files, src_dir) == (
        "# Project File Structure (Python Scripts)\n"
        "\n"
        "**Source Directory:** `/x/proj`\n"
        "\n"
        "```text\n"
        "📁 proj\n"
        "├── 📁 pkg\n"
        "│   ├── 📁 sub\n"
        "│   │   └── c.py\n"
        "│   └── b.py\n"
        "└── a.py\n"
        "```"
    )


def test_render_tree_matches_legacy(tmp_path: Path) -> None:
    src = _make_source_tree(tmp_path)
    scan = discover_python_files(src, excluded_dirs=set(_legacy.EXCLUDED_DIRS))
    assert render_tree_markdown(scan.files, scan.src_dir) == _legacy.generate_tree_markdown(
        list(scan.files), scan.src_dir
    )


# --- markdown renderers ----------------------------------------------------


def test_render_code_section() -> None:
    assert render_code_section("core.py", "X = 1\n") == (
        "## `📄 core.py`\n\n```python\nX = 1\n\n```\n\n---\n"
    )


def test_render_code_section_with_backticks_uses_longer_fence() -> None:
    """Source containing triple backticks must not close the fence early."""
    code = '"""Example:\n\n```python\nX = 1\n```\n"""\n'
    rendered = render_code_section("doc.py", code)
    assert rendered.startswith("## `📄 doc.py`\n\n````python\n")
    assert rendered.endswith("````\n\n---\n")
    assert "```python\nX = 1\n```" in rendered


def test_render_rollup_document() -> None:
    sections = [render_code_section("a.py", "A = 1\n"), render_code_section("b.py", "B = 2\n")]
    assert render_rollup_document("pkg", "pkg", sections) == (
        "# Directory: `pkg`\n"
        "\n"
        "**Path:** `pkg`\n"
        "\n"
        "---\n"
        "\n"
        "## `📄 a.py`\n\n```python\nA = 1\n\n```\n\n---\n"
        "\n"
        "## `📄 b.py`\n\n```python\nB = 2\n\n```\n\n---\n"
    )


def test_render_single_file_document() -> None:
    assert render_single_file_document("core.py", "pkg/core.py", "X = 1\n") == (
        "# `core.py`\n\n**Project Path:** `pkg/core.py`\n\n---\n\n```python\nX = 1\n\n```\n"
    )


# --- pipeline ---------------------------------------------------------------


def _dir_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


@pytest.mark.parametrize("rollup", [True, False])
def test_export_matches_legacy_byte_for_byte(tmp_path: Path, rollup: bool) -> None:
    """Full export must be byte-identical to the legacy script."""
    src = _make_source_tree(tmp_path)
    legacy_dest = tmp_path / "legacy_out"
    new_dest = tmp_path / "new_out"
    _legacy.mirror_py_to_md(src_path=src, dest_path=legacy_dest, rollup_dirs=rollup)
    export_project(src, new_dest, rollup_dirs=rollup, excluded_dirs=set(_legacy.EXCLUDED_DIRS))
    assert _dir_snapshot(legacy_dest) == _dir_snapshot(new_dest)


def test_export_rollup_layout(tmp_path: Path) -> None:
    src = _make_source_tree(tmp_path)
    dest = tmp_path / "out"
    result = export_project(src, dest, excluded_dirs=set(_legacy.EXCLUDED_DIRS))
    assert isinstance(result, ExportResult)
    assert result.src_dir == src.resolve()
    assert result.dest_dir == dest.resolve()
    assert result.structure_file == dest / "project_structure.md"
    produced = {p.relative_to(dest).as_posix() for p in dest.rglob("*.md")}
    assert produced == {
        "project_structure.md",
        "demo_proj.md",  # root dir rollup, named after the source dir
        "pkg.md",
        "pkg/sub.md",
    }
    assert result.files_written == 4
    # The undecodable file is skipped but its directory still gets a document.
    pkg_doc = (dest / "pkg.md").read_text(encoding="utf-8")
    assert "broken.py" not in pkg_doc
    assert "core.py" in pkg_doc


def test_export_rollup_skips_directory_with_only_unreadable_files(tmp_path: Path) -> None:
    """A directory whose files all fail to read gets no (empty) document."""
    src = tmp_path / "demo_proj"
    (src / "good").mkdir(parents=True)
    (src / "good" / "ok.py").write_text("X = 1\n", encoding="utf-8")
    (src / "only_bad").mkdir(parents=True)
    (src / "only_bad" / "broken.py").write_bytes(b"\xff\xfe not utf-8 \x00")
    dest = tmp_path / "out"
    result = export_project(src, dest, excluded_dirs=set(_legacy.EXCLUDED_DIRS))
    produced = {p.relative_to(dest).as_posix() for p in dest.rglob("*.md")}
    assert "only_bad.md" not in produced
    assert "good.md" in produced
    assert result.files_written == len(produced)


def test_export_mirrored_layout(tmp_path: Path) -> None:
    src = _make_source_tree(tmp_path)
    dest = tmp_path / "out"
    result = export_project(src, dest, rollup_dirs=False, excluded_dirs=set(_legacy.EXCLUDED_DIRS))
    produced = {p.relative_to(dest).as_posix() for p in dest.rglob("*.md")}
    assert produced == {
        "project_structure.md",
        "pkg/__init__.md",
        "pkg/core.md",
        "pkg/sub/deep.md",
        "top.md",
    }
    assert result.files_written == 5


def test_export_default_dest_dir(tmp_path: Path) -> None:
    src = _make_source_tree(tmp_path)
    result = export_project(src, excluded_dirs=set(_legacy.EXCLUDED_DIRS))
    assert result.dest_dir == src.resolve() / "reports" / "markdown_src_directory"
    assert result.structure_file.exists()


def test_export_no_python_files_raises(tmp_path: Path) -> None:
    src = tmp_path / "empty"
    src.mkdir()
    (src / "notes.txt").write_text("nothing\n", encoding="utf-8")
    with pytest.raises(NoPythonFilesError):
        export_project(src, tmp_path / "out")


def test_export_missing_src_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        export_project(tmp_path / "nope", tmp_path / "out")
