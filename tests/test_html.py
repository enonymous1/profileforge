"""Tests for profileforge.site.html."""

from __future__ import annotations

from profileforge.site.html import markdown_inline_to_html


def test_plain_text_is_escaped() -> None:
    assert markdown_inline_to_html("a < b & c") == "a &lt; b &amp; c"


def test_link() -> None:
    assert (
        markdown_inline_to_html("[hi](https://example.com)")
        == '<a href="https://example.com">hi</a>'
    )


def test_link_with_code_span_inside() -> None:
    assert (
        markdown_inline_to_html("[`octocat/proj`](https://github.com/octocat/proj)")
        == '<a href="https://github.com/octocat/proj"><code>octocat/proj</code></a>'
    )


def test_code_span() -> None:
    assert markdown_inline_to_html("pushed to `main`") == "pushed to <code>main</code>"


def test_typical_activity_line() -> None:
    line = "📦 Pushed 3 commits to [`octocat/proj`](https://github.com/octocat/proj)"
    html = markdown_inline_to_html(line)
    assert html == (
        "📦 Pushed 3 commits to "
        '<a href="https://github.com/octocat/proj"><code>octocat/proj</code></a>'
    )


def test_url_is_escaped() -> None:
    html = markdown_inline_to_html('[x](https://example.com/?a="b")')
    assert 'href="https://example.com/?a=&quot;b&quot;"' in html


def test_unmatched_brackets_stay_literal() -> None:
    assert markdown_inline_to_html("[not a link") == "[not a link"
