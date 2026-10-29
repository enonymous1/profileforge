"""Minimal Markdown-to-HTML for activity lines.

Only the constructs our own formatters emit are supported: ``[text](url)``
links (with optional backtick code spans inside the link text) and
```code` spans. Everything else is HTML-escaped as plain text.
"""

from __future__ import annotations

import html
import re

_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
_CODE_RE = re.compile(r"`([^`]+)`")


def _format_code_spans(escaped: str) -> str:
    return _CODE_RE.sub(lambda match: f"<code>{match.group(1)}</code>", escaped)


def markdown_inline_to_html(line: str) -> str:
    """Convert one Markdown activity line to inline HTML."""
    parts: list[str] = []
    pos = 0
    for match in _LINK_RE.finditer(line):
        parts.append(_format_code_spans(html.escape(line[pos : match.start()])))
        text = _format_code_spans(html.escape(match.group(1)))
        url = html.escape(match.group(2), quote=True)
        parts.append(f'<a href="{url}">{text}</a>')
        pos = match.end()
    parts.append(_format_code_spans(html.escape(line[pos:])))
    return "".join(parts)
