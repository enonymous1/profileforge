"""Command-line interface for profileforge."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import typer
from pydantic import ValidationError
from pydantic_settings import SettingsError

from profileforge import __version__
from profileforge.config import Settings, get_settings
from profileforge.exporter.pipeline import NoPythonFilesError, export_project
from profileforge.github.activity import build_activity_lines
from profileforge.github.client import GitHubAPIError, GitHubClient
from profileforge.github.models import parse_event
from profileforge.logging_config import setup_logging
from profileforge.profile.renderer import build_profile_context, render_readme, render_stats_body
from profileforge.profile.sparkline import (
    build_daily_counts,
    render_sparkline_text,
    sparkline_start,
)
from profileforge.profile.stats import fetch_code_share, fetch_repo_summaries
from profileforge.readme.updater import MarkerNotFoundError, SectionUpdate, update_section
from profileforge.site.builder import build_site
from profileforge.site.data import assemble_site_data

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="profileforge",
    help=(
        "Tooling that powers a living GitHub profile: activity sync, "
        "doc export, and portfolio site generation."
    ),
    no_args_is_help=True,
)


def _load_settings() -> Settings:
    """Load validated settings, exiting(2) with a clear error if invalid."""
    try:
        return get_settings()
    except (ValidationError, SettingsError) as exc:
        typer.echo(f"Configuration error:\n{exc}", err=True)
        raise typer.Exit(code=2) from exc


def _require_token(settings: Settings, command: str) -> None:
    """Fail fast when a command needs GITHUB_TOKEN and none is configured.

    Per-repo language fetches cost one request per repo and exhaust the
    unauthenticated rate limit almost immediately; waiting it out in the
    retry loop would stall the run for minutes with no benefit.
    """
    if settings.github_token is None:
        typer.echo(
            f"error: {command} needs GITHUB_TOKEN: it fetches language data "
            "for every repo, which exhausts the unauthenticated rate limit. "
            "Set GITHUB_TOKEN in .env or the environment.",
            err=True,
        )
        raise typer.Exit(code=2)


def _update_section_or_exit(
    target: Path,
    lines: list[str],
    section: str,
    *,
    dry_run: bool,
    bullets: bool = True,
) -> SectionUpdate:
    """Apply a marker-section update, mapping file errors to exit 1."""
    try:
        return update_section(target, lines, section=section, dry_run=dry_run, bullets=bullets)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        raise typer.Exit(code=1) from exc
    except MarkerNotFoundError as exc:
        logger.error("%s", exc)
        raise typer.Exit(code=1) from exc


@app.command("version")
def version() -> None:
    """Print the installed profileforge version."""
    typer.echo(__version__)


@app.command("config-show")
def config_show() -> None:
    """Validate settings and print the effective configuration (secrets masked)."""
    settings = _load_settings()
    setup_logging(settings.log_level, json_output=settings.log_json, force=True)
    for key, value in settings.masked_dump().items():
        typer.echo(f"{key}={value}")


@app.command("sync-activity")
def sync_activity(
    username: str | None = typer.Option(
        None, "--username", help="GitHub username (default: GH_USERNAME)."
    ),
    target: Path | None = typer.Option(
        None, "--target", help="README to update (default: TARGET_FILE)."
    ),
    max_lines: int | None = typer.Option(
        None, "--max-lines", help="Max activity lines (default: MAX_LINES)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing."),
) -> None:
    """Fetch recent public GitHub activity into the README's activity section."""
    settings = _load_settings()
    setup_logging(settings.log_level, json_output=settings.log_json, force=True)

    effective_username = username or settings.gh_username
    target_file = target if target is not None else settings.target_file
    line_limit = max_lines if max_lines is not None else settings.max_lines
    if line_limit < 1:
        typer.echo("error: --max-lines must be positive", err=True)
        raise typer.Exit(code=2)

    try:
        with GitHubClient.from_settings(settings) as client:
            raw_events = client.fetch_public_events(
                effective_username, per_page=settings.events_per_page
            )
    except GitHubAPIError as exc:
        logger.error("Failed to fetch GitHub activity: %s", exc)
        raise typer.Exit(code=1) from exc

    lines = build_activity_lines(raw_events, username=effective_username, max_lines=line_limit)
    if not lines:
        message = "No displayable activity found; README unchanged."
        logger.info(message)
        typer.echo(message)
        return

    result = _update_section_or_exit(target_file, lines, "activity", dry_run=dry_run)

    if dry_run:
        typer.echo(f"Would update {target_file} with {result.line_count} line(s):")
        for line in lines:
            typer.echo(f"  - {line}")
    elif result.changed:
        typer.echo(f"Updated {target_file} with {result.line_count} activity line(s).")
    else:
        typer.echo("README already up to date.")


@app.command("export-docs")
def export_docs(
    src: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Source directory to document.",
    ),
    dest: Path | None = typer.Option(
        None,
        "--dest",
        help="Output directory (default: <src>/reports/markdown_src_directory).",
    ),
    rollup: bool | None = typer.Option(
        None,
        "--rollup/--no-rollup",
        help="Combine each directory into one file (default: ROLLUP_DIRS).",
    ),
) -> None:
    """Export Python sources to Markdown documentation."""
    settings = _load_settings()
    setup_logging(settings.log_level, json_output=settings.log_json, force=True)
    try:
        result = export_project(
            src,
            dest,
            rollup_dirs=settings.rollup_dirs if rollup is None else rollup,
            excluded_dirs=settings.excluded_dirs,
        )
    except (FileNotFoundError, NoPythonFilesError) as exc:
        logger.error("%s", exc)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Wrote {result.files_written} Markdown file(s) to {result.dest_dir}.")


