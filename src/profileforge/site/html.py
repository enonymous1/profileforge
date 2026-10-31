"""Minimal Markdown-to-HTML for activity lines.

Only the constructs our own formatters emit are supported: ``[text](url)``
links (with optional backtick code spans inside the link text) and
```code` spans. Everything else is HTML-escaped as plain text.
Backslash-escaped brackets (``\\[``) stay literal: the formatters emit them
for user-supplied titles, and they must not become links here.
"""

from __future__ import annotations

import html
import re

_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
_CODE_RE = re.compile(r"`([^`]+)`")
# A backslash-escaped bracket span, e.g. \[here\] from an escaped title.
# Protected before link conversion: without this, the link regex would
# match from an outer "[" to the escaped span's "]" and turn user text
# into a link to the wrong URL.
_ESCAPED_SPAN_RE = re.compile(r"\\\[.*?\\\]")


def _format_code_spans(escaped: str) -> str:
    return _CODE_RE.sub(lambda match: f"<code>{match.group(1)}</code>", escaped)


def markdown_inline_to_html(line: str) -> str:
    """Convert one Markdown activity line to inline HTML."""
    protected: dict[str, str] = {}

    def _protect(match: re.Match[str]) -> str:
        key = f"\x00{len(protected)}\x00"
        protected[key] = match.group(0)
        return key

    line = _ESCAPED_SPAN_RE.sub(_protect, line)
    parts: list[str] = []
    pos = 0
    for match in _LINK_RE.finditer(line):
        parts.append(_format_code_spans(html.escape(line[pos : match.start()])))
        text = _format_code_spans(html.escape(match.group(1)))
        url = html.escape(match.group(2), quote=True)
        parts.append(f'<a href="{url}">{text}</a>')
        pos = match.end()
    parts.append(_format_code_spans(html.escape(line[pos:])))
    rendered = "".join(parts)
    for key, original in protected.items():
        # Placeholders survive html.escape untouched, so restore them now.
        rendered = rendered.replace(key, html.escape(original))
    return rendered
