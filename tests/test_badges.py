"""Tests for profileforge.site.badges."""

from __future__ import annotations

import pytest

from profileforge.site.badges import format_compact, render_badge


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (999, "999"),
        (1000, "1k"),
        (1500, "1.5k"),
        (22881, "22.9k"),
        (1_000_000, "1M"),
        (2_500_000, "2.5M"),
    ],
)
def test_format_compact(value: int, expected: str) -> None:
    assert format_compact(value) == expected


def test_format_compact_rejects_negative() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        format_compact(-1)


def test_render_badge() -> None:
    svg = render_badge("stars", "22.9k", color="#dfb317")
    assert svg.startswith("<svg ")
    assert 'role="img"' in svg
    assert 'aria-label="stars: 22.9k"' in svg
    assert "<title>stars: 22.9k</title>" in svg
    assert ">stars<" in svg
    assert ">22.9k<" in svg
    assert 'fill="#dfb317"' in svg
    assert 'fill="#555"' in svg


def test_render_badge_escapes_text() -> None:
    svg = render_badge("<b>", "&amp;")
    assert "<b>" not in svg
    assert "&lt;b&gt;" in svg
    assert "&amp;amp;" in svg


def test_render_badge_default_color() -> None:
    assert 'fill="#4c1"' in render_badge("x", "y")
