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

## v3: Coolify env exposure, fancier mobile UI, encrypted UI-managed keys
- [x] `docker-compose.yml`: explicit `environment:` blocks on `app`/`dashboard`
      (kept alongside `env_file: .env`) so Coolify's UI lists every var
- [x] AirTag keys moved out of `config.yaml`/`.env` entirely: `AirtagConfig`
      is now just `id`+`name`; keys are encrypted (Fernet,
      `AIRTAG_KEY_ENCRYPTION_KEY`) and stored in a new `airtag_keys` Postgres
      table, managed via `/api/airtags/{id}/key` (POST/DELETE)
- [x] `airtag_sentry/keystore.py`: small encrypt/decrypt module
- [x] `tracker.py`: `_load_key` now decrypts from the DB per poll instead of
      reading `accessory_json_path`/env vars
- [x] `web/static/index.html`: full rewrite — mobile-first responsive layout,
      stat cards, restyled map/table, and a new "AirTags verwalten" panel for
      uploading/pasting keys and removing them, with client-side validation
      before sending
- [x] README: config-first/encrypted-at-rest key storage section, updated
      key-extraction flow (upload via UI instead of `accessory_json_path`),
      post-upgrade callout for existing users

## Review (v3)
- Another breaking change, no back-compat shim: `accessory_json_path` and
  `AIRTAG_PRIVATE_KEY_B64_<ID>` are gone. Existing users must set
  `AIRTAG_KEY_ENCRYPTION_KEY` and re-enter each key once via the dashboard.
- The encryption master key is still an env var by necessity (a key can't
  protect data while living inside that same data store) — this is the one
  secret that couldn't move to "config first."
- Key validation happens server-side before storing (constructs a real
  `KeyPair`/`FindMyAccessory` from the submitted value) so a bad paste/upload
  is rejected immediately with a 400, not discovered at the next poll.
- Not verified in this sandbox (no browser available here): the dashboard's
  actual visual appearance and mobile responsiveness. Logic was verified via
  `pytest` against a real local Postgres and a `TestClient`-driven exercise of
  the new key-management endpoints (set via both b64 and JSON, confirm
  `has_key`, delete) — see PR description.

## v4: tracked schema migrations, Coolify single-domain/no-port-bind follow-up
- [x] Confirmed the dashboard's `ports:` mapping was already removed directly
      on `main` (user commit, merged with PR #2) — no `ports:` on any service
      now, so Coolify's proxy reaches `dashboard` over the internal network
      only; added `docker-compose.override.yml.example` for local host-port
      access without touching the Coolify-facing compose file
- [x] Confirmed "single domain": `SERVICE_FQDN_DASHBOARD_8000` is the only
      `SERVICE_FQDN_*` var in the stack — documented explicitly in
      `.env.example` and the Coolify section rather than leaving it implicit
- [x] Replaced the hand-rolled idempotent `SCHEMA` blob in `db.py` with real
      tracked migrations: `airtag_sentry/migrations.py` holds an ordered
      `(version, sql)` list (`0001_initial_schema`, `0002_multi_airtag`,
      `0003_airtag_keys` — the exact history so far, decomposed), applied by
      a new `run_migrations()` that records each version in a
      `schema_migrations` table so it only ever runs once; `init_schema` is
      gone, renamed everywhere it was called (`web/app.py`, `tracker.py`,
      `tests/test_db.py`)
- [x] Tests: `schema_migrations` is asserted to contain exactly the 3 expected
      versions after a fresh run, and re-running `run_migrations` is asserted
      idempotent (no re-inserts)

## v5: drop config.yaml, all app-behavior settings become env vars
- [x] Root cause of a Coolify deploy crash (`IsADirectoryError: config.yaml`):
      `config.yaml` was git-ignored and bind-mounted by `docker-compose.yml`;
      a fresh Coolify clone never had the file on disk, so Docker silently
      created an empty directory at that path instead of erroring, which
      then blew up `yaml.safe_load(path.read_text())` at startup
- [x] `config.py`: removed YAML parsing entirely; `apple`/`polling`/
      `movement`/`web` settings now read from env vars (`APPLE_STORE_PATH`,
      `ANISETTE_MODE`/`ANISETTE_LIBS_PATH`/`ANISETTE_REMOTE_URL`,
      `POLLING_INTERVAL_MINUTES`, `MOVEMENT_*`, `WEB_HOST`/`WEB_PORT`) with
      the same defaults `config.example.yaml` used to have; `load_config()`
      takes no path argument anymore
- [x] `cli.py`: dropped the now-meaningless `--config` flag
- [x] `docker-compose.yml`: removed both `./config.yaml:/app/config.yaml:ro`
      bind mounts; `app`/`dashboard` now get the new settings via their
      `environment:` blocks (only the ones safe to change under Docker -
      `POLLING_INTERVAL_MINUTES`/`MOVEMENT_*`; anisette mode is hardcoded to
      `remote` for the bundled container, and `APPLE_STORE_PATH`/
      `ANISETTE_LIBS_PATH`/`WEB_HOST`/`WEB_PORT` are left at their defaults
      since changing them would break the volume mount or Coolify's
      `SERVICE_FQDN_DASHBOARD_8000` routing)
- [x] Deleted `config.example.yaml`; removed its `COPY` from `Dockerfile`,
      its entries from `.gitignore`/`.dockerignore`, and the now-unused
      `pyyaml` dependency from `pyproject.toml`
- [x] `.env.example` and README updated so every setting the app reads is
      documented in one place instead of split across `.env`/`config.yaml`
- [x] `tests/test_config.py`: added coverage for `load_config()`'s
      apple/polling/movement/web env-var parsing (previously untested either
      way - the old YAML path had zero test coverage too)

## Review (v5)
- Another breaking change, no back-compat shim: anyone with an existing
  `config.yaml` needs to move its values into `.env` per the new table in
  the README. Postgres/GitHub/session/encryption-key requirements are
  unchanged.
- Verified: `pytest` (full suite, 20 passed/7 skipped - skips are the
  real-Postgres `test_db.py` cases, unrelated to this change) in a fresh
  venv; `load_config()` exercised directly with only the required env vars
  set, confirming defaults match the old YAML defaults exactly; `docker
  compose config` parses cleanly with no bind mount left pointing at
  `config.yaml` and no "variable not set" warnings for the new vars.

## Review (v4)
- This removes the "IF NOT EXISTS defensive guard" style of migration for
  anything new going forward — a migration only ever runs once per database,
  tracked by `schema_migrations`, so new migrations can write plain
  non-idempotent SQL. `0002_multi_airtag` keeps its `IF NOT EXISTS`/`DO $$`
  guards specifically because it's the one migration that might already have
  partially applied on a database that ran this project before
  `schema_migrations` existed (i.e. before this change) — that's a one-time
  transitional concern, not the new pattern going forward.
- Verified against a real local Postgres: a completely fresh database ends up
  with exactly the 3 expected `schema_migrations` rows; re-running
  `run_migrations()` is a no-op; `docker compose config` still parses with
  the override file's `services.dashboard.ports` merged in when present.
