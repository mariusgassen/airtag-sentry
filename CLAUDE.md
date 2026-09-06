# CLAUDE.md

Guidance for Claude Code (or any future contributor/agent) working in this
repository. Read this before making changes.

## Hard constraint: UI-first, no CLI-only setup steps

**Everything the user needs to do to operate this app should be doable from
the dashboard UI.** The CLI (`python -m airtag_sentry ...`) only has
`poll`/`run`/`serve` - container entrypoints, not user setup steps. Apple ID
login (AirTag tracking, and optional owner device tracking) used to be
CLI-only interactive scripts; it's now a dashboard Settings ⚙️ → **Apple-Konten**
flow (`auth.py`/`owner_tracking.py`'s stateful `start_login`/`request_2fa_code`/
`submit_2fa_code` functions, `web/app.py`'s `/api/apple/*` routes,
`AppleConnectPanel.tsx`).

When a future feature needs setup or an ongoing user action:
- Design it as a dashboard UI flow (a form, a panel, a button) first.
- Only fall back to a CLI step if there's a real technical reason a browser
  request can't do it (there usually isn't one here — this is a FastAPI app
  that already handles OAuth, encrypted key/credential storage, and Apple
  login entirely through the UI).
- If you add or touch a CLI subcommand in `cli.py`, ask whether it should
  become a UI flow instead rather than assuming CLI is fine because some
  older code once did it that way.

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
- AirTag key material and the owner-tracking Apple password are never
  stored in `.env`/config files — entered via the dashboard, encrypted at
  rest in Postgres (`keystore.py`). The AirTag-tracking Apple session is the
  one exception: `FindMy.py`'s `AppleAccount.to_json()` already persists a
  resumable session without the password, so it's a plain file
  (`APPLE_STORE_PATH`), not a DB secret - no long-lived password to protect.
- Verification before calling something done: `pytest` against a real local
  Postgres (not mocked), `cd frontend && npx tsc -b && npx vite build &&
  npx oxlint`, and `docker compose config` with a throwaway `.env`.
