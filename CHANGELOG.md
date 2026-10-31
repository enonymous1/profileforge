# Changelog

All notable changes to profileforge are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- `fetch_repos` now paginates instead of silently truncating at 100 repos,
  so star counts, project selection, and code share are correct for users
  with more than 100 repositories.
- Issue/PR titles are escaped before being placed in Markdown links, so a
  title containing a link can no longer inject a live link into the
  profile README (and the site converter renders escaped spans as text).
- `format_compact` no longer renders counts of 999950–999999 as "1000k".
- A persistent rate limit now raises `GitHubRateLimitError` instead of
  falling through to `AssertionError`, and `RATE_LIMIT_MAX_WAIT=0` fails
  immediately as documented.
- The exporter skips unreadable files on `OSError` as well as decode
  errors, and no longer writes an empty rollup document for a directory
  whose files all failed to read.
- Code fences in exported Markdown grow longer than any backtick run in
  the source, so docstrings containing triple backticks no longer corrupt
  the document.

### Changed

- The README renderer and the portfolio site builder now share one fetch
  pipeline (`profile.snapshot.fetch_profile_snapshot`); a new data source
  is added in exactly one place.
- `build-page` builds into a staging directory and swaps it into place, so
  a failed build never leaves a half-new `dist/`.
- `setup_logging` no longer removes handlers installed by a host
  application (pass `force=True`, as the CLI does, to reconfigure from
  scratch).
- `get_settings` is no longer cached; environment changes after the first
  call are honored.
- `MAX_RETRIES=0` and `RATE_LIMIT_MAX_WAIT=0` are accepted (previously
  rejected by `PositiveInt`/`PositiveFloat` validation).
- `SPARKLINE_DAYS` is now a setting; `--sparkline-days` falls back to it
  when the flag is omitted.
- The version is single-sourced from `src/profileforge/__init__.py`
  (`[tool.hatch.version]`); `pyproject.toml` no longer carries its own
  copy.
- CI now tests Python 3.11, 3.12, and 3.13, caches pip, and runs weekly to
  catch dependency drift between pushes.
- A GitHub Pages workflow publishes the `build-page` output on every push
  to `main` (requires one-time Pages setup: Settings → Pages → Source
  GitHub Actions).

### Removed

- Dead `EVENT_ICONS` / `DEFAULT_ICON` maps in `github/formatters.py`
  (formatters hardcode their icons inline).

## [0.1.0]

- Initial public release: activity sync, code-share stats sync, Markdown
  doc export, Jinja2 profile README template, portfolio site builder,
  scheduled refresh workflow, typed client with retries/ETags, 231 tests.
