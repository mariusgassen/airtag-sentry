# airtag-sentry

Self-hosted location history and movement alerts for a single AirTag, built for
one scenario: a stolen bike with an AirTag on it. It polls Apple's Find My
network via [`FindMy.py`](https://github.com/malmeloo/FindMy.py), stores a
location time series in Postgres, alerts you (ntfy.sh, Telegram, and/or Web
Push) when the tag moves further than expected or moves at all after a long
stillstand, and shows an installable PWA dashboard with a Leaflet map and
timeline.

## How it fits together

- **`app` service** — a scheduler (APScheduler) that polls every
  `polling.interval_minutes`, fetches the last ~7 days of location reports,
  dedupes them into Postgres, runs Haversine-distance movement detection, and
  fires notifications.
- **`dashboard` service** — a FastAPI app serving the reports/status API and
  a Vite + React PWA (map, timeline, AirTag management, "enable notifications"
  button).
- **`anisette` service** — [`anisette-v3-server`](https://github.com/Dadoum/anisette-v3-server),
  required for Apple's authentication flow.
- **`postgres` service** — stores `location_reports`, `alerts`, and
  `push_subscriptions`.

## ⚠️ What you must already have

- **An AirTag key for each AirTag you want to track**, entered through the
  dashboard once it's running. See
  [Extracting your AirTag key](#extracting-your-airtag-key) below.
- **An encryption key for storing those AirTag keys at rest.** See
  [AirTags: fully UI-managed, keys encrypted at rest](#airtags-fully-ui-managed-keys-encrypted-at-rest)
  below.
- **Your own Apple ID**, with 2FA you can complete interactively once.
- **A GitHub OAuth App**, so the dashboard can require you to log in with your
  own GitHub account. See [Dashboard login](#dashboard-login-github-oauth)
  below.
- Using this against an AirTag you don't own, or in a way that violates
  Apple's Terms of Service, is on you — this is for tracking your own
  property.

## AirTags: fully UI-managed, keys encrypted at rest

AirTags are not configured in `config.yaml` at all — there is nothing to edit
in a file. Add, rename, and remove them entirely through the dashboard's
**AirTags verwalten** (⚙️) panel; each one is a row in Postgres. The actual
secret key material is entered the same way (paste a base64 key or upload a
JSON export) and stored encrypted, never in `config.yaml` or `.env`.

This needs one encryption key in `.env`, used to encrypt/decrypt that stored
key material — it can't itself live in the database it protects:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the result into `.env` as `AIRTAG_KEY_ENCRYPTION_KEY`. Once the
dashboard is running (see [Local setup](#local-setup)), open the ⚙️ panel,
add an AirTag by name, and either paste its base64 key or upload the JSON
file exported per the next section.

## Extracting your AirTag key

This app does not need the AirTag physically present to get its key — the key
material is generated at pairing time and synced via iCloud to any Mac signed
into the same Apple ID, as a local encrypted record. You just need **a Mac
that has the AirTag paired in the Find My app** (the AirTag itself can be
anywhere, as long as it still shows up as an owned item in Find My).

On that Mac, with `findmy` installed (it's already a project dependency —
`pip install -e ".[dev]"`, or just `pip install findmy` if you don't want the
whole project there):

```bash
python -m findmy decrypt --out-dir data/keys
```

This will prompt for your macOS login keychain password / Touch ID (possibly
twice) to read the `BeaconStore` Keychain item, then decrypts the local Find My
accessory records and writes one `<uuid>.json` file per paired accessory
(AirTags, AirPods, paired Macs/iPhones, etc.) into `data/keys/`. Files are
named by internal UUID, not by display name, so open each one and check its
`"name"` field to find the AirTag you're after, then upload that file
directly in the dashboard's AirTags-verwalten panel (see above) — no need to
rename it or reference it from `config.yaml`.

This only works for accessories already paired to your own Apple ID on that
Mac — extract keys for your own property only.

## Dashboard login (GitHub OAuth)

The dashboard requires logging in with a specific GitHub account before
showing any data. To set it up:

1. Create a GitHub OAuth App at
   [github.com/settings/applications/new](https://github.com/settings/applications/new).
   - Homepage URL: anything (GitHub requires a value).
   - Authorization callback URL: `https://<your-domain>/auth/callback`.
2. Put the resulting Client ID/Secret, your own GitHub username, and a random
   session secret into `.env`:
   ```
   GITHUB_CLIENT_ID=...
   GITHUB_CLIENT_SECRET=...
   GITHUB_ALLOWED_LOGIN=your-github-username
   SESSION_SECRET_KEY=...   # e.g. `openssl rand -hex 32`
   ```

Note: a GitHub OAuth App supports only **one** callback URL. If you want to
test the login flow locally as well as in production, create a second OAuth
App for local development (`http://localhost:8000/auth/callback`) with its
own `.env.local`-style credentials — otherwise just test everything except the
login flow itself locally, and verify login against the deployed instance.

The session cookie is always marked `Secure`/HTTPS-only, which browsers will
only ever send back over an HTTPS connection. This matches the deployment
model this repo assumes (Coolify terminates TLS at the edge, so the browser
always talks to the dashboard over `https://`). **If you access the dashboard
over plain HTTP** — e.g. running it directly on `http://localhost:8000` with
no TLS-terminating proxy in front — the browser will silently refuse to send
the cookie back, and login will loop back to `/login` with no clear error.
For that case, set `https_only=False` on the `SessionMiddleware` call in
`airtag_sentry/web/app.py`.

## Local setup

```bash
cp config.example.yaml config.yaml   # adjust polling/movement thresholds
cp .env.example .env                 # fill in POSTGRES_* creds, GitHub OAuth, encryption key, etc.
python scripts/generate_vapid_keys.py   # paste the output into .env for Web Push

# Local (non-Coolify) only: publish the dashboard on localhost.
cp docker-compose.override.yml.example docker-compose.override.yml
```

`config.yaml` only has Apple/polling/movement/web settings — AirTags
themselves are added later, through the dashboard. For Docker Compose, set
`apple.anisette.mode: remote` and `apple.anisette.remote_url: http://anisette:6969`
so polling uses the bundled anisette container instead of generating anisette
data in-process.

```bash
docker compose up -d postgres anisette
docker compose run --rm app python -m airtag_sentry login   # interactive, needs your real 2FA code
docker compose up -d
```

The dashboard is then at `http://localhost:8000` (with the override file from
above — without it, plain `docker compose up` doesn't publish any host port,
matching how Coolify runs it) — open it, log in with
GitHub, and add each AirTag's key via the ⚙️ panel (see
[AirTags: fully UI-managed, keys encrypted at rest](#airtags-fully-ui-managed-keys-encrypted-at-rest)).
Until a key is added, that tag's poll is skipped with a log line — it won't
crash the scheduler.

**The `login` step cannot be automated or run in CI** — it needs your Apple ID
password and a live 2FA code from your phone. Run it once; the resulting
session token (`data/account.json`, in the `app_data` volume) is reused by the
scheduler and dashboard afterwards.

### CLI reference

```
python -m airtag_sentry login   # interactive Apple ID login + 2FA, persists the session
python -m airtag_sentry poll    # run a single poll immediately and exit
python -m airtag_sentry run     # run the scheduler forever (used by the `app` service)
python -m airtag_sentry serve   # run the dashboard (used by the `dashboard` service)
```

## Notifications

Each backend is optional and independent — configure any combination in `.env`:

| Backend  | Enable by setting                                          |
|----------|-------------------------------------------------------------|
| ntfy.sh  | `NTFY_TOPIC_URL` (e.g. `https://ntfy.sh/your-secret-topic`) |
| Telegram | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`                    |
| Web Push | `VAPID_PUBLIC_KEY` + `VAPID_PRIVATE_KEY` + `VAPID_SUBJECT`, then click "Enable notifications" on the dashboard |

## Installing the dashboard as an app (PWA)

Open the dashboard in a browser (Chrome/Edge on desktop or Android, Safari
16.4+ on iOS/iPadOS), then "Install app" / "Add to Home Screen". Once
installed, click **Benachrichtigungen aktivieren** ("Enable notifications") to
subscribe that device to Web Push alerts — they'll arrive as real OS
notifications, even when the app isn't open.

## Deploying with Coolify

1. Create a new **Docker Compose** resource in Coolify pointed at this repo
   (`docker-compose.yml` at the root).
2. Every variable from `.env.example` is declared explicitly in
   `docker-compose.yml`'s `environment:` blocks, so Coolify's environment tab
   lists each one individually — fill them in there.
3. Uncomment `SERVICE_FQDN_DASHBOARD_8000` in your env — Coolify auto-assigns
   a public domain + TLS to the `dashboard` service's port 8000. It's the
   only `SERVICE_FQDN_*` variable in the stack, so the whole deployment sits
   behind a single domain — the `dashboard` service isn't given a host port
   mapping in `docker-compose.yml`; Coolify's proxy reaches it directly over
   the internal Docker network.
4. Deploy. Coolify persists the `postgres_data` and `app_data` named volumes
   across redeploys automatically.
5. Run the login step once against the deployed stack: open the `app`
   service's container terminal in Coolify (or SSH to the host) and run
   `python -m airtag_sentry login` interactively.

## Movement detection

Two alert conditions, both based on the Haversine distance between
consecutive reports:
- **`distance_threshold`**: the tag moved more than
  `movement.distance_threshold_meters` (default 100 m) since the last report.
- **`stillstand_movement`**: the tag had been stationary for at least
  `movement.stillstand_hours` (default 24 h) and then moved more than
  `movement.stillstand_movement_meters` (default 15 m) — catches "someone
  finally rolled it away" moves too small to trip the main threshold.

The very first poll backfills ~7 days of history; alerts for that backfill are
suppressed unless you set `movement.alert_on_backfill: true`.

## Database migrations

Schema changes are managed with [Alembic](https://alembic.sqlalchemy.org/)
(`alembic/versions/`). `poll`/`run`/`serve` all call `airtag_sentry.migrate.upgrade_to_head()`
once at startup, so there's no separate migration step to remember. The
connection URL comes from the same `POSTGRES_*` env vars the rest of the app
uses (see `alembic/env.py`) — nothing to configure separately in `alembic.ini`.

To add a schema change: `alembic revision -m "description"`, fill in
`upgrade()`/`downgrade()` in the generated file under `alembic/versions/`, and
never edit a migration that has already shipped — add a new one instead.

Run migrations manually (e.g. to inspect what would happen) with:
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
npm run build   # production build - writes straight into
                 # airtag_sentry/web/static (same command Docker's build stage runs)
```

## Known limitations

- The Apple login/2FA flow, a live poll against the real Find My network, and
  an actual Web Push round-trip to a browser's push service all require
  real credentials/devices and were **not** exercised end-to-end by whoever
  built this — only unit/integration-tested against a real local Postgres and
  a hand-seeded dashboard. Verify these yourself after setup.
- Single user (one allowed GitHub login), no native mobile app beyond the
  installable PWA — intentional per the original spec's non-goals. Multiple
  AirTags per Apple ID are supported, added/managed entirely via the
  dashboard's ⚙️ panel.
- **Upgrading from an earlier version of this project**: this is still early,
  pre-production software with no real deployed data to preserve, so schema
  changes have not carried a backward-compatible upgrade path so far (most
  recently: AirTags moving from `config.yaml` entries to a real `airtags`
  table, and the hand-rolled migration tracker being replaced by Alembic). If
  you deployed an earlier version, the simplest path is to drop and recreate
  the database, then re-enter each AirTag and its key via the dashboard.
- If Apple changes the Find My protocol, `FindMy.py` (and therefore this app)
  can break without warning — keep an eye on its upstream repo.
