"""Project-tree Markdown renderer, byte-compatible with the legacy exporter."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any


def render_tree_markdown(py_files: Sequence[Path], src_dir: Path) -> str:
    """Render the project file tree as a fenced Markdown code block."""
    lines = [
        "# Project File Structure (Python Scripts)\n",
        f"**Source Directory:** `{src_dir}`\n",
        "```text",
        f"📁 {src_dir.name}",
    ]
    lines.extend(_render_node(_build_tree(py_files, src_dir)))
    lines.append("```")
    return "\n".join(lines)


def _build_tree(py_files: Sequence[Path], src_dir: Path) -> dict[str, Any]:
    """Build a nested dict: empty dict = file, non-empty = directory."""
    tree: dict[str, Any] = {}
    for py_file in py_files:
        node = tree
        for part in py_file.relative_to(src_dir).parts:
            node = node.setdefault(part, {})
    return tree


def _render_node(node: dict[str, Any], prefix: str = "") -> list[str]:
    """Render one tree level; directories first, then case-insensitive A-Z."""
    lines: list[str] = []
    items = sorted(node, key=lambda key: (not bool(node[key]), key.lower()))
    for index, item in enumerate(items):
        is_last = index == len(items) - 1
        connector = "└── " if is_last else "├── "
        child = node[item]
        if not child:
            lines.append(f"{prefix}{connector}{item}")
        else:
            lines.append(f"{prefix}{connector}📁 {item}")
            extension = "    " if is_last else "│   "
            lines.extend(_render_node(child, prefix + extension))
    return lines
