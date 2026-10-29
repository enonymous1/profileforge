"""Render SiteData to a static site directory."""

from __future__ import annotations

import importlib.resources
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import jinja2

from profileforge.profile.renderer import render_top_languages
from profileforge.site.badges import format_compact, render_badge
from profileforge.site.data import SiteData

logger = logging.getLogger(__name__)

_SITE_ENV = jinja2.Environment(
    loader=jinja2.PackageLoader("profileforge.site", "templates"),
    autoescape=True,
)


@dataclass(frozen=True)
class BuildResult:
    """Where the site was written and which files were produced."""

    output_dir: Path
    files: tuple[str, ...]


def site_data_to_dict(data: SiteData) -> dict[str, Any]:
    """Serialize the site model for profile.json."""
    return asdict(data)


def _static_bytes(name: str) -> bytes:
    return (importlib.resources.files("profileforge.site") / "static" / name).read_bytes()


def build_site(data: SiteData, output_dir: str | Path) -> BuildResult:
    """Render the portfolio page, profile.json, CSS, and badges.

    Args:
        data: Assembled site model.
        output_dir: Directory to write (created if missing).

    Returns:
        BuildResult with the output dir and relative file paths written.
    """
    out = Path(output_dir)
    badges_dir = out / "badges"
    badges_dir.mkdir(parents=True, exist_ok=True)

    context = {
        "user": data.user,
        "total_stars": data.total_stars,
        "languages": data.languages,
        "projects": data.projects,
        "activity_html": data.activity_html,
        "sparkline_svg": data.sparkline_svg,
        "top_languages_html": render_top_languages(data.languages),
        "sparkline_days": data.sparkline_days,
        "generated_at": data.generated_at,
    }

    written: list[str] = []

    def _write(relative: str, content: str | bytes) -> None:
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        written.append(relative)

    _write("index.html", _SITE_ENV.get_template("index.html.j2").render(context))
    _write("profile.json", json.dumps(site_data_to_dict(data), indent=2) + "\n")
    _write("styles.css", _static_bytes("styles.css"))

    badge_specs = (
        ("stars", "stars", format_compact(data.total_stars), "#dfb317"),
        ("repos", "repos", str(data.user.public_repos), "#0969da"),
        ("followers", "followers", format_compact(data.user.followers), "#8250df"),
    )
    for name, label, value, color in badge_specs:
        _write(f"badges/{name}.svg", render_badge(label, value, color=color))

    logger.info("Built site in %s (%d files)", out, len(written))
    return BuildResult(output_dir=out, files=tuple(written))
