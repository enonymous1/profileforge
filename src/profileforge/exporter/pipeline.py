"""Export orchestration: discover → tree doc → rendered Markdown files."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

from profileforge.exporter.markdown import (
    render_code_section,
    render_rollup_document,
    render_single_file_document,
)
from profileforge.exporter.scanner import ScanResult, discover_python_files
from profileforge.exporter.tree import render_tree_markdown

logger = logging.getLogger(__name__)

_DEFAULT_DEST_DIRNAME = Path("reports") / "markdown_src_directory"


class NoPythonFilesError(ValueError):
    """No Python files were discovered under the source directory."""


@dataclass(frozen=True)
class ExportResult:
    """Outcome of :func:`export_project`."""

    src_dir: Path
    dest_dir: Path
    files_written: int
    structure_file: Path


def export_project(
    src_dir: str | Path,
    dest_dir: str | Path | None = None,
    *,
    rollup_dirs: bool = True,
    excluded_dirs: Collection[str] | None = None,
) -> ExportResult:
    """Mirror Python sources to Markdown documentation.

    Unlike the legacy script this raises instead of silently returning:
    :class:`FileNotFoundError` for a missing source dir and
    :class:`NoPythonFilesError` when nothing is discovered. Files that fail
    UTF-8 decoding are skipped with an error log, as before.

    Args:
        src_dir: Root of the Python sources to document.
        dest_dir: Output directory; defaults to
            ``<src>/reports/markdown_src_directory``.
        rollup_dirs: Combine each directory's files into one document.
        excluded_dirs: Directory names to skip during discovery.

    Returns:
        An :class:`ExportResult` describing what was written.
    """
    scan = discover_python_files(src_dir, excluded_dirs)
    if not scan.files:
        raise NoPythonFilesError(f"No Python files discovered under {scan.src_dir}")

    dest = (
        Path(dest_dir).resolve() if dest_dir is not None else scan.src_dir / _DEFAULT_DEST_DIRNAME
    )
    dest.mkdir(parents=True, exist_ok=True)

    structure_file = dest / "project_structure.md"
    structure_file.write_text(render_tree_markdown(scan.files, scan.src_dir), encoding="utf-8")
    logger.info("Wrote project structure to %s", structure_file)

    written = 1
    if rollup_dirs:
        written += _export_rollup(scan, dest)
    else:
        written += _export_mirrored(scan, dest)

    mode = "rolled up" if rollup_dirs else "mirrored"
    logger.info("Successfully %s %d Python file(s) into %s", mode, len(scan.files), dest)
    return ExportResult(
        src_dir=scan.src_dir,
        dest_dir=dest,
        files_written=written,
        structure_file=structure_file,
    )


def _read_source(path: Path) -> str | None:
    """Read a Python source file; None (plus an error log) if unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        logger.error("Skipping %s: %s", path.name, exc)
        return None


def _export_rollup(scan: ScanResult, dest: Path) -> int:
    """Write one Markdown document per directory; returns files written."""
    grouped: defaultdict[Path, list[Path]] = defaultdict(list)
    for py_file in scan.files:
        grouped[py_file.parent].append(py_file)

    written = 0
    for directory in sorted(grouped):
        rel_dir = directory.relative_to(scan.src_dir)
        if rel_dir == Path("."):
            md_file = dest / f"{scan.src_dir.name}.md"
        else:
            md_file = dest / rel_dir.parent / f"{directory.name}.md"

        sections: list[str] = []
        for py_file in grouped[directory]:
            code = _read_source(py_file)
            if code is None:
                continue
            sections.append(render_code_section(py_file.name, code))

        if not sections:
            # Every file in this directory was unreadable; do not write an
            # empty document for it.
            continue
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(
            render_rollup_document(directory.name, str(rel_dir), sections),
            encoding="utf-8",
        )
        written += 1
    return written


def _export_mirrored(scan: ScanResult, dest: Path) -> int:
    """Write one Markdown document per Python file; returns files written."""
    written = 0
    for py_file in scan.files:
        code = _read_source(py_file)
        if code is None:
            continue
        rel_path = py_file.relative_to(scan.src_dir)
        md_file = dest / rel_path.with_suffix(".md")
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(
            render_single_file_document(py_file.name, str(rel_path), code),
            encoding="utf-8",
        )
        written += 1
    return written
