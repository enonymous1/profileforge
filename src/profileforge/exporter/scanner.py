"""Source discovery for the Markdown exporter.

Finds ``*.py`` files under a source directory while skipping excluded
directory names (virtualenvs, caches, VCS metadata, ...).

Deliberate improvement over the legacy script: exclusion is matched against
path parts *relative to* the source directory. The legacy version matched
absolute parts, so a source tree living under a directory like ``.venv``
was swallowed whole.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanResult:
    """Discovered Python files for one source directory."""

    src_dir: Path
    files: tuple[Path, ...]


def discover_python_files(
    src_dir: str | Path,
    excluded_dirs: Collection[str] | None = None,
) -> ScanResult:
    """Recursively find ``*.py`` files, skipping excluded directory names.

    Args:
        src_dir: Root directory to scan.
        excluded_dirs: Directory names to skip (matched against each path
            part relative to ``src_dir``). None means no exclusions.

    Raises:
        FileNotFoundError: ``src_dir`` does not exist.
        NotADirectoryError: ``src_dir`` is not a directory.
    """
    root = Path(src_dir).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Source directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")
    excluded = set(excluded_dirs or ())

    files: list[Path] = []
    for file_path in sorted(root.rglob("*.py")):
        rel_parts = file_path.relative_to(root).parts
        if any(part in excluded for part in rel_parts):
            logger.debug("Skipping excluded path: %s", file_path)
            continue
        files.append(file_path)

    logger.info("Discovered %d Python file(s) under %s", len(files), root)
    return ScanResult(src_dir=root, files=tuple(files))
