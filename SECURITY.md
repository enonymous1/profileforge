# Security Policy

## Supported versions

Only the latest release on `main` receives fixes. This is a small tool with
a single maintainer; older tags are not patched.

## Reporting a vulnerability

Open a GitHub issue with the `security` label, or email the maintainer via
the address on their GitHub profile. Please include:

- What you observed and how to reproduce it.
- The version/commit and the command involved.
- Whether any secret or token could have been exposed.

Do not post a working exploit or a real token in a public issue.

## Token handling (by design)

- `GITHUB_TOKEN` / `PROFILE_PAT` are read from the environment only, held
  as `SecretStr`, and never printed (settings dumps mask them).
- `.env` is gitignored; only `.env.example` (placeholders, no real values)
  is committed.
- The refresh workflow passes tokens via secrets, never via command-line
  arguments or logs.
- The site builder and README renderer only ever read *public* GitHub
  data; they never request private repository content.
