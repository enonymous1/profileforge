# Contributing

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pip install pre-commit && pre-commit install
```

## Gates (all enforced by CI)

```bash
ruff check src tests
ruff format --check src tests
mypy src
pytest --cov=profileforge --cov-report=term-missing --cov-fail-under=90
```

## Working style

- **Preview before writing.** Every sync command has a `--dry-run` mode;
  `render-readme` prints to stdout by default. Trial-sync against a scratch
  README and review the diff before syncing a real profile.
- **Library code never decides exit codes.** Raise typed exceptions from
  library code; only the CLI maps them to exits.
- **No `print()` in library code.** Use `logging.getLogger(__name__)`.
- **One fetch pipeline.** New live data goes through
  `profile.snapshot.fetch_profile_snapshot`, not into a second ad-hoc
  fetch in the renderer or the site builder.
- **Golden tests for formatting.** If you change activity lines, the stats
  body, or exported Markdown, update the golden tests deliberately and say
  so in the PR — a golden diff is a behavior change, not noise.
- **Docs follow code.** If a change alters a command, a setting, or a
  workflow, update the README and `docs/ARCHITECTURE.md` in the same PR.

## Releases

1. Bump `__version__` in `src/profileforge/__init__.py` (the single
   source of truth).
2. Add a CHANGELOG entry.
3. Tag `vX.Y.Z`, push the tag, and create a GitHub Release from it.
