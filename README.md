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
  the static PWA (map, timeline, "enable notifications" button).
- **`anisette` service** — [`anisette-v3-server`](https://github.com/Dadoum/anisette-v3-server),
  required for Apple's authentication flow.
- **`postgres` service** — stores `location_reports`, `alerts`, and
  `push_subscriptions`.

## ⚠️ What you must already have

- **An AirTag key for each AirTag you want to track**, entered through the
  dashboard once it's running. See
  [Extracting your AirTag key](#extracting-your-airtag-key) below.
- **An encryption key for storing those AirTag keys at rest.** See
  [AirTag key storage](#airtag-key-storage-config-first-encrypted-at-rest)
  below.
- **Your own Apple ID**, with 2FA you can complete interactively once.
- **A GitHub OAuth App**, so the dashboard can require you to log in with your
  own GitHub account. See [Dashboard login](#dashboard-login-github-oauth)
  below.
- Using this against an AirTag you don't own, or in a way that violates
  Apple's Terms of Service, is on you — this is for tracking your own
  property.

## AirTag key storage (config-first, encrypted at rest)

`config.yaml`'s `airtags:` list only declares each AirTag's identity — `id`
and display `name`. The actual secret key material never goes in
`config.yaml` or `.env`; instead it's entered through the dashboard's
**AirTags verwalten** (⚙️) panel, encrypted, and stored in Postgres.

This needs one encryption key in `.env`, used to encrypt/decrypt that stored
key material — it can't itself live in the database it protects:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the result into `.env` as `AIRTAG_KEY_ENCRYPTION_KEY`. Once the
dashboard is running (see [Local setup](#local-setup)), open the ⚙️ panel,
pick the AirTag, and either paste its base64 key or upload the JSON file
exported per the next section.

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
cp config.example.yaml config.yaml   # adjust thresholds, airtag name, key source
cp .env.example .env                 # fill in DATABASE_URL, notifier creds, etc.
python scripts/generate_vapid_keys.py   # paste the output into .env for Web Push

# Local (non-Coolify) only: publish the dashboard on localhost.
cp docker-compose.override.yml.example docker-compose.override.yml
```

Edit `config.yaml`:
- Add one entry (`id` + `name`) per AirTag under `airtags:`.
- For Docker Compose, set `apple.anisette.mode: remote` and
  `apple.anisette.remote_url: http://anisette:6969` so polling uses the
  bundled anisette container instead of generating anisette data in-process.

```bash
docker compose up -d postgres anisette
docker compose run --rm app python -m airtag_sentry login   # interactive, needs your real 2FA code
docker compose up -d
```

The dashboard is then at `http://localhost:8000` (with the override file from
above — without it, plain `docker compose up` doesn't publish any host port,
matching how Coolify runs it) — open it, log in with
GitHub, and add each AirTag's key via the ⚙️ panel (see
[AirTag key storage](#airtag-key-storage-config-first-encrypted-at-rest)).
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

Schema changes live as an ordered list of one-time SQL migrations in
`airtag_sentry/migrations.py`, each recorded in a `schema_migrations` table
once applied (`SELECT * FROM schema_migrations ORDER BY applied_at` shows the
history). Both `poll`/`run` and `serve` call `run_migrations()` on startup, so
there's no separate migration step to remember — a fresh database and an
upgraded one both replay the same history and end up in the same state.
Never edit a migration that has already shipped; add a new entry to the list
instead.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest   # movement math + notifier payloads run standalone;
         # DB tests need a reachable Postgres at $TEST_DATABASE_URL
         # (defaults to postgresql://airtag:airtag@localhost:5432/airtag_sentry_test)
```

## Known limitations

- The Apple login/2FA flow, a live poll against the real Find My network, and
  an actual Web Push round-trip to a browser's push service all require
  real credentials/devices and were **not** exercised end-to-end by whoever
  built this — only unit/integration-tested against a real local Postgres and
  a hand-seeded dashboard. Verify these yourself after setup.
- Single user (one allowed GitHub login), no mobile app beyond the installable
  PWA — intentional per the original spec's non-goals. Multiple AirTags per
  Apple ID are supported via `config.yaml`'s `airtags:` list.
- **Upgrading from a version that used `accessory_json_path` or
  `AIRTAG_PRIVATE_KEY_B64_<ID>`**: those config/env fields are gone. Remove
  them from `config.yaml`/`.env`, set `AIRTAG_KEY_ENCRYPTION_KEY`, and
  re-enter each AirTag's key (the same base64 string or JSON file you already
  have) once via the dashboard's ⚙️ panel.
- If Apple changes the Find My protocol, `FindMy.py` (and therefore this app)
  can break without warning — keep an eye on its upstream repo.
