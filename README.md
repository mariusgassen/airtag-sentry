<p align="center">
  <img src="frontend/public/icons/icon-192.png" width="96" height="96" alt="AirTag Sentry logo">
</p>

<h1 align="center">AirTag Sentry</h1>

<p align="center">
  <a href="https://github.com/mariusgassen/airtag-sentry/actions/workflows/ci.yml">
    <img src="https://github.com/mariusgassen/airtag-sentry/actions/workflows/ci.yml/badge.svg" alt="CI build status">
  </a>
</p>

Self-hosted location history and movement alerts for a single AirTag, built
for one scenario: a stolen bike with an AirTag on it. It polls Apple's Find
My network, stores a location time series in Postgres, alerts you when the
tag moves, and shows an installable PWA dashboard with a map and timeline.

## How it works

AirTag Sentry polls Apple's Find My network via
[`FindMy.py`](https://github.com/malmeloo/FindMy.py) on a schedule, dedupes
new location reports into Postgres, and runs Haversine-distance movement
detection on each new report. A move that's bigger than expected — or any
move at all after a long stillstand — triggers a notification through
whichever backends you've enabled, and shows up on the dashboard's map and
timeline.

| Service     | Role                                                                                                  |
|-------------|-------------------------------------------------------------------------------------------------------|
| `app`       | APScheduler polling loop (default every 15 min): fetch → dedupe → movement check → notify             |
| `dashboard` | FastAPI API + installable Vite/React PWA — map, timeline, AirTag management, notification opt-in      |
| `anisette`  | [`anisette-v3-server`](https://github.com/Dadoum/anisette-v3-server), Apple's authentication handshake |
| `postgres`  | Stores location reports, alerts, and push subscriptions                                               |

AirTags themselves are fully UI-managed — add, rename, and remove them from
the dashboard's AirTags list. Their key material is entered the same way
(paste a base64 key or upload a JSON export) and stored encrypted, never in
`.env`.

## Getting started

**Prerequisites**
- Your own Apple ID, with 2FA you can complete interactively once.
- A Mac with the AirTag paired in Find My, to extract its key (see below).
- A GitHub OAuth App, so the dashboard can require your GitHub login (see below).

### 1. Configure secrets

```bash
cp .env.example .env
```

Generate the two keys the app needs and paste them into `.env`:

```bash
# AIRTAG_KEY_ENCRYPTION_KEY — encrypts AirTag keys at rest. Back it up: losing
# it makes every stored AirTag key permanently undecryptable.
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY — for Web Push notifications.
python scripts/generate_vapid_keys.py
```

Then create a [GitHub OAuth App](https://github.com/settings/applications/new)
(callback URL `https://<your-domain>/auth/callback`) and add its credentials:

```
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
GITHUB_ALLOWED_LOGIN=your-github-username
SESSION_SECRET_KEY=...   # e.g. `openssl rand -hex 32`
```

For local development, publish the dashboard on `localhost`:

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
```

### 2. Extract your AirTag's key

The key material is generated at pairing time and synced via iCloud to any
Mac signed into the same Apple ID — the AirTag itself doesn't need to be
present. On that Mac, with `findmy` installed (`pip install -e ".[dev]"`,
or just `pip install findmy`):

```bash
python -m findmy decrypt --out-dir data/keys
```

This prompts for your macOS keychain password/Touch ID and writes one
`<uuid>.json` file per paired accessory into `data/keys/`. Open each file
and check its `"name"` field to find your AirTag, then upload it directly
in that AirTag's detail view in the dashboard.

### 3. Start it up

```bash
docker compose up -d postgres anisette
docker compose run --rm app python -m airtag_sentry login   # interactive Apple ID + 2FA, once
docker compose up -d
```

Open `http://localhost:8000`, log in with GitHub, and add each AirTag's key
from its detail view. A tag without a key yet is simply skipped each poll
(logged, not fatal) until you add one.

The `login` step needs your real Apple ID password and a live 2FA code, so
it can't run in CI — run it once per deployment. The resulting session
token (`data/account.json`) is reused by the scheduler and dashboard after
that.

### CLI reference

```
python -m airtag_sentry login         # interactive Apple ID login + 2FA, persists the session
python -m airtag_sentry login-owner   # optional: same, for owner device tracking - see below
python -m airtag_sentry poll          # run a single poll immediately and exit
python -m airtag_sentry run           # run the scheduler forever (used by the `app` service)
python -m airtag_sentry serve         # run the dashboard (used by the `dashboard` service)
```

## Owner device tracking (optional): "moved without you" alerts

Ordinary movement alerts only look at the AirTag's own history - they can't
tell "you rode your bike to the store" apart from "someone took it while you
were at work." Doing that needs a second signal: where *you* were when the
tag moved.

`FindMy.py`'s AirTag lookups (above) use Apple's offline-finding/crowd-sourced
network, which mostly only produces reports for a device that's off, dead, or
in airplane mode - not useful for tracking a phone that's normally on and
connected. Instead, this feature uses Apple's separate, classic **Find My
iPhone web service** (the same one behind `icloud.com/find`) via the
[`pyicloud`](https://github.com/picklepete/pyicloud) library, which gives a
near-real-time location for your own signed-in devices. This is a second,
independent Apple session from the AirTag one above - its own login, its own
2FA, its own persisted session - and it's entirely optional.

To enable it:

1. Generate an **app-specific password** for your Apple ID at
   [appleid.apple.com](https://appleid.apple.com) -> Sign-In and Security ->
   App-Specific Passwords. Use this, not your real Apple ID password - it can
   be revoked independently if you ever need to.
2. Set `APPLE_OWNER_ID` and `APPLE_OWNER_PASSWORD` in `.env`.
3. Run the login step once (same TTY/2FA constraint as `login`):
   ```bash
   docker compose run --rm app python -m airtag_sentry login-owner
   ```
   This persists a trusted session to `APPLE_OWNER_SESSION_PATH` (default
   `data/pyicloud_session`, inside the same `app_data` volume as
   `APPLE_STORE_PATH`) - re-authentication is only needed roughly every two
   months, per `pyicloud`'s session lifetime, not on every poll.

Once configured, every poll also records your device's current location and,
when a normal movement alert fires *and* the tag's new position is far from
your last-known location, additionally fires a `moved_without_owner` alert -
see [Movement detection](#movement-detection) for the two tunable settings
this adds. Leaving `APPLE_OWNER_ID`/`APPLE_OWNER_PASSWORD` unset disables the
feature entirely; everything else works exactly as without it.

## Notifications

Each backend is optional and independent — enable any combination in `.env`:

| Backend  | Enable by setting                                                                                             |
|----------|-----------------------------------------------------------------------------------------------------------------|
| ntfy.sh  | `NTFY_TOPIC_URL` (e.g. `https://ntfy.sh/your-secret-topic`)                                                     |
| Telegram | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`                                                                       |
| Web Push | `VAPID_PUBLIC_KEY` + `VAPID_PRIVATE_KEY` + `VAPID_SUBJECT`, then click "Enable notifications" on the dashboard |

Treat the VAPID keypair like the encryption key above — generate it once and
back it up. Every device's push subscription is tied to the public key that
was active when it subscribed, so devices re-subscribe after a key change.

## Movement detection

Two alert conditions, both based on the Haversine distance between
consecutive reports, tunable from the dashboard's ⚙️ Settings panel:

- **`distance_threshold`** — the tag moved more than this distance
  (default 100 m) since the last report.
- **`stillstand_movement`** — the tag was stationary for at least
  `stillstand_duration` (default 24 h) and then moved more than this
  threshold (default 15 m) — catches slow moves too small to trip the main
  threshold.

The first poll backfills ~7 days of history; alerts from that backfill are
suppressed unless "Alarm beim ersten Abruf" is enabled in Settings.

If [owner device tracking](#owner-device-tracking-optional-moved-without-you-alerts)
is configured, either of the alerts above also triggers a check for a
third, additional alert — it never replaces the other two:

- **`moved_without_owner`** — one of the alerts above just fired, *and* the
  tag's new position is more than the away-distance threshold (default
  150 m) from your device's last-known location. If that location reading
  is older than the max-age setting (default 60 min), this check is skipped
  entirely for that alert rather than guessing off stale data.

## Configuration reference

**Env vars** (`.env`) — infra-shaped settings that need a redeploy anyway:

| Variable             | Default              | Meaning                                                                          |
|-----------------------|----------------------|-----------------------------------------------------------------------------------|
| `APPLE_STORE_PATH`    | `data/account.json`  | Where the Apple session token from `login` is persisted.                        |
| `ANISETTE_MODE`       | `local`               | `local` (in-process) or `remote` (use `anisette-v3-server`). Docker Compose sets this to `remote`. |
| `ANISETTE_LIBS_PATH`  | `data/ani_libs.bin`   | Cache path for the local anisette provider's libraries.                          |
| `ANISETTE_REMOTE_URL` | unset                 | URL of the anisette server. Required when `ANISETTE_MODE=remote`.               |
| `WEB_HOST`            | `0.0.0.0`             | Dashboard bind address.                                                          |
| `WEB_PORT`            | `8000`                | Dashboard bind port.                                                             |

**Dashboard settings** (⚙️ panel, stored in Postgres) — polling interval,
the movement thresholds above, and (if owner device tracking is configured)
the away-distance/max-age thresholds. Changes apply on the `app` service's
next poll, no restart needed.

## Installing the dashboard as an app (PWA)

Open the dashboard in Chrome/Edge (desktop or Android) or Safari 16.4+
(iOS/iPadOS), then "Install app" / "Add to Home Screen". Once installed,
click "Enable notifications" to subscribe that device to Web Push — alerts
then arrive as real OS notifications, even when the app isn't open.

## Deploying with Coolify

1. Create a **Docker Compose** resource in Coolify pointed at this repo's
   `docker-compose.yml`.
2. Every setting from `.env.example` is declared in `docker-compose.yml`'s
   `environment:` blocks, so Coolify's environment tab lists each one —
   fill them in there.
3. Uncomment `SERVICE_FQDN_DASHBOARD_8000` — Coolify assigns a public
   domain + TLS to the `dashboard` service.
4. Deploy. Coolify persists the `postgres_data` and `app_data` volumes
   across redeploys.
5. Run the login step once against the deployed stack: open the `app`
   service's container terminal in Coolify and run
   `python -m airtag_sentry login`.

The `dashboard` service exposes `GET /health` (round-trips to Postgres) as
its Docker healthcheck, so Coolify's health indicator and zero-downtime
deploys reflect whether it's actually serving.

## Database migrations

Schema changes are managed with [Alembic](https://alembic.sqlalchemy.org/).
`poll`/`run`/`serve` all apply pending migrations automatically at startup,
so there's no separate migration step in normal operation.

To add a schema change: `alembic revision -m "description"`, fill in
`upgrade()`/`downgrade()` in the generated file, and add a new migration
rather than editing one that's already shipped.

```bash
alembic upgrade head    # apply
alembic downgrade -1    # roll back one step
alembic history         # see the chain
```

## Development

Backend:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest   # movement math + notifier payloads run standalone;
         # DB tests need a reachable Postgres at $TEST_DATABASE_URL
         # (defaults to postgresql://airtag:airtag@localhost:5432/airtag_sentry_test)
```

Frontend (Vite + React + TypeScript, in `frontend/`):
```bash
cd frontend
npm install
npm run dev     # dev server on :5173, proxies /api, /login, /logout, /auth
                 # to a separately-running `python -m airtag_sentry serve` on :8000
npm run build   # production build, writes into airtag_sentry/web/static
                 # (same command Docker's build stage runs)
```

## Scope

Single user (one allowed GitHub login), no native mobile app beyond the
installable PWA — by design. Multiple AirTags per Apple ID are supported,
managed entirely via the dashboard. Use this only on AirTags you own.

Both AirTag tracking (`FindMy.py`) and owner device tracking (`pyicloud`,
optional) talk to unofficial Apple APIs and can break without warning —
keep an eye on their upstream repos. Owner tracking is entirely opt-in:
leaving `APPLE_OWNER_ID`/`APPLE_OWNER_PASSWORD` unset means it never runs.
