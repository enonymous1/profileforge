"""Locally generated SVG badges (shields-style, no third-party service)."""

from __future__ import annotations

import html

_HEIGHT = 20
_FONT_SIZE = 11
_CHAR_WIDTH = 6.5  # approximate advance for Verdana-ish 11px text
_PAD = 10


def format_compact(value: int) -> str:
    """Format a count compactly: 999 -> "999", 1500 -> "1.5k", 2M -> "2M"."""
    if value < 0:
        raise ValueError("value must be non-negative")
    if value < 1000:
        return str(value)
    divisor, suffix = (1000.0, "k") if value < 1_000_000 else (1_000_000.0, "M")
    text = f"{value / divisor:.1f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def _text_width(text: str) -> float:
    return len(text) * _CHAR_WIDTH + _PAD


def render_badge(label: str, value: str, *, color: str = "#4c1") -> str:
    """Render a two-part flat badge as an SVG string.

    Args:
        label: Left (dark) segment text.
        value: Right (colored) segment text.
        color: CSS color for the value segment.
    """
    label_esc = html.escape(label)
    value_esc = html.escape(value)
    label_w = _text_width(label)
    value_w = _text_width(value)
    total_w = label_w + value_w
    label_x = label_w / 2
    value_x = label_w + value_w / 2
    aria = html.escape(f"{label}: {value}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" '
        f'height="{_HEIGHT}" role="img" aria-label="{aria}">'
        f"<title>{aria}</title>"
        f'<clipPath id="r"><rect width="{total_w:.0f}" height="{_HEIGHT}" rx="3"/></clipPath>'
        f'<g clip-path="url(#r)">'
        f'<rect width="{label_w:.0f}" height="{_HEIGHT}" fill="#555"/>'
        f'<rect x="{label_w:.0f}" width="{value_w:.0f}" height="{_HEIGHT}" fill="{color}"/>'
        "</g>"
        f'<g fill="#fff" font-family="Verdana,DejaVu Sans,sans-serif" '
        f'font-size="{_FONT_SIZE}">'
        f'<text x="{label_x:.1f}" y="14" text-anchor="middle">{label_esc}</text>'
        f'<text x="{value_x:.1f}" y="14" text-anchor="middle">{value_esc}</text>'
        "</g></svg>"
    )