@app.command("sync-stats")
def sync_stats(
    target: Path | None = typer.Option(
        None, "--target", help="README to update (default: TARGET_FILE)."
    ),
    sparkline_days: int | None = typer.Option(
        None,
        "--sparkline-days",
        help="Trailing days in the sparkline (default: SPARKLINE_DAYS).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing."),
) -> None:
    """Refresh the README's stats section (plain-text code share + sparkline)."""
    settings = _load_settings()
    setup_logging(settings.log_level, json_output=settings.log_json, force=True)
    days = sparkline_days if sparkline_days is not None else settings.sparkline_days
    if days < 1:
        typer.echo("error: --sparkline-days must be positive", err=True)
        raise typer.Exit(code=2)
    _require_token(settings, "sync-stats")
    target_file = target if target is not None else settings.target_file
    moment = datetime.now(UTC)

    try:
        with GitHubClient.from_settings(settings) as client:
            repos = fetch_repo_summaries(client, settings.gh_username)
            share = fetch_code_share(client, settings.gh_username, repos)
            raw_events = client.fetch_public_events(settings.gh_username, per_page=100, max_pages=3)
    except GitHubAPIError as exc:
        logger.error("Failed to fetch GitHub data: %s", exc)
        raise typer.Exit(code=1) from exc

    events = [parse_event(raw) for raw in raw_events]
    start = sparkline_start(days, now=moment)
    sparkline_text = render_sparkline_text(build_daily_counts(events, days, now=moment), start)
    body = render_stats_body(share, sparkline_text, moment.strftime("%b %d, %Y"))

    result = _update_section_or_exit(target_file, [body], "stats", dry_run=dry_run, bullets=False)

    if dry_run and result.changed:
        typer.echo(f"Would update stats section in {target_file}.")
    elif result.changed:
        typer.echo(f"Updated stats section in {target_file}.")
    else:
        typer.echo("Stats section already up to date.")


@app.command("render-readme")
def render_readme_cmd(
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write to a file instead of stdout."
    ),
    max_lines: int | None = typer.Option(
        None, "--max-lines", help="Max activity lines (default: MAX_LINES)."
    ),
    sparkline_days: int | None = typer.Option(
        None,
        "--sparkline-days",
        help="Trailing days in the sparkline (default: SPARKLINE_DAYS).",
    ),
) -> None:
    """Render the Jinja2 profile README template with live GitHub data."""
    settings = _load_settings()
    setup_logging(settings.log_level, json_output=settings.log_json, force=True)
    days = sparkline_days if sparkline_days is not None else settings.sparkline_days
    if days < 1:
        typer.echo("error: --sparkline-days must be positive", err=True)
        raise typer.Exit(code=2)
    _require_token(settings, "render-readme")

    try:
        with GitHubClient.from_settings(settings) as client:
            context = build_profile_context(
                client,
                settings.gh_username,
                max_lines=max_lines if max_lines is not None else settings.max_lines,
                sparkline_days=days,
            )
    except GitHubAPIError as exc:
        logger.error("Failed to fetch GitHub data: %s", exc)
        raise typer.Exit(code=1) from exc

    rendered = render_readme(context)
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
        typer.echo(f"Wrote rendered README to {output}.")
    else:
        typer.echo(rendered)


@app.command("build-page")
def build_page(
    output: Path = typer.Option(
        Path("dist"), "--output", "-o", help="Directory to write the site into."
    ),
    projects: int = typer.Option(6, "--projects", help="Max project cards to showcase."),
    max_lines: int | None = typer.Option(
        None, "--max-lines", help="Max activity lines (default: MAX_LINES)."
    ),
    sparkline_days: int | None = typer.Option(
        None,
        "--sparkline-days",
        help="Trailing days in the sparkline (default: SPARKLINE_DAYS).",
    ),
) -> None:
    """Build the static portfolio site (index.html, profile.json, badges)."""
    settings = _load_settings()
    setup_logging(settings.log_level, json_output=settings.log_json, force=True)
    if projects < 1:
        typer.echo("error: --projects must be positive", err=True)
        raise typer.Exit(code=2)
    days = sparkline_days if sparkline_days is not None else settings.sparkline_days
    if days < 1:
        typer.echo("error: --sparkline-days must be positive", err=True)
        raise typer.Exit(code=2)

    try:
        with GitHubClient.from_settings(settings) as client:
            data = assemble_site_data(
                client,
                settings.gh_username,
                max_lines=max_lines if max_lines is not None else settings.max_lines,
                sparkline_days=days,
                projects_limit=projects,
            )
    except GitHubAPIError as exc:
        logger.error("Failed to fetch GitHub data: %s", exc)
        raise typer.Exit(code=1) from exc

    result = build_site(data, output)
    typer.echo(f"Built {len(result.files)} files in {result.output_dir}:")
    for name in result.files:
        typer.echo(f"  {name}")
