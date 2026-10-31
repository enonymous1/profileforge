"""Tests for profileforge.site.builder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from profileforge.profile.stats import LanguageStat, UserSummary
from profileforge.site.builder import BuildResult, build_site, site_data_to_dict
from profileforge.site.data import ProjectCard, SiteData


def _data() -> SiteData:
    return SiteData(
        user=UserSummary(
            login="octocat",
            name="Octo Cat",
            bio="I <build> things",
            html_url="https://github.com/octocat",
            avatar_url="https://avatars.example/u/1",
            public_repos=8,
            followers=1500,
            following=5,
        ),
        total_stars=22881,
        languages=(LanguageStat(name="Python", repos=3, stars=10, share=60.0),),
        projects=(
            ProjectCard(
                name="proj",
                full_name="octocat/proj",
                html_url="https://github.com/octocat/proj",
                description="Does <stuff>",
                language="Python",
                language_color="#3572A5",
                stargazers_count=42,
                forks_count=7,
                topics=("demo",),
                updated_at="2026-10-01T00:00:00Z",
            ),
        ),
        activity_lines=("📦 Pushed 1 commit",),
        activity_html=('📦 Pushed <a href="https://github.com/o/p"><code>o/p</code></a>',),
        sparkline_svg="<svg>spark</svg>",
        sparkline_days=30,
        generated_at="2026-10-07 12:00",
    )


def test_build_site(tmp_path: Path) -> None:
    result = build_site(_data(), tmp_path / "dist")
    assert isinstance(result, BuildResult)
    assert result.output_dir == tmp_path / "dist"
    assert result.files == (
        "index.html",
        "profile.json",
        "styles.css",
        "badges/stars.svg",
        "badges/repos.svg",
        "badges/followers.svg",
    )
    for name in result.files:
        assert (tmp_path / "dist" / name).exists()


def test_build_site_rebuild_replaces_stale_files(tmp_path: Path) -> None:
    """Rebuilding over an existing site drops files the new build lacks."""
    out = tmp_path / "dist"
    build_site(_data(), out)
    (out / "stale.html").write_text("old", encoding="utf-8")
    (out / "badges" / "stale.svg").write_text("old", encoding="utf-8")
    build_site(_data(), out)
    assert not (out / "stale.html").exists()
    assert not (out / "badges" / "stale.svg").exists()
    assert (out / "index.html").exists()
    # No staging or backup debris left beside the output dir.
    assert [p.name for p in tmp_path.iterdir()] == ["dist"]


def test_index_html_content(tmp_path: Path) -> None:
    build_site(_data(), tmp_path / "dist")
    page = (tmp_path / "dist" / "index.html").read_text(encoding="utf-8")
    assert "<title>Octo Cat · GitHub Portfolio</title>" in page
    # User-controlled text is escaped (autoescape on).
    assert "I &lt;build&gt; things" in page
    assert "Does &lt;stuff&gt;" in page
    # Trusted pipeline HTML passes through.
    assert "<svg>spark</svg>" in page
    assert '<a href="https://github.com/o/p"><code>o/p</code></a>' in page
    assert "Python" in page
    assert "badges/stars.svg" in page
    assert "prefers-color-scheme" in (tmp_path / "dist" / "styles.css").read_text()


def test_badges_content(tmp_path: Path) -> None:
    build_site(_data(), tmp_path / "dist")
    stars = (tmp_path / "dist" / "badges" / "stars.svg").read_text(encoding="utf-8")
    assert "22.9k" in stars
    followers = (tmp_path / "dist" / "badges" / "followers.svg").read_text(encoding="utf-8")
    assert "1.5k" in followers
    repos = (tmp_path / "dist" / "badges" / "repos.svg").read_text(encoding="utf-8")
    assert ">8<" in repos


def test_profile_json(tmp_path: Path) -> None:
    build_site(_data(), tmp_path / "dist")
    payload: dict[str, Any] = json.loads(
        (tmp_path / "dist" / "profile.json").read_text(encoding="utf-8")
    )
    assert payload["user"]["login"] == "octocat"
    assert payload["total_stars"] == 22881
    assert payload["projects"][0]["name"] == "proj"
    assert payload["languages"][0]["name"] == "Python"
    assert payload["generated_at"] == "2026-10-07 12:00"


def test_site_data_to_dict() -> None:
    payload = site_data_to_dict(_data())
    assert payload["sparkline_days"] == 30
    assert tuple(payload["activity_lines"]) == ("📦 Pushed 1 commit",)
