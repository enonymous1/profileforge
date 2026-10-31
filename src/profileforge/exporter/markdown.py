"""Markdown renderers for the Python-to-Markdown exporter.

All renderers are pure functions producing output byte-compatible with the
legacy ``export_to_md.py`` script.
"""

from __future__ import annotations

import re
from collections.abc import Sequence


def _fence_for(code: str) -> str:
    """A fence longer than any backtick run in the code.

    Python source can legally contain triple backticks (Markdown examples
    in docstrings are the common case); a fixed ``` fence would close
    early and corrupt the document.
    """
    longest = max((len(run) for run in re.findall(r"`+", code)), default=0)
    return "`" * max(3, longest + 1)


def render_code_section(file_name: str, code: str) -> str:
    """Render one Python file's section inside a rollup document."""
    fence = _fence_for(code)
    return f"## `📄 {file_name}`\n\n{fence}python\n{code}\n{fence}\n\n---\n"


def render_rollup_document(directory_name: str, rel_dir: str, file_sections: Sequence[str]) -> str:
    """Render a rollup document combining one directory's Python files."""
    parts = [
        f"# Directory: `{directory_name}`\n",
        f"**Path:** `{rel_dir}`\n",
        "---\n",
        *file_sections,
    ]
    return "\n".join(parts)


def render_single_file_document(file_name: str, rel_path: str, code: str) -> str:
    """Render a 1-to-1 mirrored Markdown document for one Python file."""
    fence = _fence_for(code)
    return (
        f"# `{file_name}`\n\n**Project Path:** `{rel_path}`\n\n---\n\n"
        f"{fence}python\n{code}\n{fence}\n"
    )
