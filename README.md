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

- **An AirTag key.** This app does not extract AirTag keys from Apple's
  Find My app — that's a separate, non-trivial step (typically exporting the
  keychain item for an officially-paired AirTag, e.g. via the
  `macless-haystack`/`plist_to_json` tooling that ships with `FindMy.py`, or
  using your own self-made tracker's key). You need either:
  - a base64-encoded private key (`AIRTAG_PRIVATE_KEY_B64` in `.env`), or
  - an exported `FindMyAccessory` JSON file (`airtag.accessory_json_path` in
    `config.yaml`).
- **Your own Apple ID**, with 2FA you can complete interactively once.
- Using this against an AirTag you don't own, or in a way that violates
  Apple's Terms of Service, is on you — this is for tracking your own
  property.

## Local setup

```bash
cp config.example.yaml config.yaml   # adjust thresholds, airtag name, key source
cp .env.example .env                 # fill in DATABASE_URL, notifier creds, etc.
python scripts/generate_vapid_keys.py   # paste the output into .env for Web Push
```

Edit `config.yaml`:
- Set `airtag.accessory_json_path` **or** leave it `null` and set
  `AIRTAG_PRIVATE_KEY_B64` in `.env` instead — exactly one is required.
- For Docker Compose, set `apple.anisette.mode: remote` and
  `apple.anisette.remote_url: http://anisette:6969` so polling uses the
  bundled anisette container instead of generating anisette data in-process.

```bash
docker compose up -d postgres anisette
docker compose run --rm app python -m airtag_sentry login   # interactive, needs your real 2FA code
docker compose up -d
```

The dashboard is then at `http://localhost:8000`.

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
2. Set the variables from `.env.example` in Coolify's environment tab (or
   commit your own non-secret defaults and let Coolify prompt for secrets).
3. Uncomment `SERVICE_FQDN_DASHBOARD_8000` in your env — Coolify auto-assigns
   a public domain + TLS to the `dashboard` service's port 8000.
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
- Single AirTag, single user, no mobile app beyond the installable PWA — all
  intentional per the original spec's non-goals.
- If Apple changes the Find My protocol, `FindMy.py` (and therefore this app)
  can break without warning — keep an eye on its upstream repo.
