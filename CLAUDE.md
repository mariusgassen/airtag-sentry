# CLAUDE.md

Guidance for Claude Code (or any future contributor/agent) working in this
repository. Read this before making changes.

## Hard constraint: UI-first, no CLI-only setup steps

**Everything the user needs to do to operate this app should be doable from
the dashboard UI.** The CLI (`python -m airtag_sentry ...`) is not a
first-class interface for end users — it exists today only because some
flows (Apple ID login) were built as blocking interactive scripts
(`input()`/`getpass.getpass()`) for expedience, not because the underlying
protocol requires a terminal.

Concretely, when a feature needs setup or an ongoing action:
- Design it as a dashboard UI flow (a form, a panel, a button) first.
- Only fall back to a CLI step if there's a real technical reason a browser
  request can't do it (there usually isn't one here — this is a FastAPI app
  that already handles OAuth, encrypted key upload, and settings entirely
  through the UI).
- If you add or touch a CLI subcommand in `cli.py`, ask whether it should
  become a UI flow instead rather than assuming CLI is fine because that's
  the existing pattern for adjacent code (e.g. `login`).

**Known debt, not the target state**: `python -m airtag_sentry login` and
`login-owner` (Apple ID + 2FA for AirTag tracking and, optionally, owner
device tracking) are currently CLI-only. This is tracked in
`tasks/roadmap.md` as a feature to move into the dashboard (a login form +
2FA code entry step, mirroring the existing AirTag-key-upload UI). Treat
this as backlog, not as precedent for building new setup flows as CLI
commands.

## Project shape

- `airtag_sentry/` — Python backend: `tracker.py`/`scheduler.py` (the `app`
  service, a polling loop), `web/app.py` (FastAPI dashboard API + static
  PWA, the `dashboard` service), `db.py` (plain psycopg, no ORM),
  `movement.py` (pure, DB-free alert logic — keep it that way), `auth.py` /
  `owner_tracking.py` (two independent Apple sessions — AirTag lookups via
  `FindMy.py`, owner-device location via `pyicloud` — don't conflate them).
- `frontend/` — Vite + React + TypeScript PWA, builds straight into
  `airtag_sentry/web/static`.
- `alembic/versions/` — schema migrations. Never edit a migration that has
  already shipped; add a new one. `poll`/`run`/`serve` apply pending
  migrations automatically at startup.
- `tasks/todo.md` — historical changelog (`vN:` entries + a review section
  per version). Add a new entry here for any shipped feature.
- `tasks/roadmap.md` — forward-looking, prioritized backlog. Not
  commitments; move an item into `todo.md` as it's actually built.
- `tasks/lessons.md` — corrections from the user, logged with the pattern
  and the rule adopted to avoid repeating it.

## Established conventions (from the existing changelog)

- **No backward-compatibility shims.** This is still pre-production
  software with no real deployed data to preserve — breaking config/schema
  changes are fine and have been made repeatedly (config.yaml → env vars →
  DB-backed settings; AirTag keys moving storage location twice). Document
  the break in the README/changelog instead of adding a compat layer.
- **Single-user, single-Apple-ID-account app.** No multi-user support is a
  deliberate non-goal — don't add abstractions for it.
- Config comes entirely from environment variables (`.env`), validated in
  `config.py`. No `config.yaml`.
- AirTag key material is never stored in `.env`/config files — entered via
  the dashboard, encrypted at rest in Postgres.
- Verification before calling something done: `pytest` against a real local
  Postgres (not mocked), `cd frontend && npx tsc -b && npx vite build &&
  npx oxlint`, and `docker compose config` with a throwaway `.env`.
