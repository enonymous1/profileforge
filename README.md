# profileforge

Tooling that powers a living GitHub profile/portfolio: it syncs recent GitHub
activity into the profile README, exports Python sources to Markdown docs, and
(eventually) builds a small static portfolio site from the same data pipeline.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env             # then set GH_USERNAME
profileforge config-show         # validates settings, prints effective config
profileforge --help
```

`python -m profileforge` works too.

## Layout

```
src/profileforge/
├── cli.py              # typer CLI (config-show, version; more subcommands per phase)
├── config.py           # validated, env-driven settings (single source of truth)
├── logging_config.py   # deterministic stdlib logging (console or JSON)
├── github/             # phase 2-3: typed models, formatter registry, resilient client
├── readme/             # phase 4: marker-section README updater
├── exporter/           # phase 5: scanner / tree / markdown renderers
├── profile/            # phase 8: stats, sparkline SVG, Jinja2 README template
└── site/               # phase 9: portfolio builder (templates, badges, profile.json)
```

See `docs/ARCHITECTURE.md` for the full phase plan.

## Configuration

All settings come from the environment (optionally via a `.env` file).
`GH_USERNAME` is required; everything else has sane defaults. Run
`profileforge config-show` to see the effective configuration with secrets masked.

## Usage

```bash
profileforge sync-activity --dry-run       # preview the README activity update
profileforge sync-activity                # fetch events and update the README
profileforge sync-stats --dry-run         # preview the stats section (sparkline + languages)
profileforge sync-stats                   # update the stats section
profileforge render-readme                # render the full README template to stdout
profileforge render-readme -o README.md   # ...or write it to a file
profileforge export-docs --dest ./docs-export
profileforge build-page --output ./dist   # portfolio site: index.html, profile.json, badges
```

`build-page` assembles the same pipeline as the README (user/repo summaries,
language stats, activity lines, sparkline) and renders a responsive,
dark/light-aware portfolio page with project cards, plus `profile.json` and
locally generated SVG badges (`dist/badges/*.svg`) you can embed anywhere.

`sync-stats` refreshes the `<!--START_SECTION:stats-->` marker with a
plain-text activity sparkline and top-language bars by share of code bytes
(fenced code blocks — GitHub strips inline SVG and styled HTML from
READMEs). It needs `GITHUB_TOKEN`: one language request per repo exhausts
the unauthenticated rate limit. `render-readme` renders the Jinja2 template
(`src/profileforge/profile/templates/readme.md.j2`) with live GitHub data —
handy for bootstrapping a profile README that already contains both marker
sections.

## Scheduled refresh

`.github/workflows/refresh-profile.yml` runs `sync-activity` and
`sync-stats` daily against your `<user>/<user>` profile repo and commits
the result. It needs a `PROFILE_PAT` secret, because `GITHUB_TOKEN`
cannot push to a different repository. (`GITHUB_TOKEN` itself is passed
to both sync steps: `sync-stats` fetches language data for every repo.)

Setup:

1. Create a personal access token (classic) with the `repo` scope:
   GitHub → Settings → Developer settings → Personal access tokens →
   Tokens (classic) → Generate new token (classic). Copy the token — it
   shows only once.
2. In this repo: Settings → Secrets and variables → Actions → New
   repository secret, name `PROFILE_PAT`, paste the token.
3. Prove it once by hand: Actions → Refresh profile → Run workflow. A
   green run should produce a `chore: refresh profile data [skip ci]`
   commit in your profile repo. After that the daily 04:17 UTC schedule
   runs itself.

## Development

```bash
ruff check src tests
ruff format --check src tests
mypy src
pytest
pytest --cov=profileforge --cov-report=term-missing   # 90% coverage gate (CI enforces)
```

Install the pre-commit hooks once (with the venv activated) so lint, format,
and type checks run on every commit:

```bash
pip install pre-commit
pre-commit install
```

CI (`.github/workflows/ci.yml`) runs ruff, ruff-format, mypy --strict, and
the test suite with the coverage gate on every push to `main` and every pull
request. Dependabot proposes weekly pip and GitHub Actions updates.
