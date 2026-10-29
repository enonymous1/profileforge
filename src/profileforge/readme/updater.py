"""Marker-section README updater.

Replaces the legacy ``update_readme`` with a testable, atomic writer.
Content between ``<!--START_SECTION:{name}-->`` and
``<!--END_SECTION:{name}-->`` markers is spliced with plain string search —
never ``re.sub`` with the new content as the replacement pattern (the legacy
approach mangled activity lines containing backslashes like ``\\1``).

Files are written atomically via a temp file + ``os.replace`` with the
original permissions preserved, and a ``dry_run`` mode previews changes
without touching disk. Library code raises; only the CLI decides exit codes.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class MarkerNotFoundError(ValueError):
    """A START/END_SECTION marker pair is missing from the target file."""


@dataclass(frozen=True)
class SectionUpdate:
    """Outcome of :func:`update_section`."""

    path: Path
    section: str
    changed: bool
    line_count: int


def markers(section: str) -> tuple[str, str]:
    """Return the ``(start, end)`` markers for a section name."""
    return (
        f"<!--START_SECTION:{section}-->",
        f"<!--END_SECTION:{section}-->",
    )


def build_section_body(
    lines: Sequence[str], section: str = "activity", *, bullets: bool = True
) -> str:
    """Render a marker section body, byte-compatible with the legacy updater.

    With ``bullets=False`` lines are written as-is (for HTML/SVG sections).
    """
    start_marker, end_marker = markers(section)
    body = start_marker + "\n"
    if lines:
        if bullets:
            body += "\n".join(f"- {line}" for line in lines) + "\n"
        else:
            body += "\n".join(lines) + "\n"
    return body + end_marker


def update_section(
    path: str | Path,
    lines: Sequence[str],
    section: str = "activity",
    *,
    dry_run: bool = False,
    bullets: bool = True,
) -> SectionUpdate:
    """Replace a marker section's content, atomically.

    Args:
        path: README file to update.
        lines: Section lines (``- `` prefixed unless ``bullets=False``).
        section: Marker section name (``activity`` by default).
        dry_run: Report what would change without writing.
        bullets: Render lines as a Markdown bullet list.

    Raises:
        FileNotFoundError: The target file does not exist.
        MarkerNotFoundError: The marker pair is missing or incomplete.
    """
    target = Path(path)
    start_marker, end_marker = markers(section)

    try:
        content = target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Target file not found: {target}") from exc

    start = content.find(start_marker)
    if start == -1:
        raise MarkerNotFoundError(f"Start marker {start_marker!r} not found in {target}")
    end = content.find(end_marker, start + len(start_marker))
    if end == -1:
        raise MarkerNotFoundError(
            f"End marker {end_marker!r} not found in {target} after its start marker"
        )
    end += len(end_marker)

    updated = content[:start] + build_section_body(lines, section, bullets=bullets) + content[end:]
    result = SectionUpdate(
        path=target,
        section=section,
        changed=updated != content,
        line_count=len(lines),
    )

    if not result.changed:
        logger.info("No changes to %s: section %r already up to date", target, section)
        return result
    if dry_run:
        logger.info(
            "Dry run: would update section %r in %s with %d line(s)",
            section,
            target,
            len(lines),
        )
        return result
    _atomic_write(target, updated)
    logger.info("Updated section %r in %s with %d line(s)", section, target, len(lines))
    return result


def _atomic_write(target: Path, content: str) -> None:
    """Write ``content`` to ``target`` atomically, preserving permissions."""
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f"{target.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        shutil.copymode(target, tmp_path)
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
