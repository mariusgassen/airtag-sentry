# AirTagSentry — Task Breakdown

Source: user's spec (`airtagsentryspec.md`) + amendments (Postgres, PWA push, Coolify).

## Backend core
- [x] Project scaffold (`pyproject.toml`, package layout, `.gitignore`)
- [x] Config loading (`config.yaml` + `.env` overlay, validation)
- [x] Postgres schema (`location_reports`, `alerts`, `push_subscriptions`)
- [x] Apple-ID login flow with `FindMy.py` (2FA handling, `AppleAccount` token persistence)
- [x] AirTag key material loading (`KeyPair.from_b64` or `FindMyAccessory.from_json`)
- [x] `tracker.poll_once()`: fetch_location_history → dedupe insert → movement check → notify
- [x] Haversine-based movement detection (distance threshold + stillstand-then-movement)
- [x] APScheduler-based periodic polling (15 min default)

## Notifications
- [x] ntfy.sh notifier
- [x] Telegram notifier
- [x] Web Push notifier (VAPID, `push_subscriptions` table, pruning on 410/404)

## Dashboard (Phase 2, PWA)
- [x] FastAPI app: `/api/reports`, `/api/status`, `/api/push/*`
- [x] Leaflet map + timeline table (`index.html`)
- [x] PWA manifest + icons + service worker (installable, offline shell, push display)
- [x] "Enable notifications" subscribe flow in the browser

## Packaging & deployment
- [x] Dockerfile
- [x] docker-compose.yml (postgres, anisette, app, dashboard)
- [x] `scripts/generate_vapid_keys.py`
- [x] README: local setup, login flow, Coolify deployment, PWA install, limitations

## Tests & verification
- [x] `test_movement.py` — 8 tests, all passing
- [x] `test_db.py` — against a real local Postgres, all passing
- [x] `test_notifiers.py` — mocked HTTP/webpush, all passing
- [x] `docker compose config` validation — parses cleanly
- [x] Dashboard smoke test via headless Chromium (manifest linked, service worker
      registers and activates, status/table populate from seeded Postgres data)
  - Leaflet map itself could not be visually confirmed in this sandbox: its CDN
    (jsdelivr) is blocked by this environment's outbound proxy policy
    (`ERR_TUNNEL_CONNECTION_FAILED`), not by the app. This will work in any
    normal browser with internet access, since the *browser*, not the server,
    fetches it.
- [ ] End-to-end Apple/AirTag flow — **cannot run in this sandbox** (needs a
      real Apple ID, live 2FA code, and an extracted AirTag key). Documented
      in the README for the user to run themselves.
- [ ] Live Web Push round-trip to a real browser push service, and the actual
      Coolify deployment — likewise need real infra outside this sandbox.

## Non-goals (v1, per spec)
- No multi-user support
- No native mobile app (PWA dashboard instead)
- ~~No multi-AirTag support~~ — added, see below.

## v2: multi-AirTag, dashboard login, key extraction docs
- [x] `config.yaml`: `airtag:` → `airtags:` list, each entry keyed by `id`,
      private key sourced from `AIRTAG_PRIVATE_KEY_B64_<ID>` when
      `accessory_json_path` isn't set; env-var-suffix collisions rejected
- [x] `db.py`: `airtag_id` column + composite `(airtag_id, timestamp)`
      uniqueness on `location_reports`, idempotent migration for existing
      deployments, `airtag_id` threaded through all report/alert queries
- [x] `tracker.py`: `poll_once` loops over all configured airtags under one
      Apple session, isolates per-tag failures
- [x] `web/app.py`: `/api/airtags`, `airtag_id` param on `/api/reports` +
      `/api/status`
- [x] `web/static/index.html`: airtag selector dropdown, fixed a real Leaflet
      "map already initialized" bug that the dropdown would have triggered
- [x] Dashboard auth: GitHub OAuth (`/login`, `/auth/callback`, `/logout`),
      session-cookie middleware protecting all routes including the mounted
      static app
- [x] README: GitHub OAuth App setup, `python -m findmy decrypt` key
      extraction steps (replacing the old "outside this app's scope" framing)
- [x] Tests updated for the new `airtag_id` field on `Report`/`Alert`; added a
      regression test for cross-tag timestamp uniqueness

## Review
- Breaking config change, no back-compat shim: existing single-tag
  `config.yaml`/`.env` files must be migrated to the new `airtags:`/
  `AIRTAG_PRIVATE_KEY_B64_<ID>` shape. Existing Postgres data migrates
  automatically (backfilled under `airtag_id = 'default'`) the next time
  `init_schema` runs.
- Dashboard login is now mandatory — `GITHUB_CLIENT_ID`/`_SECRET`,
  `GITHUB_ALLOWED_LOGIN`, `SESSION_SECRET_KEY` are required env vars for every
  CLI subcommand, not just `serve`, since they share `load_config()`.
- Not verified in this sandbox (no real Apple ID, GitHub OAuth App, live
  Postgres/browser, or a Mac): the GitHub OAuth round-trip, multi-tag
  dashboard switching in an actual browser, and `python -m findmy decrypt`
  itself. `pytest` (movement + notifiers) and a syntax/import check were run;
  see PR description for the full verification list.
