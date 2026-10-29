# Architecture

`profileforge` is a small, boring-in-a-good-way Python package: one validated
settings object, deterministic logging, and a typer CLI fronting focused
subpackages. Each phase below lands as one module (or a tight group) with
tests, keeping behavior byte-identical to the legacy scripts until the new
features are explicitly added.

## Module responsibilities

- `config.py` — the only place that reads the environment. Validates once at
  startup (`get_settings()` is cached); fails fast with a clear message
  instead of silently using a wrong default.
- `logging_config.py` — stdlib-only logging setup. Console by default, JSON
  with `LOG_JSON=true`. No `print()` in library code, ever.
- `cli.py` — typer entry point. Library code raises typed exceptions; only
  the CLI decides exit codes.
- `github/models.py` — typed event dataclasses; kills the `.get()` soup.
- `github/formatters.py` — `dict[event_type, formatter]` registry replacing
  the if/elif chain. New event type = one small function.
- `github/client.py` — httpx session with retries, rate-limit backoff, and
  ETag conditional requests so the scheduled job survives 403/429s.
- `readme/updater.py` — marker-section splice with atomic writes and
  `--dry-run`.
- `exporter/` — `scanner.py` (discovery + exclusion), `tree.py` (tree
  rendering), `markdown.py` (mirror/rollup renderers).
- `profile/` — profile-page data and rendering: `stats.py` (user/repo
  summaries, language ranking), `sparkline.py` (locally generated SVG
  activity chart — no third-party image service), `renderer.py` (Jinja2
  template context + `templates/readme.md.j2`).
- `site/` — portfolio builder: `data.py` (site model from the shared
  pipeline), `builder.py` (renders `dist/`), `badges.py` (local SVG badges),
  `html.py` (activity Markdown → HTML), Jinja2 templates + `styles.css`
  (dark/light aware, responsive).

## Phase plan

1. Packaging skeleton, `config.py`, `logging_config.py`, CLI stub. ✅
2. `github/models.py` + `formatters.py` (registry). ✅
3. `github/client.py` (resilient client). ✅
4. `readme/updater.py`. ✅
5. `exporter/` modules. ✅
6. `cli.py` wiring (`sync-activity`, `export-docs`; `build-page` with phase 9). ✅
7. Tooling: ruff/mypy/pre-commit/CI enforcement, coverage gate. ✅
8. Profile flash: Jinja2 README template, scheduled refresh workflow. ✅
9. Portfolio site builder + generated SVG badges. ✅

## Conventions

- `src/` layout, `pyproject.toml` is the single config file.
- Importing a module must have no side effects (no env reads, no I/O).
- Exceptions carry context; the CLI translates them to exit codes.
- Tests use recorded fixtures — no network in the test suite.
