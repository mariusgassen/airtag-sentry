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

## v6: polling interval / movement thresholds move from env vars to a UI setting
Trigger: "AirTag encryption key is not documented" (small doc gap - the
`AIRTAG_KEY_ENCRYPTION_KEY` section never says what happens if you lose or
rotate it) + "move polling interval, distance threshold etc to a setting in
the UI" (a real feature - v5 just moved these the *other* direction, into
env vars, for the Coolify config.yaml bug; the request now is DB + UI
instead, so the `app` scheduler process and the `dashboard` process both
need to see the same live value without a restart).

- [x] README: add the missing warning to the "AirTags: fully UI-managed,
      keys encrypted at rest" section - `AIRTAG_KEY_ENCRYPTION_KEY` must not
      be lost or changed once keys are stored; doing so makes every stored
      key undecryptable and each one has to be re-entered via the dashboard.
- [x] New Alembic migration (`0002_...`): single-row `settings` table
      (`id` constrained to one row via `CHECK`), columns
      `polling_interval_minutes`, `movement_distance_threshold_meters`,
      `movement_stillstand_hours`, `movement_stillstand_movement_meters`,
      `movement_alert_on_backfill`, seeded with today's defaults
      (15 / 100 / 24 / 15 / false) in the same migration.
- [x] `db.py`: `AppSettings` dataclass, `get_settings(conn)`,
      `update_settings(conn, ...)`.
- [x] `config.py`: drop `PollingConfig`/`MovementConfig` and their env
      parsing (`POLLING_INTERVAL_MINUTES`, `MOVEMENT_*`) entirely - another
      breaking change, no back-compat shim, consistent with v3/v5. Drop the
      now-dead `_env_float`/`_env_bool` helpers too.
- [x] `movement.py`: `MovementConfig` moves here (keeps this module's "no DB
      access" pure-function design intact); `tracker.py` builds one from
      `AppSettings` each `poll_once()` call instead of from `cfg`.
- [x] `scheduler.py`: swap the fixed APScheduler `interval` trigger for a
      self-rescheduling `date` trigger - after every poll, re-read
      `polling_interval_minutes` from the DB and schedule the next single
      run that far out (`replace_existing=True`). Makes an interval change
      take effect starting next poll, not on the next container restart.
- [x] `web/app.py`: `GET`/`PUT /api/settings` (validated Pydantic body,
      reuses the existing `AuthMiddleware` coverage of `/api/*`); `/api/status`
      reads `poll_interval_minutes` from DB settings instead of `cfg.polling`.
- [x] Frontend: `api.ts` (`AppSettings`, `getSettings`/`updateSettings`),
      a gear icon, a `SettingsPanel` component styled like
      `AirtagDetail`'s Section/Row forms, wired into `App.tsx`'s sidebar
      views next to the existing list/detail panels.
- [x] Strip `POLLING_INTERVAL_MINUTES`/`MOVEMENT_*` from `.env.example`,
      `docker-compose.yml` `environment:` blocks, the README "App behavior
      settings" table, and the `run` CLI help text; note where they live now.
- [x] Tests: `test_config.py` (drop the removed env vars), `test_movement.py`
      (import `MovementConfig` from `airtag_sentry.movement`), `test_db.py`
      (settings get/update round-trip, single-row invariant). Full `pytest`
      run against real Postgres; `docker compose config`; frontend
      `tsc`/`vite build`.

## Review (v6)
- Another breaking change, no back-compat shim (consistent with v3/v5):
  `POLLING_INTERVAL_MINUTES`/`MOVEMENT_*` env vars are gone; anyone with
  them set in `.env` just has them ignored now (harmless, not an error) —
  the DB-seeded defaults match the old env-var defaults exactly, so nothing
  changes behaviorally for an existing deployment on upgrade.
- The scheduler no longer uses APScheduler's `interval` trigger at all — it
  self-reschedules a `date` trigger after every poll, re-reading
  `polling_interval_minutes` from Postgres each time. A change made in the
  dashboard takes effect starting with the very next poll; there is no
  "still running on the old interval until restart" window.
- Verified against a real local Postgres (started for this session): full
  `pytest` (30 passed, 0 skipped — first time this suite has actually run
  against live Postgres rather than skipping the DB-backed tests), including
  new coverage for `get_settings`/`update_settings` round-tripping and the
  `CHECK (id = 1)` single-row constraint actually rejecting a second row.
  Also manually exercised `GET`/`PUT /api/settings` and `/api/status` through
  a `TestClient` with a hand-signed session cookie (real auth middleware,
  not bypassed): round-trips correctly, and `PUT` with
  `polling_interval_minutes: 0` correctly 422s. `docker compose config`
  parses cleanly with no `POLLING_INTERVAL_MINUTES`/`MOVEMENT_*` left in any
  `environment:` block. Frontend: `tsc -b && vite build` succeeds with no
  type errors.
- Not verified: the Settings panel's actual appearance/interaction in a
  real browser (no browser available in this sandbox) — logic was verified
  via the API round-trip above and by reading the component against the
  existing `AirtagDetail`/`AirtagList` styling it reuses (`Section`/`Row`).

## v7: UI polish (navigation, theming, icons, mobile sheet, input zoom)
Trigger: direct UI feedback against a screenshot of the real Find My app -
settings felt bolted onto the list instead of being real navigation, no way
to see more than half the list on mobile, dark-only, two hand-drawn icons
were subtly broken, and focusing a form field zoomed the whole page in.

- [x] `components/icons.tsx`: `GearIcon` replaced with a properly
      radially-symmetric path (the old one had ad-hoc tooth coordinates,
      visibly lopsided); `TrashIcon`'s lid was actually a bug, not just
      ad-hoc - its right corner's arc had the wrong sweep flag and bulged
      up above the lid line instead of mirroring the smooth left corner;
      rewrote the whole glyph as a verified rounded-rect-plus-lid path and
      added the two rib lines real trash-can icons have.
- [x] `theme.ts` (new) + `index.css`: dark stays the default, but the app
      now has a real light palette too, applied via `prefers-color-scheme`
      by default and overridable per-user via `data-theme="light"/"dark"`
      on `<html>` (`useTheme()` hook, persisted to `localStorage`). An
      inline script in `index.html` applies the stored override before
      first paint so there's no flash of the wrong theme. `theme-color`
      meta tag kept in sync so the PWA/browser chrome matches.
- [x] `components/TabBar.tsx` (new): real persistent bottom tab bar
      (Objekte / Einstellungen) replacing the old pattern where a gear icon
      pushed a full-screen Settings view over the list with no visual
      indication it was "open" - `App.tsx` now tracks `activeTab`
      independently of the Objekte tab's own list/detail navigation, so
      switching tabs and back preserves whichever screen was open, like a
      real per-tab nav stack.
- [x] `App.tsx`: mobile sheet can now expand near-fullscreen via its grab
      handle (a real toggle button, not a gesture - deliberately simpler
      than tracking a drag, and keeps working for keyboard/switch-control
      users), matching Find My's fullscreen-the-list-sheet behavior. The
      tab bar is grouped with the sheet in one bottom-pinned column so it
      never moves regardless of the sheet's height; `--tabbar-h` in
      `index.css` is shared between the two so the expanded-sheet height
      calc doesn't need to measure the tab bar at runtime.
- [x] `index.css`: `input`/`select`/`textarea` forced to a 16px minimum
      font-size below the `md` breakpoint - the actual root cause of the
      "typing in a field zooms the page" complaint (iOS/Android auto-zoom
      any focused control computed under 16px; Tailwind's `text-sm` is
      14px). No viewport `maximum-scale` lock added, since that would trade
      the bug for taking away pinch-zoom entirely.
- [x] `AirtagList.tsx`/`SettingsPanel.tsx`: dropped the gear button and the
      Settings panel's back-to-AirTags button now that Settings is a
      persistent tab, not a pushed view; added an "Erscheinungsbild"
      (System/Hell/Dunkel) row to Settings using the existing segmented-
      control pattern from the key-upload form.

- [x] Fixed a real bug surfaced after the above: the PWA app icon was
      missing on the home screen. Root cause was `AuthMiddleware`
      (`web/app.py`) gating *every* path behind a login session except
      `/login`/`/auth/callback`/`/logout` - including
      `/manifest.webmanifest`, `/icons/*`, and the service worker scripts.
      The browser's "Add to Home Screen"/install-eligibility checks and
      background service-worker update fetches request those outside the
      page's own authenticated fetch context, so they got a 302 redirect to
      the login HTML instead of the actual PNG/JSON/JS - which is what a
      missing/broken install icon looks like. Added `_is_public()` so those
      specific paths (not sensitive - no user data, just install plumbing)
      are servable without a session; `/`, `/assets/*`, and all `/api/*`
      routes are unaffected and still require login.

## v8: UI/UX polish (login page, favicon, auto-save settings, logout placement, map fallback, native chrome)
Trigger: direct UI/UX feedback list - login page is a bare link, favicon/PWA
icon isn't wired up correctly, settings needed a Save button instead of
auto-saving, logout was in the AirTags tab instead of Settings, the map was
blank for a brand-new AirTag, and the overall app still read as a styled web
page rather than a native iOS app (including a sheet grab-handle that only
supported tap, not the drag it visually implies).

- [x] `web/app.py::login_page`: full redesign - theme-aware (reads the same
      `localStorage` key as `index.html`'s early-theme script, falls back to
      `prefers-color-scheme`), glass card, app glyph, matches the dashboard's
      actual palette instead of hardcoded `#0d1117`/`#238636`.
- [x] `vite.config.ts`: fix stale PWA manifest `background_color`/
      `theme_color` (`#0d1117`/`#1f6feb`) to match the real palette
      (`#000000`/`#0a84ff`).
- [x] `scripts/generate_icons.py` + `frontend/public/favicon.ico` (new,
      generated): multi-size favicon from the same glyph; `index.html` links
      it plus a sized PNG variant; `web/app.py`: `/favicon.ico` added to
      `_PUBLIC_PATHS` (same non-sensitive class as the existing manifest/icon
      exemptions) so it isn't 302'd behind login.
- [x] `AirtagList.tsx`: drop the bottom logout link. `SettingsPanel.tsx`: add
      it at the bottom as a destructive `Row` (reusing `AirtagDetail.tsx`'s
      `Row`/`Section`).
- [x] `SettingsPanel.tsx`: auto-save - numeric fields debounce-PUT ~600ms
      after the last keystroke (inline validation hint instead of blocking
      `alert()`), checkbox/theme PUT immediately; Save button removed,
      replaced by a small transient "Speichert…/Gespeichert" label.
- [x] `MapCard.tsx`: no-reports-yet state now tries
      `navigator.geolocation.getCurrentPosition` and renders a pulsing
      "Aktueller Standort" dot marker centered there; unchanged text
      fallback if geolocation is denied/unsupported.
- [x] Native-chrome polish (focused scope, not a nav rewrite): translucent
      `backdrop-filter` blur on the tab bar and sheet handle bar; real
      pointer-drag-to-resize on the sheet's grab handle with snap-on-release
      (tap-to-toggle kept as a fallback via a drag-distance threshold),
      fixing the reported non-functional handle; minor spacing/typography
      pass on settings rows/section headers toward iOS grouped-table
      conventions.

## Review (v8)
- Found and fixed a real bug introduced while implementing auto-save: the
  first version of `SettingsPanel.tsx`'s `update()` put side effects (the
  debounce timer, calling `persist()`) inside a `setSettings` *functional*
  updater. React StrictMode (enabled in `main.tsx`) deliberately
  double-invokes functional updaters in dev to catch exactly this, which
  fired two identical `PUT /api/settings` calls per checkbox click - caught
  by the Playwright verification below, not by `tsc`/`oxlint`. Fixed by
  deriving `next` from the `settings` closure directly and running the
  side effects once, outside the updater - the correct pattern, not a
  workaround.
- The sheet's grab handle previously only supported tap
  (`setSheetExpanded` toggle) despite looking like a drag handle - the
  reported "handle does not work" bug. Real pointer-drag is now driven by a
  `--drag-delta` CSS custom property set on the sheet element during
  `pointermove` (see the `[data-dragging="true"]` rules in `index.css`),
  resolved to a collapsed/expanded snap on `pointerup` via a
  drag-distance threshold; a genuine `click` (no preceding `pointerup`,
  i.e. keyboard/switch-control activation) still toggles directly. A
  `dragHandledClick` ref swallows the synthetic click that follows a real
  pointer interaction so it doesn't double-toggle.
- `_is_public()`/`_PUBLIC_PATHS` (`web/app.py`) gained `/favicon.ico` for
  the same reason the v7 fix added the manifest/icons/service-worker
  exemptions: browsers request it directly, outside any authenticated
  fetch context, independent of the page's `<link rel="icon">`.
- Scope for "reinvent the layout as a native Apple app" was deliberately
  narrowed to focused polish (translucency, real drag, spacing) rather than
  a navigation rework, per explicit user choice when the plan was
  presented - no collapsing large-title header, no iPad/desktop split-view,
  no change to the tab-based navigation model.
- Verified: `cd frontend && npm run build` (`tsc -b && vite build`) and
  `npm run lint` (oxlint - only the two pre-existing `set-state-in-effect`
  warnings from v7 remain, no new ones). Backend: full `pytest` (28
  passed / 10 skipped - same real-Postgres skips as always; added
  `test_favicon_is_servable_without_a_session` to `test_web_auth.py`,
  covering the new `_PUBLIC_PATHS` entry). Rendered the actual
  `login_page()` HTML via a `TestClient` (no mocking of that route) and
  screenshotted it with headless Chromium in both light and dark - glass
  card, gradient backdrop, and GitHub icon all render correctly, themed
  from the stored `localStorage` preference exactly like the rest of the
  app. Ran the real app via `vite dev` with the backend's API routes
  mocked at the network layer (Playwright `page.route`, not a stub
  component) and drove the actual UI end-to-end: confirmed no Save button
  and no `alert()` remain in Settings; a numeric field's PUT fires once
  ~600ms after the last keystroke with the typed value; an invalid value
  (`0`) blocks the PUT and shows the inline German error text; the
  checkbox PUTs immediately (and, after the StrictMode fix above, exactly
  once); the logout row appears in Settings and not in the AirTags list;
  a synthetic pointer-drag on the handle grows the sheet's live height and
  snaps it to `data-expanded="true"` on release, and a plain click after
  that collapses it again; the current-location dot marker renders when
  `getCurrentPosition` (mocked via Playwright's geolocation context option)
  resolves and `reports` is empty; the tab bar's computed
  `backdrop-filter` is non-`none`. Also screenshotted the mobile app at
  both themes and a 1400×900 desktop viewport for a visual pass.
- Not verified: real iOS/Android Safari for the drag gesture's feel and the
  translucency's actual look over live map tiles - this sandbox's outbound
  proxy blocks the OpenStreetMap tile CDN (`ERR_TUNNEL_CONNECTION_FAILED`,
  same known limitation noted in earlier reviews), so the map itself
  renders blank/grey in every screenshot here; the blur/marker/drag
  mechanics were still verified directly against the real DOM and CSS, not
  a stand-in. The actual GitHub OAuth round-trip from the new login page
  was not re-tested (unchanged since v2/v7 - only the HTML around the
  existing `authorize_url` link changed).

## Review (v7)
- One backend change (see the app-icon fix above), otherwise UI-only; no
  breaking changes for existing deployments.
- Verified: `tsc -b && vite build` and `oxlint` (only pre-existing,
  untouched-by-this-change warnings remain - two `set-state-in-effect`
  notices on the original data-loading effects). Ran the actual app via
  `vite dev` + a headless Chromium (Playwright, not a project dependency -
  installed with `--no-save` for this check and removed again after) at
  both a mobile (390×844) and desktop (1400×900) viewport: confirmed no
  console/page errors beyond the expected `502`s from this sandbox having
  no backend running; measured the sheet's collapsed/expanded heights
  (438.875px / 751px at 844px viewport, matching the `52vh` /
  `calc(100vh - tabbar-h - 44px)` rules exactly) and confirmed the tab bar's
  bottom edge stays flush with the window bottom in both states; forced
  each theme via the new toggle and read `getComputedStyle` back
  (`rgb(242,242,247)` light, `rgb(0,0,0)` dark); confirmed the add-AirTag
  input computes to exactly `16px` on the mobile viewport; confirmed the
  gear button no longer renders in the AirTags list header.
- Not verified: real iOS/Android Safari (auto-zoom-on-focus and the PWA
  status bar are browser behaviors a headless desktop Chromium can't
  reproduce) - the font-size fix is the documented, standard root cause and
  fix for that behavior, but hasn't been confirmed against real hardware.
- App-icon fix verified with a `TestClient` hitting the real `create_app()`
  unauthenticated: `/manifest.webmanifest`, all three `/icons/*.png`,
  `/registerSW.js`, and `/sw.js` now 200; `/`, `/assets/*`, and `/api/*`
  still redirect to `/login` (302) or 401 exactly as before. Full `pytest`
  (20 passed / 10 skipped - same DB-backed skips as always, no regression).

## v8: Coolify health check
Trigger: "A health check is missing so coolify does not know the state" -
neither `docker-compose.yml` service had a `healthcheck:`, so Coolify could
only infer state from "is the container process running", not from whether
the dashboard was actually serving.

- [x] `web/app.py`: new `GET /health` route - round-trips to Postgres
      (`SELECT 1`) and returns `{"status": "ok"}`/200, or 503 with the error
      detail if the DB is unreachable. Added to `_PUBLIC_PATHS` (same reason
      as the PWA install paths already there: the prober - Docker's
      healthcheck this time, not a browser - has no session cookie to send).
- [x] `docker-compose.yml`: `healthcheck:` on the `dashboard` service, probed
      with `python -c "...urlopen(...)"` since the `python:3.14-slim` base
      image has no curl/wget. Added a comment on `app` explaining why it
      deliberately has none: it's the scheduler loop with no HTTP surface to
      probe, so Coolify/Docker's own container-running state (already what
      `restart: unless-stopped` acts on) is its health signal.
- [x] `tests/test_web_auth.py`: `/health` reachable without a session (DB
      round-trip stubbed via `monkeypatch`, consistent with this file's
      already-fake Postgres creds in the `cfg` fixture) and returns 503 when
      pointed at a genuinely unreachable database.
- [x] README: documented the new endpoint/healthcheck and the `app`/
      `dashboard` split in the Coolify deployment section.

## Review (v8)
- Small, additive change - one new route, one new `_PUBLIC_PATHS` entry, one
  compose `healthcheck:` block. No breaking changes, no schema/env changes.
- Verified against a real local Postgres (started for this session):
  `.venv/bin/python -m pytest` - 39 passed. Also stopped Postgres and
  re-ran - 29 passed / 10 skipped, same pre-existing DB-backed skip pattern,
  no new failures.
- Verified the actual production code path end-to-end, not just the test
  double: ran `python -m airtag_sentry serve` against real Postgres and hit
  it with the literal `python -c "import urllib.request as u; u.urlopen(...)"`
  command that's now in the compose `healthcheck:`, confirming it returns
  200 against a live server. Separately drove `create_app()` through
  `TestClient` with a bad `database_url` and confirmed a 503.
- `docker compose config` (Compose v5.1.1) parses the updated file cleanly
  with a dummy `.env` (not committed - `.env` is gitignored); the rendered
  `healthcheck:` block matches what was hand-verified above.
- Not verified: an actual Coolify deployment showing the healthy/unhealthy
  badge (no Coolify instance in this sandbox) and `docker build`/a full
  container run (no Docker daemon available here) - the healthcheck command
  itself was verified directly against `uvicorn`, which is what runs inside
  the container either way.

## v9: Consistent safe-area glass + full-screen map
Trigger: "Can we use the same glass/background in all the safe areas but
just not put controls there? It looks cut off otherwise" - the bottom safe
area (home indicator) already gets the app's translucent `chrome-blur`
material via `TabBar`/the sheet handle, but the top safe area (status
bar/notch) got nothing - the full-bleed map bled raw right up under it.
Also clarified an earlier ambiguous "minimize the panel" ask: it means a way
to collapse the bottom sheet down to just its handle so the map becomes
genuinely full-screen, for both the all-AirTags overview map and a single
AirTag's detail/history + route map (both already render through the same
shared sheet/map-pane pair in `App.tsx`).

- [x] `App.tsx`: added a decorative, `pointer-events-none`, `aria-hidden`
      glass bar (`h-[env(safe-area-inset-top)]`, reuses the existing
      `.chrome-blur` class, `md:hidden`) sitting over the top safe area -
      pure background, no controls, never intercepts map taps. No change
      needed to `.leaflet-top`'s existing `env(safe-area-inset-top)` offset,
      which already clears it.
- [x] `App.tsx` / `index.css`: replaced the boolean `sheetExpanded` with a
      3-value `SheetState` (`'minimized' | 'default' | 'expanded'`) plus a
      pure `resolveNextSheetState(start, delta)` transition function. Tap
      always resolves to one deterministic step (`default → expanded`,
      anything else `→ default`); a drag past the existing
      `SNAP_THRESHOLD_PX` moves exactly one level - `expanded` and
      `minimized` are never reached directly from each other, only through
      `default`. New `.sheet[data-state="minimized"]` CSS shrinks the sheet
      to a `--sheet-handle-h: 40px` strip (with `min-height: 0` to override
      the base rule's `280px` floor), leaving the map full-screen behind it;
      matching `[data-dragging="true"]` variant added for the live preview.
      `aria-expanded`/`aria-label` updated for the third state (new German
      label: "Ansicht einblenden"). No changes needed in `AirtagDetail.tsx`,
      `MapCard.tsx`, `OverviewMap.tsx`, `AirtagList.tsx`, or `TabBar.tsx` -
      minimizing clips the shared sheet body via its pre-existing
      `overflow-hidden` + `min-h-0 flex-1` wrapper.

## Review (v9)
- Two files touched (`App.tsx`, `index.css`), no new dependencies, no
  backend/schema changes.
- Verified: `npx tsc -b && npx vite build` clean; `npx oxlint` shows only
  the two pre-existing `set-state-in-effect` warnings on the untouched
  data-loading effects (same as every prior review).
- Drove the real app via `vite dev` + headless Chromium (Playwright,
  `--no-save`, removed after) at a mobile viewport (390×844), using Chrome
  DevTools Protocol's `Emulation.setSafeAreaInsetsOverride` to simulate a
  real notch/home-indicator device (`env(safe-area-inset-top)` confirmed to
  resolve to the overridden `47px`, not `0`, so this wasn't testing a no-op).
  Confirmed: the new top bar's computed height exactly matches
  `env(safe-area-inset-top)` with a non-`none` `backdrop-filter` and
  `pointer-events: none`; every transition in the design's table fires
  exactly as specified via simulated tap and drag (`default↔expanded` by
  tap; `default→minimized`, `minimized→default`, `default→expanded`,
  `expanded→default` by drag, with no direct `expanded↔minimized` jump
  reachable by either gesture); `aria-expanded`/`aria-label` correct in all
  three states; minimized sheet height is exactly `40px`. Screenshotted
  default and minimized states - minimized shows the map filling the screen
  down to a thin handle strip above the tab bar, for both the AirTags list
  (`showDetail=false`) view used in this check. Also checked a desktop
  viewport (1400×900): both the new top bar and the grab handle compute to
  `display: none` there, confirming the change is a no-op on the sidebar
  layout.
- Not verified: the single-AirTag detail/history map in the minimized state
  specifically (only the overview/list flow was screenshotted, since both
  share the identical sheet mechanism and no per-view code changed - the
  logic covering both was confirmed by reading `App.tsx`, not by driving an
  actual AirTag through the UI, since this sandbox has no backend running to
  create one against); real iOS/Android Safari rendering of the glass
  bar/notch interplay (CDP's safe-area override is a DevTools emulation, not
  the genuine WebKit safe-area-inset resolution path); map tiles (this
  sandbox's proxy still blocks the OpenStreetMap tile CDN, a pre-existing,
  previously-noted limitation - screenshots show grey/blank map).

## v10: Bottom safe-area dead space in the installed PWA
Trigger: real-device screenshot from the installed PWA after v9 shipped -
"the nav bar and icons seem to have the perfect size now but there is still
a dead space below in the PWA that should have the same glass effect." The
tab bar itself now looked right, but on the real device a strip of raw,
un-glassed map was visible below it, down to the true screen edge.

Root cause: the sheet+tab-bar column was `absolute inset-x-0 bottom-0` with
otherwise-intrinsic height (sized by its own content, not pinned to the
parent on all four sides) - unlike the map pane right above it in the JSX,
which is `absolute inset-0` and therefore always exactly matches the fixed
root regardless of any viewport-height quirk. `App.tsx`'s own root-level
comment already documents this exact class of bug once before (`fixed
inset-0` over `h-[100dvh]` on the *root*, because "100dvh has not reliably
spanned the true edge-to-edge screen across WebKit versions" on an installed
PWA) - the column one level down had the same intrinsic-height exposure the
root fix didn't cover, and on this device it fell short of the true bottom
edge, exposing raw map below the (correctly-sized) tab bar with no glass.

- [x] `App.tsx`: changed the sheet+tab-bar column from
      `absolute inset-x-0 bottom-0 ... flex flex-col` to
      `absolute inset-0 ... flex flex-col justify-end`, i.e. pinned to the
      fixed root on all four sides exactly like the map pane, with the
      sheet+tab-bar pushed to the bottom via `justify-end` instead of via
      the column's own intrinsic height + `bottom-0`. This makes the tab
      bar's bottom edge mathematically equal to the true viewport bottom -
      not just usually equal to it. The column is `pointer-events-none`
      (it now also covers the transparent area above the sheet, where taps
      must still reach the map underneath) with `pointer-events-auto`
      restored on the two real children (`.sheet` and `TabBar`'s `<nav>`,
      in `TabBar.tsx`) and on the whole column again at `md:` (desktop has
      no transparent gap to pass through - the sidebar is opaque top to
      bottom).
- [x] `TabBar.tsx`: added `pointer-events-auto` to the `<nav>` so it stays
      clickable under the now-pointer-events-none column.

## Review (v10)
- Two files touched (`App.tsx`, `TabBar.tsx`), no CSS/dependency changes,
  no backend changes.
- Verified: `npx tsc -b && npx vite build` clean; `npx oxlint` shows only
  the two pre-existing `set-state-in-effect` warnings (unchanged).
- Drove the real app via `vite dev` + headless Chromium (Playwright,
  `--no-save`, removed after), CDP `Emulation.setSafeAreaInsetsOverride`
  (top 47/bottom 34) at 390×844:
  - Measured the column's `getBoundingClientRect()`: exactly `{x:0, y:0,
    width:390, height:844}`, i.e. pixel-identical to `window.innerHeight` -
    proving the fix is mathematically guaranteed, not just visually
    plausible in this one test. The tab bar's own rect bottom is exactly
    `844` (= viewport height, zero gap) and the sheet's rect bottom exactly
    equals the tab bar's top (contiguous, no gap between them either).
  - Regression-checked every interaction the restructuring could plausibly
    break: `elementFromPoint` in the transparent area above the sheet (both
    at `default` sheet height and after minimizing, where that transparent
    area is much larger) resolves to the map's own div, not the now
    full-screen column - confirming clicks still pass through to Leaflet
    instead of being swallowed by the enlarged column box. Tab bar buttons
    still switch tabs (`Objekte`↔`Einstellungen`, content changes both
    ways). The handle drag-to-minimize gesture from v9 still resolves to
    `data-state="minimized"` correctly.
  - Desktop (1400×900): column computes to `position: static`,
    `pointer-events: auto`, `height: 900px` (i.e. `md:pointer-events-auto`
    correctly overrides the mobile default) and the settings tab is still
    clickable - confirming zero behavior change on the sidebar layout.
  - Screenshotted the mobile default state: the tab bar row sits flush
    against the screenshot's bottom edge with no visible gap beneath it.
- Not verified: the actual real device that reported the bug (this sandbox
  cannot reproduce genuine WebKit/Android viewport-height computation
  quirks - CDP's safe-area override emulates the *value* of
  `env(safe-area-inset-bottom)`, not the specific rendering discrepancy
  between an intrinsic-height `bottom-0` box and an `inset-0` box that this
  fix targets). The fix is structurally guaranteed correct by construction
  (an `inset-0` box cannot end up shorter than its containing block,
  regardless of viewport quirks) rather than confirmed to match the
  original bug 1:1, since the original couldn't be reproduced here to
  compare against directly.

## v11: "moved without you" alert correlation
Trigger: asked to refine/extend the roadmap and implement the next feature.
Compared against Traccar (geofences, trip/stop reports, per-device
notification rules) and researched the specific gap the user cared about:
movement alerts only look at an AirTag's own history, not whether it moved
*while the owner wasn't with it* - the actual signal that distinguishes
theft from normal use. `FindMy.py`'s AirTag protocol (offline-finding/
crowd-sourced) mostly only reports a device that's off or dead, so a live
phone's location needs a different source - see `tasks/roadmap.md` (new
file, item 1) for the full writeup and the rest of the backlog this session
also produced.

- [x] New dependency `pyicloud`: a second, independent Apple session (own
      login, own 2FA, own persisted cookie-based session) purely to fetch
      the owner's own device location via Apple's classic Find My iPhone
      web service (`fmipservice` - the one behind icloud.com/find), a
      different protocol than the AirTag search-party lookups. Entirely
      optional - unset `APPLE_OWNER_ID`/`APPLE_OWNER_PASSWORD` and nothing
      about existing behavior changes.
- [x] `airtag_sentry/owner_tracking.py` (new): `interactive_owner_login()`
      (CLI-invoked, handles 2FA + `trust_session()`) and
      `fetch_owner_location()`, mirroring `auth.py`'s shape.
- [x] `config.py`: `OwnerTrackingConfig`/`AppleConfig.owner`, read from
      `APPLE_OWNER_ID`/`APPLE_OWNER_PASSWORD`/`APPLE_OWNER_SESSION_PATH`
      (same "present together or disabled" pattern as Telegram's two vars).
- [x] New Alembic migration: `owner_locations` (append-only history table,
      no dedup needed) + two new `settings` columns
      (`movement_away_distance_meters` default 150,
      `owner_location_max_age_minutes` default 60).
- [x] `db.py`: `OwnerLocation` dataclass, `record_owner_location`/
      `latest_owner_location`; `AppSettings`/`_SETTINGS_COLUMNS`/
      `update_settings` extended for the two new columns.
- [x] `movement.py`: `MovementConfig` gains the two new fields; new pure
      `evaluate_away()` - only meaningful once a real movement alert has
      already fired, returns the distance-from-owner if it's stale-free and
      over threshold, else `None`. Same "no DB access" discipline as the
      rest of the module.
- [x] `tracker.py`: `_update_owner_location()` runs once per `poll_once()`
      (best-effort, never allowed to break AirTag polling - wrapped in
      try/except); after an existing movement alert fires, `evaluate_away()`
      runs and - if it returns a distance - records and notifies a *third,
      additional* `moved_without_owner` alert, never replacing the other two.
- [x] `cli.py`: new `login-owner` subcommand, parallel to `login`.
- [x] `web/app.py`: `SettingsIn` gains the two new fields;
      new `GET /api/owner-location` (null if unconfigured/no reading yet).
- [x] Frontend: `api.ts` (`AppSettings` fields, `getOwnerLocation`),
      `SettingsPanel.tsx` (new "Standort-Korrelation" section, same
      `Field`/`validate()` pattern as the existing movement settings),
      `format.ts` (`ALERT_REASON_LABELS`/`formatAlertReason` - also fixes
      `AirtagDetail.tsx` previously printing the raw `distance_threshold`/
      `stillstand_movement` enum string verbatim, now that a third one
      would have made that worse).
- [x] README: new "Owner device tracking (optional)" section (what it does,
      the `pyicloud`/fmipservice explanation, app-specific-password
      recommendation, the `login-owner` step), Movement detection section
      updated for the third alert type, Known Limitations updated.
      `.env.example`/`docker-compose.yml` updated - the two secrets are
      declared on both `app`/`dashboard` `environment:` blocks, matching
      the existing pattern of every other secret in this file being listed
      on both regardless of which service functionally needs it.
- [x] `tests/test_movement.py`: `evaluate_away` cases (no owner location,
      fresh+far, fresh+near, stale+far). `tests/test_db.py`:
      `record_owner_location`/`latest_owner_location` round-trip, settings
      tests extended for the two new columns.

## Review (v11)
- Additive, opt-in feature - unset `APPLE_OWNER_ID`/`APPLE_OWNER_PASSWORD`
  and behavior is unchanged from v10. The one breaking-adjacent change is
  the two new required `SettingsIn`/`AppSettings` fields (existing
  deployments get them via migration-seeded defaults, matching the pattern
  every previous settings-column addition in this project has used).
- No new automated test coverage was added for `/api/settings` or the new
  `/api/owner-location` route specifically - this repo has never had
  endpoint-level tests for any authenticated `/api/*` route (only `/health`,
  whose DB call is stubbed); building that scaffolding just for this
  feature would be new infrastructure the rest of the suite doesn't use.
  Instead, matching how v6's settings endpoints were verified: manually
  exercised via a real `TestClient` driven through the actual GitHub OAuth
  login flow (not a hand-crafted session cookie) against real Postgres -
  `GET /api/owner-location` round-trips a seeded row and returns `null`
  when empty; `GET`/`PUT /api/settings` round-trip the two new fields;
  `PUT` with `movement_away_distance_meters: 0` correctly 422s.
- Verified: full `pytest` (51 passed) against a real local Postgres
  (started for this session) - confirms the migration applies cleanly, the
  `owner_locations` table and new `settings` columns exist with the right
  seeded defaults, and `evaluate_away`'s four cases (no owner location,
  fresh+far, fresh+near, stale+far) behave as designed. `docker compose
  config` (with a dummy, uncommitted `.env`) parses cleanly and confirms
  `APPLE_OWNER_ID`/`APPLE_OWNER_PASSWORD` are present in both `app`'s and
  `dashboard`'s rendered `environment:` blocks. Frontend:
  `tsc -b && vite build` clean; `oxlint` shows only the two pre-existing
  `set-state-in-effect` warnings, no new ones.
- Not verified in this sandbox (no real Apple ID/2FA device, no live
  fmipservice access): the actual `pyicloud` login/2FA flow end-to-end, a
  real Find My iPhone location round-trip, and whether `trust_session()`'s
  ~2-month session lifetime holds up in practice - same category of
  "not verified here" as the existing AirTag Apple login flow already is.
  This is a reverse-engineered, unofficial Apple API; if it breaks, it
  breaks the owner-tracking feature only - AirTag tracking is on a
  completely separate Apple session/library and is unaffected either way.

## v12: move Apple login (AirTag + owner tracking) into the dashboard UI
Trigger: "Why do I need to do the login from the CLI, I want to do this from
the UI. Everything should be done from the UI if possible" - `login`/
`login-owner` were the one remaining CLI-only setup step, added in v11 by
mirroring an existing pattern without questioning it (see
`tasks/lessons.md`). New `CLAUDE.md` now states this as a hard constraint.
Implementing it surfaced a real design fix, not just a UI wrapper: unlike
`FindMy.py`'s `AppleAccount` (which persists a resumable session without
the password via `to_json()`/`from_json()`), `pyicloud` has no
"resume-from-token-alone" mode - the owner-tracking password must stay
available to every poll indefinitely, so storing it in plaintext `.env`
(what v11 shipped) was the wrong call. Fixed here by giving it the same
treatment AirTag keys already got in v3: encrypted in Postgres, entered via
the dashboard.

- [x] `airtag_sentry/auth.py`: `interactive_login()` replaced with a
      stateful wizard - `start_login(cfg, email, password)` (persists
      immediately if no 2FA, else returns available 2FA methods),
      `request_2fa_code(method_index)`, `submit_2fa_code(cfg, code)`,
      `is_connected(cfg)`, `disconnect(cfg)`. The in-progress `AppleAccount`
      is held in a module-level variable between requests - single-user app,
      one login attempt at a time, no session-store needed.
      `restore_account()` (used by `tracker.py`) is unchanged.
- [x] `airtag_sentry/owner_tracking.py`: `interactive_owner_login()`
      replaced the same way - `start_owner_login(cfg, conn, apple_id,
      password)`, `submit_owner_2fa_code(cfg, conn, code)`, `is_connected(conn)`,
      `disconnect(conn)`. Successful login now encrypts the password
      (`keystore.encrypt`, same as AirTag keys) and stores it in a new
      `owner_apple_credentials` table instead of `.env`.
      `fetch_owner_location(cfg, conn)` (gained `conn`) reads+decrypts from
      there each poll instead of `cfg.apple.owner`.
- [x] New Alembic migration: `owner_apple_credentials` table (single row,
      same shape as `airtag_keys` - row absence = "not connected").
- [x] `config.py`: `OwnerTrackingConfig`/`AppleConfig.owner` removed
      entirely along with the `APPLE_OWNER_ID`/`APPLE_OWNER_PASSWORD` env
      reads - another breaking change, no back-compat shim, consistent with
      this project's established pattern (and low-cost: owner tracking only
      shipped last PR, unlikely to be configured anywhere real yet).
      `AppleConfig.owner_session_dir` (env `APPLE_OWNER_SESSION_PATH`)
      replaces it as a plain infra path, same treatment as
      `APPLE_STORE_PATH`.
- [x] `tracker.py`: `_update_owner_location` simplified - no more
      `cfg.apple.owner is None` guard, since `fetch_owner_location` now
      checks the DB itself.
- [x] `cli.py`: `login`/`login-owner` subcommands removed entirely (not
      deprecated-but-kept) - only `poll`/`run`/`serve` remain, which are
      container entrypoints, not user setup steps.
- [x] `web/app.py`: new `/api/apple/status`, `/api/apple/login`,
      `/api/apple/2fa/select`, `/api/apple/2fa/submit`, `DELETE /api/apple`,
      and the owner-tracking equivalents under `/api/apple/owner/*` - all
      behind the existing `AuthMiddleware` like every other `/api/*` route.
- [x] Frontend: `AppleConnectPanel.tsx` (new) - a small reusable wizard
      (credentials → optional 2FA-method-select → code → connected),
      parameterized by an adapter so the same component drives both
      sessions (owner tracking's pyicloud login never offers a method
      choice, AirTag's `FindMy.py` login sometimes does). Wired into
      `SettingsPanel.tsx` as a new "Apple-Konten" section.
- [x] `docker-compose.yml`: removed `APPLE_OWNER_ID`/`APPLE_OWNER_PASSWORD`
      from both services. Also fixed a real bug this change would otherwise
      have caused: the `dashboard` service's `app_data` volume was mounted
      `:ro` (fine when only the `app` service's CLI ever wrote
      `account.json`/the pyicloud session cache) - now that login runs as a
      dashboard HTTP action, `dashboard` needs read-write access too.
- [x] README/`.env.example`/`CLAUDE.md` updated throughout to describe the
      UI flow instead of the CLI steps; roadmap item 10 marked done.
- [x] Tests: `test_db.py` round-trip for the new credentials table;
      `test_auth.py`/`test_owner_tracking.py` (new) cover the pending-login
      guard clauses and `auth.py`'s file-based `is_connected`/`disconnect`
      - real Apple network calls aren't exercisable here, consistent with
      this project's existing precedent for Apple-login-flow coverage.

## Review (v12)
- Breaking change: `APPLE_OWNER_ID`/`APPLE_OWNER_PASSWORD` are gone: anyone
  who somehow already set them (unlikely - v11 merged one PR ago) needs to
  reconnect via Settings instead. The AirTag-tracking session's env var
  (`APPLE_STORE_PATH`) is unchanged in shape, just no longer written by a
  CLI command.
- Verified: full `pytest` (57 passed) against a real local Postgres,
  including the new migration applying cleanly with the expected columns.
  Manually drove every new route through a real `TestClient` (actual GitHub
  OAuth login flow, not a stubbed cookie) with `auth.start_login`/
  `auth.request_2fa_code`/`auth.submit_2fa_code`/`auth.disconnect` and the
  owner-tracking equivalents monkeypatched at the call site (real Apple
  servers aren't reachable from here): confirmed the full wizard sequence
  for both sessions (status → login → 2FA select → 2FA submit → status
  flips to connected → disconnect → status flips back), that the stored
  owner password is encrypted (not plaintext) in Postgres, and that a
  failure surfaces as a 400 with a readable message. `docker compose
  config` (dummy, uncommitted `.env`, no `APPLE_OWNER_*` vars at all now)
  parses cleanly and confirms the `dashboard` service's `app_data` volume
  is read-write (the `:ro` bug described above). Frontend:
  `tsc -b && vite build` clean; `oxlint` shows only the two pre-existing
  warnings - the new effect's `exhaustive-deps` warning was fixed properly
  (adding the actually-stable `adapter` dependency), not suppressed.
- Not verified in this sandbox (no real Apple ID/2FA device): the actual
  `AppleConnectPanel` UI/UX in a real browser, and the true Apple
  login/2FA round-trip for either session - same category of "not verified
  here" as the CLI flows it replaces already were.

## v12.1: fix "Login failed: No module named 'rich'" on owner tracking
Trigger: real-user bug report immediately after v12 shipped, hit by
actually using the new "Eigener Standort" login panel.

Root cause: `pyicloud`'s own `__init__.py` unconditionally imports
`pyicloud.services.notes.rendering.exporter` (a Notes-service module,
unrelated to Find My iPhone device location), which does `from
rich.console import Console` at module load time - but `pyicloud` doesn't
declare `rich` as a dependency itself. `owner_tracking.py` only imports
`pyicloud` lazily inside `_build_api()`, so this was invisible to every
existing test (none of them actually trigger an owner-tracking login) and
to `pip install -e ".[dev]"` succeeding cleanly - the missing package only
surfaced the first time `start_owner_login`/`fetch_owner_location` actually
ran and tried `from pyicloud import PyiCloudService`.

- [x] `pyproject.toml`: added `rich>=13` as an explicit dependency, with a
      comment explaining it's a stand-in for `pyicloud`'s own incomplete
      dependency declaration, not something this app uses directly.
- [x] `tests/test_owner_tracking.py`: new regression test that just
      `import pyicloud`s - the cheapest test that would have caught this
      before it shipped.

## Review (v12.1)
- Verified against a truly clean install (fresh venv, not just the one
  already carrying `rich` from debugging this): `pip install -e ".[dev]"`
  then `import pyicloud` / `from pyicloud import PyiCloudService` /
  `import airtag_sentry.owner_tracking` all succeed. Full `pytest` (57
  passed) against real local Postgres. Confirmed no *further* missing
  transitive dependencies beyond `rich` by completing the same clean-install
  import chain end to end.
- Not re-verified: an actual owner-tracking login against real Apple
  servers (same sandbox limitation as v12) - but the specific reported
  failure (import-time `ModuleNotFoundError`) is fully reproduced and fixed
  independent of reaching Apple's servers at all.

## v12.2: fix wrong "use an app-specific password" README guidance
Trigger: real-user bug report with the v12.1 logging fix now in place -
the actual traceback showed `pyicloud.exceptions.PyiCloudFailedLoginException:
Invalid email/password combination` (Apple's `-20101`), i.e. a genuine auth
rejection, not a code bug. Root cause: v11's README told users to generate
and use an **app-specific password** for owner tracking - security-sensible
advice in general, but wrong for `pyicloud` specifically. Confirmed against
[picklepete/pyicloud#349](https://github.com/picklepete/pyicloud/issues/349):
`pyicloud` authenticates the same way signing into `icloud.com`/Find My
does (real account password + a live 2FA code) and cannot use an
app-specific password at all - it doesn't produce the tokens that login
step needs. Apple's server returns the exact same generic "-20101 Invalid
email/password combination" for this as for an actually-wrong password,
so a user following the old README instructions had no way to tell what
was actually wrong.

- [x] README: "Owner device tracking" section corrected - use your real
      Apple ID password, with an explanation of why an app-specific one
      fails and what error it produces, so this is diagnosable from the
      docs alone next time.
- [x] `owner_tracking.py`: `_build_api()` now catches
      `pyicloud.exceptions.PyiCloudFailedLoginException` specifically and
      re-raises with the app-specific-password hint appended, so the
      dashboard's error message (not just the README) points at the actual
      likely cause instead of repeating Apple's opaque `-20101` text
      verbatim.
- [x] `tests/test_owner_tracking.py`: new test mocking `PyiCloudService` to
      raise `PyiCloudFailedLoginException`, confirming `_build_api()` wraps
      it with the hint - real Apple auth still isn't exercisable here, but
      this pins down the wrapping logic itself.

## Review (v12.2)
- Verified: full `pytest` (59 passed) against real local Postgres,
  including the new mocked-failure test. No dependency/schema changes.
- Not verified in this sandbox (no real Apple ID available): that using the
  *correct* real-password flow actually succeeds end-to-end against Apple's
  live service - only that the specific wrong-password-type failure mode is
  now correctly explained both in the docs and in the error message itself.

## v12.3: persist the anisette container's device identity across restarts
Trigger: real-user bug report - a fresh AirTag-tracking login (not owner
tracking this time) failed 2FA submission with
`findmy.errors.UnhandledProtocolError: Error response for GSA request: 503`,
a raw HTTP 503 from Apple's own GrandSlam-auth endpoint, on three separate
attempts including a freshly-restarted login. Root cause: `docker-compose.yml`'s
`anisette` service had no persistent volume, so every container
restart/redeploy wipes its provisioned device identity, forcing it to
register as a brand-new "device" with Apple from scratch on the next
request - and several redeploys happened in quick succession while chasing
the two fixes just before this one. Repeated re-provisioning from the same
IP in a short window is exactly the kind of thing Apple's abuse detection
flags with a transient 503, unrelated to any actual bug in this app's own
authentication code (confirmed against the documented, official
[Dadoum/anisette-v3-server](https://github.com/Dadoum/anisette-v3-server)
run command, which mounts this exact path for this exact reason).

- [x] `docker-compose.yml`: `anisette` service now mounts a new
      `anisette_data` volume at `/home/Alcoholic/.config/anisette-v3/lib/`
      (the image's own documented persistent-data path).
- [x] README: Coolify section updated to list `anisette_data` among the
      volumes that must persist across redeploys, with the reason.

## Review (v12.3)
- One file (plus README) touched, no application code changes - purely a
  compose/infra fix.
- Verified: `docker compose config` (throwaway `.env`) parses cleanly and
  confirms the new volume mounts at the documented path.
- Not verified in this sandbox (no real Apple ID, no ability to run this
  compose stack for real here): that this actually stops the 503s in
  practice - the fix addresses a real, documented misconfiguration, but
  Apple's own rate-limiting/abuse-detection behavior isn't something that
  can be confirmed without watching a real deployment survive multiple
  redeploys without re-triggering it.

## v12.4: fix v12.3's anisette volume - it mounted the wrong subdirectory
Trigger: the 503 recurred hours after v12.3 deployed, on both 2FA methods.
User asked directly: "does it only meet the lib folder?" - yes, and that
was the bug. v12.3 mounted `anisette_data` at
`.../anisette-v3/lib/`, matching the upstream project's own documented
`docker run` example - but reading the actual server source
(`source/app.d` in [Dadoum/anisette-v3-server](https://github.com/Dadoum/anisette-v3-server))
shows `device.json` - the file holding the machine ID/UUID Apple actually
keys trust off - is written directly into `configurationPath`
(`~/.config/anisette-v3`), the *parent* of `lib/`. `lib/` itself only
caches two downloadable Apple libraries (`libCoreADI.so`/
`libstoreservicescore.so`), which aren't identity-bearing at all. So v12.3
persisted the one thing that didn't matter and silently missed the one
thing that did - every redeploy was still generating a brand-new device
identity exactly as before, with no error to reveal it.

Also audited: this prompted a full re-check of every env var in both
`app`'s and `dashboard`'s `environment:` blocks against what `config.py`
actually reads - none were stale. `APPLE_STORE_PATH`/
`APPLE_OWNER_SESSION_PATH`/`ANISETTE_LIBS_PATH` are deliberately absent
(code defaults, per earlier reviews) and still correctly so.

- [x] `docker-compose.yml`: `anisette_data` now mounts at
      `/home/Alcoholic/.config/anisette-v3/` (the parent), covering both
      `device.json` and `lib/` in one volume. Comment updated with the
      source-level explanation and an explicit warning not to trust the
      upstream README's own example path without checking the source, in
      case this image is ever updated again.

## Review (v12.4)
- One file touched, no application code changes.
- Verified: `docker compose config` (throwaway `.env`) parses cleanly and
  confirms the volume now mounts at the corrected parent path.
- Not verified in this sandbox (no real Apple ID, no way to run the actual
  anisette-v3-server binary here to inspect `device.json` being written):
  that a real deployment's `device.json` now survives a restart and that
  this actually stops the 503s in practice - confirmed by reading the
  server's own source code, not by observing the file get written.

## v13: Top safe-area title bar (replaces dead decorative panel)

Trigger: a follow-up round on v10's fix, done in a separate session and not
previously logged here. Real-device screenshots showed the fix's necessary
trade-off - switching `apple-mobile-web-app-status-bar-style` from
`black-translucent` to `black`/`default` to get the correct full-height
render surface (v10's actual bug) also means the status bar can no longer
be translucent, so the map can't bleed through it the way it used to. Two
follow-up attempts at softening that - a decorative "glass" panel under the
status bar (invisible there, since iOS paints an opaque bar on top
regardless of what the page draws), then a gradient fade at the map's top
edge - were both real-device-tested and rejected ("looks bad"/"weird").

Root cause of *why* neither worked: `apple-mobile-web-app-status-bar-style`
only has 3 values, and they split into two mutually exclusive behaviors -
either the status bar is translucent (but the render surface is buggy on
affected iOS versions, which is the v10 bug itself) or the render surface
is correct (but the status bar is opaque, no exceptions). There's no
in-between; see the new "Hard constraint" section in `CLAUDE.md` for the
full explanation, added specifically so this isn't relitigated.

Given that, decided to stop trying to fake translucency and lean into a
real title bar instead - the same pattern almost every non-immersive iOS
app already uses instead of edge-to-edge content.

- [x] `App.tsx`: replaced the dead decorative panel with a real title bar
      positioned at `top: env(safe-area-inset-top)` (right where the
      opaque status bar's reserved strip ends, so it's actually visible -
      confirmed by the fact that the *reverted* gradient fade, positioned
      identically, was clearly seen and disliked). Shows the selected
      AirTag's name, falling back to "AirTags" - reusing the same fallback
      already computed for `document.title`. Deliberately generic slot,
      not just today's content, so future per-AirTag meta (battery,
      last-seen, an alert badge) has an obvious place to go.
- [x] `index.css`: new `--header-h: 44px` var (same unconditional-in-`:root`-
      but-mobile-only-consumed pattern as the existing `--tabbar-h`). Also
      fixed a real regression the new title bar would otherwise have
      caused: `.leaflet-top`'s existing `top: env(safe-area-inset-top)`
      rule (from an earlier fix, pushing the map's zoom control down below
      the status bar) now collides with the title bar sitting at that same
      position - added a mobile-only override pushing the zoom control down
      by `--header-h` as well, so it clears the title bar instead of
      rendering underneath it.
- [x] `CLAUDE.md`: new "Hard constraint: iOS status bar can't be both
      correctly-sized and translucent" section, so a future session doesn't
      re-attempt the same two rejected approaches from scratch.

## Review (v13)
- Three files touched (`App.tsx`, `index.css`, `CLAUDE.md`), no
  backend/dependency changes.
- Verified: `npx tsc -b && npx vite build` clean; `npx oxlint` shows only
  the two pre-existing `set-state-in-effect` warnings (unchanged). Removed
  a leftover `aria-hidden="true"` from the old decorative panel's div now
  that it holds real, meaningful text (the AirTag name) - would have hidden
  it from screen readers otherwise.
- Not verified in this sandbox (no real iOS device, and this sandbox's
  Chromium doesn't reproduce genuine WebKit standalone-PWA status-bar
  rendering - the same limitation noted in v10's review): whether the
  title bar visually reads as intentional rather than as its own new "bar"
  - that judgment call is exactly why the two previous attempts needed
  real-device feedback to reject in the first place, and this one should
  get the same scrutiny before being considered settled.

## v14: Owner location history display

Trigger: owner-device location tracking (`owner_tracking.py`, added in
v11) has been fetching and recording history every poll since it shipped
(`tracker.py`'s `_update_owner_location()` → `db.py`'s
`record_owner_location()`, append-only into `owner_locations`), but
nothing ever read back more than the single latest row, and nothing in the
dashboard displayed it at all - not even the current position.
`frontend/src/api.ts` already had a dead `getOwnerLocation()` +
`OwnerLocation` type that no component called. This closes both gaps:
adds a history read path and surfaces both current location and history in
the UI, staying UI-first per `CLAUDE.md`.

- [x] `db.py`: new `fetch_owner_locations(conn, limit=200)`, newest-first,
      alongside the existing `latest_owner_location`. No migration needed -
      `owner_locations` and its `idx_owner_locations_recorded_at DESC`
      index (from the v11 migration) already support this query as-is.
- [x] `web/app.py`: new `GET /api/owner-location/history` route, same dict
      shape as the existing `/api/owner-location`, just as a list.
- [x] `api.ts`: `getOwnerLocationHistory(limit=200)`, one-liner mirroring
      `getReports`.
- [x] `mapIcons.ts`: promoted `MapCard.tsx`'s local pulsing-dot
      `CURRENT_LOCATION_ICON` div-icon into a shared `currentLocationIcon`
      export, reused for the owner's position rather than inventing a new
      marker style.
- [x] `MapCard.tsx` / `OverviewMap.tsx`: new optional `ownerLocation` prop,
      rendered as a `currentLocationIcon` marker alongside the existing
      AirTag marker(s)/polyline - the one place "moved without you" becomes
      visually checkable at a glance. Owner position is deliberately left
      out of `FitBounds`'s bounds calculation so a lone owner marker can't
      dominate zoom before any AirTag has reported.
- [x] `App.tsx`: lifted `ownerLocation` state, fetched once on mount
      alongside `refreshAirtags()`, passed down to both map components -
      same top-down flow already used for `statuses`/`reports`.
- [x] `AppleConnectPanel.tsx`: `AppleConnectAdapter` gained optional
      `getLocation`/`getHistory` (absent for the AirTag-tracking adapter,
      same optionality pattern as the existing `selectMethod?`). When
      present and connected, the "Eigener Standort" row now shows the
      current position + relative time, plus a lazy-loaded "Verlauf" list
      matching `AirtagDetail.tsx`'s `HistoryList` styling (skips the
      reverse, since the API is already newest-first).
- [x] `SettingsPanel.tsx`: wired `OWNER_APPLE_ADAPTER` with the new
      `getLocation`/`getHistory`; `AIRTAG_APPLE_ADAPTER` untouched (no
      location concept there).
- [x] `test_db.py`: new
      `test_fetch_owner_locations_returns_newest_first_and_respects_limit`.

## Review (v14)
- 9 files touched (2 backend, 6 frontend, 1 test), no schema/migration
  change, no new dependencies.
- Verified: `pytest` against real local Postgres - 60 passed, including the
  new test. `cd frontend && npx tsc -b && npx vite build` clean; `npx
  oxlint` shows only the same two pre-existing `set-state-in-effect`
  warnings from v13 (unchanged - the new owner-location effect in
  `App.tsx` did not add a new one). `docker compose config` parses cleanly
  with a throwaway `.env`.
- Not verified in this sandbox: true end-to-end with a live Apple
  owner-tracking session (no real Apple ID/2FA available here, same
  limitation noted in v11's and v13's reviews) - confirmed instead against
  the real Postgres round-trip test and a clean build. The map marker and
  history list should be checked visually against a real connected account
  before considering this fully settled.

## v15: Customizable per-AirTag icons + interactive map markers

Every AirTag used to render with the same fixed ring glyph everywhere
(list row, detail header, map pin), with only its accent color varying -
and that color wasn't stored either, just a hash of the AirTag's `id`
(`airtagColor.ts`). No way to tell "the bike" from "the backpack" at a
glance beyond the name text. Adds a real per-device identity: a chosen
icon (from a curated 12-icon set) and color, picked from the dashboard,
reused consistently in the list/detail avatar and the map marker, plus an
"In Karten öffnen" deep link on marker popups to hand off to the device's
native Maps app.

- [x] New migration (`8a7b73c5121e`): nullable `icon`/`color TEXT` columns
      on `airtags`. `NULL` is a first-class "automatic" state (today's
      hash-derived behavior), not a backfill target - every existing
      AirTag renders unchanged until customized.
- [x] `db.py`: `AirtagRecord` gained `icon`/`color`; `create_airtag`/
      `list_airtags`/`rename_airtag` select the new columns; new
      `set_airtag_appearance(conn, airtag_id, icon, color)`.
- [x] `web/app.py`: new `PATCH /api/airtags/{airtag_id}/appearance`
      (`AirtagAppearanceIn`), validated server-side against an
      `AIRTAG_ICON_CHOICES` allow-list (kept in sync with
      `deviceIcons.tsx`'s registry by comment) and a `#rrggbb` regex for
      color - never trusts the client. `GET`/`POST /api/airtags` responses
      extended with `icon`/`color`.
- [x] `frontend/src/deviceIcons.tsx` (new): 12 hand-rolled device glyphs
      (bike, backpack, car, wallet, suitcase, laptop, camera, pet,
      headphones, book, box, plus the existing key icon reused for
      "keys") - no icon library added, matching `icons.tsx`'s existing
      "no dependency needed for this few" approach, and Leaflet's
      `divIcon` needs raw SVG markup anyway.
      `frontend/src/deviceIconRegistry.ts` (new): the name/component/label
      registry, split into its own module so `deviceIcons.tsx` exports
      only components (Fast Refresh requirement, caught by `oxlint`'s
      `react/only-export-components`).
- [x] `mapIcons.ts`: 1:1 raw-SVG-string mirror of the same 12 icons for
      the map pin (divIcon content is plain HTML, not React - same reason
      the ring glyph was already duplicated this way); `airtagPinIcon` now
      takes `{ id, icon, color }` instead of just `id`.
- [x] `AirtagAvatar.tsx`: takes the full `airtag` object instead of just
      `airtagId`, resolving chosen icon/color with the automatic
      fallback - shared by `AirtagList.tsx`'s row and `AirtagDetail.tsx`'s
      header avatar.
- [x] `AirtagDetail.tsx`: new "Symbol & Farbe" `Section`/`Row` (icon grid
      + color swatches, immediate-apply per tap like `SettingsPanel.tsx`'s
      `ThemeField` - no separate save button), plus a new `PaletteIcon` in
      `icons.tsx` for the row.
- [x] `frontend/src/maps.ts` (new): `mapsUrl(lat, lon, label)` - an Apple
      Maps web link (hands off to the native app on iOS/macOS, or just
      opens as a normal website otherwise) on Apple platforms, a Google
      Maps universal link elsewhere.
- [x] `MapCard.tsx`/`OverviewMap.tsx`: markers now pass the full airtag to
      `airtagPinIcon`; popups gained an "In Karten öffnen" link next to
      the existing "Details anzeigen" button.
- [x] `test_db.py`: new `test_set_airtag_appearance_round_trip`.

## Review (v15)
- 14 files touched (1 migration, 2 backend, 10 frontend, 1 test), 2 new
  frontend files (`deviceIcons.tsx`, `deviceIconRegistry.ts`, `maps.ts`),
  no new dependencies (icons are hand-rolled SVG, matching the existing
  convention).
- Verified: `pytest` against a real local Postgres (started directly via
  the sandbox's `postgresql` package, no Docker daemon available here) -
  61 passed, including the new appearance round-trip test and the full
  existing suite unaffected. `cd frontend && npx tsc -b && npx vite build`
  clean; `npx oxlint` initially flagged 9 new `react/only-export-components`
  warnings from mixing icon components with registry data in one file -
  fixed by the `deviceIcons.tsx`/`deviceIconRegistry.ts` split, leaving
  only the same two pre-existing `set-state-in-effect` warnings from
  v13/v14 (untouched by this change). `docker compose config` parses
  cleanly with a throwaway `.env`.
- Live-verified in-browser (no Docker daemon in this sandbox either, so a
  local Postgres 16 cluster + a `python -m airtag_sentry serve` process
  stood in for `docker compose up`, with two seeded AirTags/reports and a
  hand-minted dev-only session cookie to get past GitHub OAuth): opened
  the "Symbol & Farbe" picker, picked the bike icon + green, confirmed the
  list row, detail header, and both the detail map pin and the overview
  map pin all updated to match; clicked a marker's popup and confirmed
  "In Karten öffnen" renders with a correct
  `google.com/maps/search/?api=1&query=<lat>,<lon>` link (headless
  Chromium's UA isn't Apple, so the Google Maps branch was the one
  exercised - the `maps.apple.com` branch is a one-line UA check, not
  independently verified here). OpenStreetMap tile fetches themselves
  failed in this sandbox (same outbound-proxy restriction noted since
  v1's review) but don't affect the app's own marker rendering, which
  doesn't depend on them.
## v16: Owner device in the main AirTags list

Trigger: v14 surfaced owner location on the map and in Settings ->
Apple-Konten, but a connected owner device was otherwise invisible - you
had to open Settings to even know owner tracking existed. The main
AirTags list (the "Objects" tab, `AirtagList.tsx`) is the first thing the
dashboard shows, so a connected owner device belongs there too, not only
tucked away in Settings.

- [x] `icons.tsx`: new `PersonIcon` (simple head-and-shoulders glyph) for
      the owner row - distinct from `AirtagGlyph` so it doesn't read as
      "just another AirTag".
- [x] `AirtagList.tsx`: new `ownerConnected`/`ownerLocation` props. When
      `ownerConnected`, renders a "Du" row at the top of the list (above
      the AirTags), styled to match the AirTag rows (same avatar-badge +
      title/subtitle layout) with its own accent-colored `PersonIcon`
      badge instead of an `AirtagAvatar`, and the same relative-time
      subtitle convention (`formatRelative`/"Kein Standort verfügbar")
      already used for AirTags without a report. Not clickable - there is
      no owner detail view (setup still lives in Settings ->
      Apple-Konten's `AppleConnectPanel`), this is a status glance only.
- [x] `App.tsx`: added `ownerConnected` state, fetched via the existing
      `getOwnerAppleStatus()` (already used by `SettingsPanel.tsx`) in the
      same mount effect as `ownerLocation`; both passed down to
      `AirtagList`.

## Review (v16)
- 3 files touched, all frontend, no backend/schema change, no new
  dependencies.
- Verified: `cd frontend && npx tsc -b && npx vite build` clean; `npx
  oxlint` shows only the same two pre-existing `set-state-in-effect`
  warnings from v13/v14 (unchanged - the added `getOwnerAppleStatus` call
  lives in the same effect as the existing `getOwnerLocation` call, so no
  new warning).
- Not verified in this sandbox: visually, against a real connected owner
  Apple account (no real Apple ID/2FA available here, same limitation
  noted in v11/v13/v14's reviews) - the row's conditional rendering and
  data flow were checked by reading `SettingsPanel.tsx`'s existing
  `OWNER_APPLE_ADAPTER` usage of the same `getOwnerAppleStatus`/
  `getOwnerLocation` calls, not by exercising the UI live.

## v17: Explicit owner device selection + movement trail

Trigger: two follow-ups to v14/v16. First, `owner_tracking.fetch_owner_location()`
returned whichever device on the connected Apple account answered first
with a location - not deterministic, and not something the user could
choose. Second, owner location has had a full history in `owner_locations`
since v11 (already listed in Settings), but the map only ever showed the
single latest position, never a route like AirTags get.

Also found while rewriting the fetch: this project's `pyicloud>=1.0` pin
currently resolves to 2.7.0, where `AppleDevice.location` is a `@property`,
not a method - the existing `device.location()` call would raise
`TypeError` the moment a real account returned a location. Fixed alongside
the rewrite (verified by downloading the pyicloud wheel and reading
`pyicloud/services/findmyiphone.py` directly, not by installing a live
Apple session).

Per `CLAUDE.md`'s "no backward-compatibility shims" convention, this is a
deliberate breaking change: owner location now stops being fetched until a
device is explicitly selected in Settings - no fallback to "first device
that answers", including for the account already connected before this
shipped.

- [x] New migration `a39d0f20721f`: `owner_apple_credentials` gains
      nullable `selected_device_id`/`selected_device_name` columns. The
      name is stored alongside the id so the dashboard can label the
      connection ("Verbunden · iPhone von Marius") without another Apple
      login just to resolve it.
- [x] `db.py`: `OwnerAppleCredentials` gains both fields;
      `set_owner_apple_credentials` now resets them to `NULL` on every
      fresh login (a previous pick may not even exist on a different
      session); new `set_owner_selected_device(conn, device_id, device_name)`.
- [x] `owner_tracking.py`: new `list_owner_devices()` (iterates
      `api.devices`, using the real `AppleDevice.name`/`.model_name`
      properties) and `set_selected_device()`; `fetch_owner_location()`
      rewritten to return `None` immediately (no Apple call at all) when
      no device is selected, otherwise match the selected device by id and
      read `.location` as a property (the pyicloud fix above). New
      `connection_status()` helper backing the status route below (which
      fully supersedes the old `is_connected()`, removed as dead code).
- [x] `web/app.py`: `owner_apple_status()` now returns
      `selected_device_id`/`selected_device_name` too; new
      `GET /api/apple/owner/devices` and `POST /api/apple/owner/device`
      routes.
- [x] `api.ts`: `OwnerDevice` type, `getOwnerDevices()`,
      `selectOwnerDevice()`; `getOwnerAppleStatus()`'s return type gained
      the two new fields.
- [x] `AppleConnectPanel.tsx`: `AppleConnectAdapter` gained optional
      `getDevices`/`selectDevice` (absent for the AirTag-tracking adapter,
      same optionality pattern as `getLocation`/`getHistory`). When
      connected with no device chosen yet, a required device list replaces
      the usual "done" state; once picked, the row shows "Verbunden ·
      <name>" with a "Gerät ändern" action to reopen the same list.
- [x] `SettingsPanel.tsx`: wired the two new adapter fields for
      `OWNER_APPLE_ADAPTER` only.
- [x] `App.tsx` / `AirtagList.tsx`: the v16 "Du" row now shows the selected
      device's name instead of the generic "Du" once one is picked, and
      "Gerät in Einstellungen auswählen" instead of "Kein Standort
      verfügbar" while connected but still unselected - directly naming
      the state the real connected account is in immediately after this
      ships.
- [x] `mapIcons.ts`: new `OWNER_TRAIL_COLOR` constant (a literal hex, not
      `var(--accent)` - Leaflet sets it as a plain SVG `stroke` attribute,
      not a CSS property). `MapCard.tsx`/`OverviewMap.tsx` gained an
      `ownerLocationHistory` prop, drawn as a dashed `Polyline` (2+ points)
      so it reads as "your trail" without being confused with the AirTag
      route's solid line despite the similar blue; left out of
      `FitBounds`'s bounds calc for the same reason the single owner
      marker already was.
- [x] `test_db.py`: new
      `test_owner_selected_device_persists_and_resets_on_relogin`;
      extended the existing credentials round-trip test to check the new
      columns default to `NULL`.
- [x] `test_owner_tracking.py`: new tests for the "no device selected -
      no Apple call" short-circuit, `list_owner_devices` returning `[]`
      when disconnected, and a regression guard (a fake device exposing
      `location` as a `@property`) for the pyicloud fix.

## Review (v17)
- 10 files touched (1 migration, 3 backend, 2 backend tests, 4 frontend),
  no new dependencies.
- Verified: `pytest` against real local Postgres (migration applied via
  `alembic upgrade head`) - 50 passed, 14 skipped (unrelated), including
  the 4 new tests. `cd frontend && npx tsc -b && npx vite build` clean;
  `npx oxlint` shows only the same two pre-existing `set-state-in-effect`
  warnings from v13/v14/v16 (two new ones surfaced while writing the device
  picker's effects and were fixed by keeping `setState` calls inside
  `.then()`/`.catch()` rather than synchronously in the effect body, and
  by inlining the status-fetch effect instead of calling a named
  non-memoized function from it). `docker compose config` parses cleanly
  with a throwaway `.env`.
- Not verified in this sandbox: a live Apple 2FA session, so the device
  list/selection UI and the map trail should get a visual check against
  the real connected account before considering this fully settled (same
  standing caveat as v11/v13/v14/v16) - that account is specifically the one
  that motivated this version, so re-selecting its device once this ships
  is a needed manual step, not optional polish.

## v18: Multi-device owner tracking with a single primary device

Trigger: user asked for multiple trackable devices ("not AirTags, like
AirPods, macs etc"), built concurrently with v17 in a separate session -
both touched the same "which Apple device is the owner" problem from
different angles and landed within minutes of each other, so this version
reconciles them via a real merge conflict rather than picking one wholesale.
User's resolution when asked: "I want a single device as 'my' location but
have multiple devices in the location list" - i.e. v17's "exactly one
device, chosen explicitly" instinct was right for away-correlation, but
the account should still show every device it can see, each independently
trackable/historized like v17's location trail already treats one.

Supersedes v17's `owner_apple_credentials.selected_device_id/_name`
mechanism entirely - replaced by a proper device registry
(`owner_devices`) where any number of devices can be enabled (tracked,
each with its own history) and at most one of those is additionally
*primary* (a partial unique index enforces this in Postgres itself). The
primary device is the one used for "moved without you" away-correlation
and the map's dashed location trail - both v17 features, now sourced from
`owner_devices.is_primary` instead of the dropped columns. Every other
enabled device is still listed with its own history and its own map
marker; it just doesn't affect either. Independently rediscovered v17's
`.location()`-vs-`.location`-property bug fix and found + fixed a second,
real bug on the same path: `PyiCloudService(...)` starts a background
thread re-polling Apple every 5 minutes on first `.devices` access, never
stopped - since a fresh instance is built every poll (`_build_api()`),
forever, the process was leaking one live thread per poll. Fixed by
collecting everything needed from `.devices` in one pass, then calling
`api.devices.stop_event.set()` as the very last thing touching it.

AirPods stay explicitly out of scope (unchanged from v17's framing): Find
My-capable AirPods (Pro/Max) use the same offline-finding network as
AirTags, not this device service - already trackable via the existing
"Manage AirTags" key-upload flow. User confirmed this scope split.

- [x] New migration `bf40cb34ac74` (revises `a39d0f20721f`): drops
      `owner_locations` (never held usable data - v17's own investigation
      found the same fetch bug) and v17's `selected_device_id`/`_name`
      columns on `owner_apple_credentials`; adds `owner_devices` (id, name,
      device_type, `enabled`, `is_primary` with a `WHERE is_primary` partial
      unique index) and `owner_device_locations` (per-device history,
      mirrors `location_reports`, FK'd `ON DELETE CASCADE`).
- [x] `db.py`: `OwnerDevice` dataclass (`enabled` + `is_primary`);
      `OwnerLocation` gained `device_id`. New `upsert_owner_devices`,
      `list_owner_devices`, `set_owner_device_enabled` (clears
      `is_primary` when disabling - a disabled device never gets a fresh
      location, so leaving it primary would silently stop
      away-correlation with no visible signal why), `set_owner_device_primary`
      (exclusive - clears any previous primary first - and force-enables
      the new one), `record_owner_device_location`,
      `latest_owner_device_locations` (one row per enabled device),
      `latest_primary_owner_device_location` (feeds away-correlation),
      `fetch_owner_device_location_history`. Removed v17's
      `selected_device`-shaped fields/functions.
- [x] `owner_tracking.py`: new `_snapshot_devices(api)` - one pass over
      `api.devices` collecting `(id, name, device_type, location)` into
      plain data, fixing both bugs above in one place (reads `.location`
      as a property; stops the monitor thread last). `list_owner_devices`
      live-refreshes identity (DB `enabled`/`is_primary` flags intact);
      `set_device_enabled`/`set_device_primary`; `fetch_owner_device_locations`
      returns every enabled device's current location.
      `connection_status()` now reports `primary_device_id`/`_name`
      instead of v17's `selected_device_id`/`_name`.
- [x] `movement.py`: `evaluate_away` keeps its v14-era single-`OwnerLocation`
      signature (per the user's "single device as my location" call) -
      just now always sourced from the primary device specifically, not
      an arbitrary/first one.
- [x] `tracker.py`: `_update_owner_devices` records every enabled device's
      location each poll; away-correlation reads
      `latest_primary_owner_device_location(conn)`.
- [x] `web/app.py`: replaced v17's `GET /api/apple/owner/devices` +
      `POST /api/apple/owner/device` with `GET/PUT /api/owner-devices`,
      `PUT /api/owner-devices/{id}/primary`, `DELETE
      /api/owner-devices/primary`, `GET /api/owner-device-locations`
      (latest per enabled device, joined with device name for map
      popups), `GET /api/owner-devices/{id}/history`. `owner_apple_status()`
      keeps calling `connection_status()`, now primary-shaped.
- [x] Frontend: new `OwnerDevicesPanel.tsx` (Settings -> Eigener Standort)
      - the actual device list/history UI, superseding v17's in-panel
      picker inside `AppleConnectPanel.tsx`. Each device gets an enable
      checkbox (list membership) and a star toggle (`StarIcon`, new in
      `icons.tsx`) for primary (exclusive - picking one clears any other).
      `AppleConnectPanel.tsx` reverted to a plain, adapter-agnostic
      connect/disconnect wizard - device management doesn't belong in a
      component shared with the AirTag-tracking adapter, which has no
      device concept at all. `MapCard.tsx`/`OverviewMap.tsx` keep v17's
      dashed trail, now drawn once per *enabled* device (`ownerLocationHistories`,
      keyed by `device_id` - user pushed back on an earlier draft that only
      trailed the primary device: "the location trail should be active for
      all devices") plus one marker per enabled device (`ownerLocations`,
      was a single conditional marker). Only away-correlation and the "Du"
      row stay primary-only, matching the user's actual ask ("single device
      as my location, but multiple in the location list"). `App.tsx`
      derives the primary device's own location from the enabled-devices
      array for `AirtagList`'s "Du" row rather than a separate fetch, and
      fetches every enabled device's history in parallel for the trails.
- [x] Tests: `test_db.py` replaced v17's selected-device test with
      registry + primary-exclusivity + per-device-history round-trips
      (including that disabling the primary clears `is_primary`, and that
      `latest_primary_owner_device_location` ignores enabled-but-not-primary
      devices even with a recorded location). `test_movement.py` unchanged
      from v14 (signature reverted to match). `test_owner_tracking.py`
      kept v17's "not connected" guard, replaced its selected-device
      fetch tests with a fake-`api.devices` regression test proving
      `_snapshot_devices` reads `.location` without calling it and always
      stops the monitor thread.

## Review (v18)
- 17 files touched (5 backend + 1 migration, 7 frontend, 3 tests, this
  changelog), one new migration, no new dependencies. Net effect after
  reconciling with v17: same file set v17 touched, plus `movement.py`
  untouched (signature already matched what v17 needed) and
  `OwnerDevicesPanel.tsx`/`icons.tsx` as the only genuinely new files.
- Verified: recreated the local Postgres test database from scratch
  before the full suite (the persistent one had a stale `alembic_version`
  pointer from mid-reconciliation migration-chain edits, which silently
  skipped the intervening migrations rather than erroring - worth
  remembering if a future session sees mysteriously-missing columns
  against a long-lived local test DB). `pytest` - 69 passed, including all
  new/updated tests. `cd frontend && npx tsc -b && npx vite build` clean;
  `npx oxlint` shows three `set-state-in-effect` warnings - the two
  pre-existing ones from v13/v14/v16/v17, plus one new one on the
  owner-location-histories clear-when-empty effect, which follows the
  exact same early-return-then-setState shape as the already-accepted
  `setReports([])` one a few lines below it rather than introducing a new
  pattern. `docker compose config` parses cleanly with a throwaway `.env`.
- Not verified in this sandbox: true end-to-end with a real multi-device
  Apple account (no real Apple ID with several real devices available
  here, same limitation noted in every prior owner-tracking review,
  v17 included) - confirmed instead against the real Postgres round-trip
  tests, a targeted fake-API regression test for both bugs, and a clean
  build. The device list, star/checkbox interaction, map markers, and
  trail should get a real-account check before this is considered fully
  settled.

## v19: Fallback to import an existing Apple session, bypassing live login

Trigger: real-user follow-up on v12.3/v12.4. Even after redeploying with
v12.4's corrected anisette volume mount, AirTag-tracking login still failed
with `findmy.errors.UnhandledProtocolError: Error response for GSA request:
503` on both 2FA methods, across multiple attempts - confirming (per
`tasks/roadmap.md` #12's own stated criterion) that the anisette
persistence fix alone doesn't resolve this for this account, and it's time
to build the documented fallback: generate the Apple session somewhere
other than this app's own container, and upload it instead of performing
the live handshake there. Built concurrently with v18 above in a separate
session; rebased onto it here rather than v18's now-superseded shape -
`AppleConnectPanel.tsx`'s device-picker plumbing that this originally
piggybacked its `importSession` optionality comment on is gone in v18,
replaced by the standalone `OwnerDevicesPanel.tsx`.

Read `FindMy.py`'s actual `AppleAccount.to_json()`/`from_json()` (installed
in a scratch venv, since it isn't vendored here) to confirm the exact shape
needed and that `from_json()` accepts an already-parsed dict directly (not
just a file path) - important, since `read_data_json()` treats a bare `str`
argument as a filesystem path, not raw JSON text, so the new endpoint must
hand it a parsed object, never a string. Also confirmed the account's
anisette provider type/state travels *inside* the session JSON itself
(`{"type": "aniRemote", ...}` vs `{"type": "aniLocal", "prov_data": ...}`),
not from this app's own `ANISETTE_MODE` config - so a session imported this
way uses whatever anisette identity it was generated with, independent of
this container's `remote` anisette service entirely.

- [x] `auth.py`: new `import_session(cfg, session_json: dict)` - validates
      via `AppleAccount.from_json()`, wraps any failure as `ValueError`,
      then writes it to `APPLE_STORE_PATH` via the same `account.to_json()`
      call the live-login flow already uses.
- [x] `web/app.py`: new `AppleSessionImportIn` model and
      `POST /api/apple/session` route.
- [x] `api.ts`: new `appleImportSession()`.
- [x] `AppleConnectPanel.tsx`: `AppleConnectAdapter` gained optional
      `importSession`, present for the AirTag-tracking adapter only, since
      owner tracking's `pyicloud` session has an unrelated shape and isn't
      affected by this issue. Credentials step gained a file picker below
      the login form, reusing `AirtagDetail.tsx`'s `KeyForm` file-input
      styling, reading the file client-side (`file.text()` + `JSON.parse`)
      rather than a true multipart upload - consistent with how the
      existing AirTag-key JSON upload already works. Resolved cleanly
      against v18's reverted, adapter-agnostic version of this file (v18
      removed the device-picker UI this originally sat next to; the
      import-session addition is independent of that and needed no
      rework).
- [x] `SettingsPanel.tsx`: wired `importSession` for `AIRTAG_APPLE_ADAPTER`
      only.
- [x] `scripts/generate_apple_session.py`: new standalone script - login
      with `LocalAnisetteProvider` on any machine (no macOS/Keychain access
      needed, unlike the *AirTag key* extraction step this was modeled on)
      and write `account.json` for upload. Deliberately runs the handshake
      from a different network than the container (a home/residential IP
      instead of wherever it's hosted) and with a completely fresh anisette
      identity - either of which may be what Apple's abuse detection was
      flagging, though which one (or both) can't be confirmed without a
      real retry.
- [x] README: new "Troubleshooting: login fails with `GSA request: 503`"
      subsection documenting the workaround.
- [x] `tasks/roadmap.md`: #12 marked done with the outcome.
- [x] `test_auth.py`: new `_cfg` gains `anisette.libs_path`;
      `test_import_session_writes_valid_session_to_store_path` (using a
      hand-built minimal valid session dict, verified against the real
      `findmy` package in a scratch venv) and
      `test_import_session_rejects_malformed_session_json`.

## Review (v19)
- 8 files touched (2 backend, 1 new script, 3 frontend, 1 test, README +
  roadmap docs), no new dependencies - `findmy`'s login primitives
  (`AppleAccount`, `LocalAnisetteProvider`) were already a dependency, just
  newly imported in the standalone script.
- Verified before v18 landed: `pytest tests/` - 52 passed, 15 skipped
  (Postgres-dependent, no live Postgres in this sandbox), including the 2
  new tests. Confirmed the minimal session fixture and the
  `from_json`/`read_data_json` path-vs-dict behavior directly against the
  real `findmy` package installed in a scratch venv, not guessed from
  docs. `cd frontend && npx tsc -b && npx vite build` clean; `npx oxlint`
  clean apart from the two pre-existing `set-state-in-effect` warnings.
  `docker compose config` (throwaway `.env`) parses cleanly.
- Then rebased onto v18 (merge conflict in `AppleConnectPanel.tsx` -
  resolved by dropping this branch's now-obsolete `OwnerDevice`/
  `OwnerLocation`/`formatRelative` imports in favor of v18's leaner ones,
  keeping this branch's `ChangeEvent` import and `importSession` addition
  intact - and in this changelog, resolved by reordering to keep both
  entries with v18 first). Re-ran the same checks against the merged tree:
  `pytest tests/` - 51 passed, 20 skipped (still no live Postgres here, so
  v18's own Postgres-backed tests count among the skips and its "69
  passed" figure isn't independently reproduced by this rebase - only that
  nothing broke among what could run); `tsc -b && vite build` clean;
  `oxlint` shows the same three warnings v18's own review already noted
  (two pre-existing, one from v18's clear-when-empty effect), nothing new
  from this branch's changes.
- Not verified in this sandbox (no real Apple ID, no way to trigger a real
  GSA 503 here): that this fallback actually gets the specific reporting
  user connected - the validation/round-trip logic is confirmed correct
  against the real `findmy` package, but the end-to-end "run the script on
  your own machine, upload the result, does Apple accept it" path needs a
  real retry against their account to fully close this out.

## v20: Fix silent hang on GET /api/owner-devices errors

Trigger: real-user report right after v18 (multi-device owner tracking)
deployed - "the device list is loading forever." Also saw a `GET
/api/owner-location 404` in their logs, from v18's own removal of that
route (superseded by `/api/owner-device-locations`) - almost certainly a
stale already-open PWA session running pre-v18 JS rather than a code bug
(the SW is already configured with `skipWaiting`/`clientsClaim` for
exactly this, per `sw.ts`'s own comment, but that only takes effect on the
*next* navigation/reload of an already-running page, not instantly for a
backgrounded/resumed tab) - not otherwise actionable from this session
without a live report of it recurring after a fresh reload.

The "loading forever" part had a real, separate cause though:
`owner_tracking.list_owner_devices()` does a *live*, uncached Apple call
on every single request (rebuilds `PyiCloudService` fresh each time, per
v18's own `_connect`/`_build_api`) - a lapsed pyicloud session trust, a
transient network blip, or Apple-side rate limiting all raised uncaught
through `GET /api/owner-devices`, producing a bare 500 with no detail.
`OwnerDevicesPanel.tsx` had no `.catch()` on that fetch at all, so the
promise rejection just left `devices` at `null` forever - "Lädt…" with no
error, no retry, no way to tell what was wrong.

- [x] `web/app.py`: `get_owner_devices()` now wraps the call in
      try/except, logs it, and returns a 400 with the exception's message
      - same pattern already used by the Apple login/2FA routes.
- [x] `OwnerDevicesPanel.tsx`: new `devicesError` state; the fetch effect
      now has a `.catch()`; on error, shows the message plus a "Erneut
      versuchen" retry button (useful here specifically, since the
      underlying call is a fresh live Apple request every time - a retry
      can genuinely succeed where the last one didn't). Kept the
      `setDevicesError` call inside the `.then()`/`.catch()` callbacks
      rather than synchronously in the effect body - oxlint's
      `set-state-in-effect` flagged an earlier draft that called a named
      `async function loadDevices()` directly from the effect (it traces
      into local function calls, not just literal `setState(...)` in the
      effect's own body); resolved by keeping the effect's own fetch
      chain fully inline and defining `loadDevices()` separately purely
      for the retry button's `onClick`, matching this file's and
      `App.tsx`'s existing convention for this exact lint rule.
- [x] `test_web_auth.py`: new
      `test_owner_devices_route_reports_apple_errors_instead_of_hanging`,
      monkeypatching `owner_tracking.list_owner_devices` to raise and
      confirming the route now returns 400 with the error detail instead
      of an unhandled 500.

## Review (v20)
- 3 files touched (1 backend, 1 frontend, 1 test), no new dependencies.
- Verified: `pytest tests/` - 52 passed, 20 skipped (Postgres-dependent,
  no live Postgres in this sandbox), including the new regression test.
  `cd frontend && npx tsc -b && npx vite build` clean; `npx oxlint` shows
  only the same three pre-existing `set-state-in-effect` warnings from
  v13/v14/v16/v17/v18, no new ones (after iterating past one new one an
  earlier draft introduced - see above).
- Not verified in this sandbox (no real owner-tracking Apple session, no
  way to reproduce a real pyicloud failure here): that this specific fix
  resolves the reporting user's actual "loading forever" symptom - the
  error-handling path itself is covered by the new test, but whether their
  underlying Apple call was in fact failing (versus, say, succeeding but
  slowly) isn't confirmed. Also unconfirmed: whether the `/api/owner-location
  404` in their logs was a one-time artifact of the v18 deploy transition
  (stale already-open tab) or is still recurring after a fresh reload -
  worth asking before assuming it's fully explained.

## v21: Telegram + general notifications moved into Settings UI
Trigger: asked to move Telegram config into the dashboard and move the
general (not per-AirTag) notification controls out of the objects panel.
Two unrelated CLAUDE.md violations in one go: Telegram was still a CLI-era
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` env-var pair (everything else
notification-adjacent already moved to the dashboard), and the Web Push
"enable notifications" toggle - which subscribes the whole browser, not one
AirTag - lived in `AirtagList`'s header bell and a per-AirTag
"Benachrichtigungen" row in `AirtagDetail` instead of Settings.

- [x] Telegram credentials follow the same treatment owner-tracking's Apple
      password got (`owner_apple_credentials`): a dashboard connect flow,
      encrypted bot token in a new singleton `telegram_settings` table (row
      absence = "not configured"), never in `.env`. New migration
      `f3a4c8e1d9b2_telegram_settings`.
- [x] `db.py`: `TelegramCredentials` dataclass +
      `set_telegram_credentials`/`get_telegram_credentials`/
      `delete_telegram_credentials`, mirroring the owner-Apple-credentials
      functions exactly.
- [x] `config.py`: dropped `TelegramConfig`/`NotificationsConfig.telegram`
      and the `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` env reads - no
      backward-compat shim, per CLAUDE.md's established convention.
- [x] `notifiers/__init__.py`: `build_notifiers()` now takes the DB
      connection too and looks up Telegram credentials there instead of on
      `cfg.notifications`, decrypting the bot token with the existing
      `AIRTAG_KEY_ENCRYPTION_KEY`. `tracker.py`'s one call site updated.
- [x] `web/app.py`: `GET/POST/DELETE /api/notifications/telegram` (status
      never returns the bot token back, same as the Apple-login routes
      never echo the password).
- [x] Frontend: new `TelegramPanel.tsx` (same connect/disconnect shape as
      `AppleConnectPanel.tsx`, minus 2FA - just bot token + chat ID) and a
      `PaperPlaneIcon`. `SettingsPanel.tsx` gained a "Benachrichtigungen"
      section (push toggle, moved from the objects panel, + `TelegramPanel`)
      placed right after "Darstellung". `AirtagList.tsx` lost its header
      bell button and `AirtagDetail.tsx` lost its per-AirTag
      "Benachrichtigungen" row - both took `pushStatus`/`onEnablePush` as
      props purely to render that control, now dropped along with it;
      `App.tsx` passes them to `SettingsPanel` instead.
- [x] `.env.example`/`docker-compose.yml`/README: removed the two Telegram
      env vars, README's Notifications table points at Settings ⚙️ →
      **Benachrichtigungen** instead.
- [x] Tests: `test_db.py` gained the same set/get/delete round-trip test
      as the owner-Apple-credentials one, plus `telegram_settings` in the
      schema-tables assertion and the per-test truncate list.

## Review (v21)
- 13 files touched (5 backend + 1 migration, 6 frontend, 1 test) + 3 docs
  files, one new migration, no new dependencies.
- Verified: recreated both local Postgres databases (`airtag_sentry` and
  the `airtag_sentry_test` `test_db.py` targets) from scratch and ran
  `alembic upgrade head` against each - the new migration chains cleanly
  onto v18's head. `pytest` - 70 passed (69 prior + the new Telegram
  round-trip), 0 skipped once both DBs existed. `cd frontend && npx tsc -b
  && npx vite build` clean; `npx oxlint` shows the same three pre-existing
  `set-state-in-effect` warnings as v18, none new. `docker compose config`
  parses cleanly with a throwaway `.env` containing no `TELEGRAM_*` vars.
- Not verified: an actual Telegram bot end-to-end (no bot token available
  in this sandbox) - `notifiers/telegram.py` itself is unchanged and still
  covered by `test_notifiers.py`'s mocked-HTTP test, so this only leaves
  the new dashboard connect flow (encrypt → store → decrypt → send)
  unexercised against a real bot; worth a real-token smoke test before
  relying on it.

## v22: Fix silent no-op when checking/favoriting an owner device fails

Trigger: user report - "cannot set device in iCloud devices as favorite or
check it." Same root cause class as v20 (which fixed the analogous problem
for the device *list* fetch): `OwnerDevicesPanel.tsx`'s `toggle()` (the
enabled checkbox) and `togglePrimary()` (the favorite star) called
`setOwnerDeviceEnabled`/`setOwnerDevicePrimary`/`clearOwnerDevicePrimary`
with no `try`/`catch` at all. Since the checkbox/star are controlled by
`device.enabled`/`device.is_primary` from state, a rejected request (a
lapsed pyicloud session, a transient network error, or any other backend
failure) left state - and therefore the control - completely unchanged,
with the rejection going nowhere but the browser console. From the user's
side this reads as "nothing happens when I click it," indistinguishable
from the feature being broken outright, even though the click was in fact
sent and failed for a real (and previously invisible) reason.

- [x] `OwnerDevicesPanel.tsx`: wrapped both `toggle()` and `togglePrimary()`
      bodies in `try`/`catch`, showing `alert('Ändern fehlgeschlagen: ' +
      err.message)` on failure - the same pattern `AirtagDetail.tsx`'s
      `KeyForm.handleSave()` already uses for a single row-level action
      failing, rather than adding a new persistent error-banner state like
      v20's list-level fix (there's no natural place to anchor a banner to
      one specific row's toggle, and a one-off alert is enough to stop the
      click from looking like it did nothing).

## Review (v22)
- 1 file touched, no new dependencies, no backend change (the enable/
  primary routes are plain DB writes with no live Apple call, so they
  don't share v20's "uncaught 500 from Apple" failure mode specifically -
  but any failure there, DB or otherwise, was equally silent before this
  fix).
- Verified: `pytest tests/` - 52 passed, 21 skipped (Postgres-dependent, no
  live Postgres in this sandbox) - unchanged, since this fix touches no
  Python. `cd frontend && npx tsc -b && npx vite build` clean; `npx oxlint`
  shows only the same three pre-existing `set-state-in-effect` warnings
  from v13/v14/v16/v17/v18, no new ones. `docker compose config` parses
  cleanly with a throwaway `.env`.
- Not verified in this sandbox (no real owner-tracking Apple session): the
  actual failing request the reporting user hit. The fix addresses the
  general defect - any failure in these two calls was silently swallowed -
  rather than one specific underlying cause, since none could be
  reproduced here; worth confirming with the user whether the alert now
  appears (and what it says) the next time a check/favorite click doesn't
  take effect. No frontend test added - this repo has no frontend test
  harness yet (no `.test.`/`.spec.` files anywhere under `frontend/`), and
  standing one up for a two-branch `try`/`catch` would be disproportionate;
  covered instead by the build/lint verification above plus manual code
  review against the working `KeyForm` precedent.

## v23: Fix 405 on owner-device routes for ids containing "/"

Trigger: v22's alert() surfaced what v20/v22 previously hid - a real
405 Method Not Allowed on `PUT /api/owner-devices/{id}/primary` for a
specific device. The id in question was a base64-ish blob (Apple's own
`AppleDevice.id` from pyicloud, not something this app generates) that
legitimately contains a `/`, e.g. `AYPw...cDrA/XrQD...3bA==`.

`frontend/src/api.ts` already `encodeURIComponent()`-ed the id before
building the URL, so the browser sent `%2F` correctly - but that alone
isn't enough. Percent-encoded slashes inside a URL *path segment* are not
reliably preserved end-to-end: ASGI (uvicorn/Starlette) decodes the
entire raw request target - `%2F` included - into `scope["path"]` before
routing ever runs, and the same is true of common reverse
proxies/dev-server proxies. That silently splits what should be one
`{device_id}` path segment into two, so `PUT /api/owner-devices/{id}/primary`
no longer matches - and because the split path happened to still match
some *other* registered route by segment count, FastAPI returned 405
(wrong method for that route) rather than a more diagnosable 404. `+` and
`=` in the same id "worked" only because decoding them back to literal
characters doesn't introduce a new `/` delimiter - the bug was specific to
ids containing an actual slash.

The only sound fix is to stop putting this opaque id where `/` can act as
a delimiter at all - not to chase encoding differences across whatever
ASGI/proxy layers happen to be in front of the app, since that's out of
this codebase's control at every layer.

- [x] `web/app.py`: `PUT /api/owner-devices/{device_id}` →
      `PUT /api/owner-devices` with `device_id` added to
      `OwnerDeviceEnabledIn`'s body. `PUT /api/owner-devices/{device_id}/primary`
      → `PUT /api/owner-devices/primary` with a new `OwnerDevicePrimaryIn`
      body (`device_id` only) - coexists fine with the existing
      `DELETE /api/owner-devices/primary`, different HTTP method on the
      same static path. `GET /api/owner-devices/{device_id}/history` →
      `GET /api/owner-devices/history` with `device_id` as a query param -
      query-string parsing splits only on `&`/`=`, never `/`, so this is
      immune to the same problem regardless of what decodes it downstream.
- [x] `api.ts`: the three matching client functions updated to match -
      `device_id` moved into the JSON body for both PUT calls, and into a
      `URLSearchParams`-equivalent query string (still `encodeURIComponent`-ed,
      since `+`/`&`/`=` are still meaningful in a query string) for the
      history GET.
- [x] `test_web_auth.py`: new
      `test_owner_device_routes_accept_ids_containing_a_slash`, exercising
      all three routes with a real slash-containing id and asserting each
      one reaches the underlying `owner_tracking`/`db` call with the id
      intact (200, not 404/405).

## Review (v23)
- 3 files touched (1 backend, 1 frontend, 1 test), no new dependencies, no
  migration (no schema/storage change - `owner_devices.id` was always
  stored as-is, only how it traveled in a request URL changes).
- Verified: `pytest tests/` - 53 passed (52 prior + the new regression
  test), 21 skipped (Postgres-dependent, no live Postgres in this
  sandbox). `cd frontend && npx tsc -b && npx vite build` clean; `npx
  oxlint` shows only the same three pre-existing `set-state-in-effect`
  warnings, no new ones. `docker compose config` parses cleanly with a
  throwaway `.env`.
- Not verified in this sandbox (no real owner-tracking Apple session):
  that the specific device id the user hit actually round-trips against
  a live Apple account end-to-end now - the regression test proves the
  routes accept and forward a slash-containing id correctly, but the
  original report was diagnosed from a raw request line, not reproduced
  against a real pyicloud session here.

## v24: Fix owner devices never getting a location; unify them into Objekte

Trigger: real-user report - "no location is present" for tracked owner
devices, plus "few to no logging" in the backend to debug it with. Also
folded in three UI requirements: every tracked device should appear in the
main list (not just Settings), grouped separately from AirTags; a device's
history should only render there, once selected, not in Settings; and
polling/persisting cadence should match AirTags (already true - see below).

Root cause, confirmed by installing the real `pyicloud==2.7.0` package in a
scratch venv and reading `services/findmyiphone.py` directly rather than
guessing: `owner_tracking._build_api()` builds a fresh `PyiCloudService`
every poll, and the very *first* `.devices` access only ever performs
Apple's `initClient` call. The block in `_refresh_client()` that sets
`isUpdatingAllLocations`/`shouldLocate`/`selectedDevice` - i.e. the part
that actually asks Apple to locate the devices - is gated behind
`if self._server_ctx:`, which is `None` on that first call and therefore
unreachable. Since this app never touches `.devices` a second time before
killing the background monitor thread (the v18 fix for a real thread
leak, which must stay), it has only ever sent the identity-only call -
`location`/`location_available` reflected whatever Apple happened to have
cached, often nothing. `FindMyiPhoneServiceManager.refresh(locate=True)` is
the library's own public method for forcing that second, locate-flagged
round trip once a `_server_ctx` exists (it does, right after the first
access) - the fix is one explicit call to it.

Separately, `tracker.py::poll_once` already calls `_update_owner_devices()`
in the same per-cycle sweep as the AirTag polling loop, both driven by
`scheduler.py`'s one `polling_interval_minutes` - so the interval
requirement was already met; it just had nothing to persist.

- [x] `owner_tracking.py`: `_snapshot_devices()` now calls
      `api.devices.refresh(locate=True)` before reading any device's
      location, with a docstring addition explaining why the constructor's
      own implicit first call can't do this. Added `logger.info`/`.debug`
      throughout (`_connect`, `_snapshot_devices`, `list_owner_devices`,
      `fetch_owner_device_locations`) - device counts, enabled-device
      counts, and per-device *why* a location is missing (feature flag vs.
      missing content key) - this module had almost no logging before,
      unlike `tracker.py`'s AirTag path.
- [x] Frontend: `AirtagList.tsx` renamed `ObjectsList.tsx` - now renders
      two labeled groups, "Geräte" (every *enabled* owner device, primary
      one star-badged, tapping selects it) above "AirTags" (unchanged).
      Replaces the old single hardcoded "Du" summary row entirely - the
      primary device is now just the badged row within "Geräte". New
      `DeviceDetail.tsx` (mirrors `AirtagDetail.tsx`, trimmed to a header
      + an expandable "Verlauf" list - device identity/enable/primary
      stay Settings-only) and `DeviceMapCard.tsx` (mirrors `MapCard.tsx`
      for one device's trail, reusing its exported `FitBounds`/
      `InvalidateSizeOnResize`/`NoReportsView`/`currentLocationIcon`
      rather than duplicating them). `OwnerDevicesPanel.tsx` (Settings ->
      Eigene Geräte) dropped its "Verlauf" row/state entirely - Settings
      now only manages which devices are enabled/primary.
      `App.tsx` now also fetches `getOwnerDevices()` (previously only
      `getOwnerDeviceLocations()`, which omits an enabled device with no
      recorded fix yet - a real visibility gap in its own right, now
      fixed) and generalizes `showDetail: boolean` into
      `detail: 'airtag' | 'device' | null` plus `selectedDeviceId` to
      route the map pane and sheet content to either detail view.
      No backend route changes needed - `getOwnerDevices`,
      `getOwnerDeviceLocations`, and `getOwnerDeviceHistory` already
      covered everything the new UI needs.
- [x] `test_owner_tracking.py`: `_FakeDeviceList` gained a `refresh()`
      recording its calls; new
      `test_snapshot_devices_forces_a_live_locate_before_reading_locations`
      asserts `_snapshot_devices` calls it with `locate=True`.

## Review (v24)
- 8 files touched (1 backend, 1 test, 6 frontend: 1 renamed, 2 new, 3
  edited), no new dependencies, no migration.
- Verified: installed `pyicloud==2.7.0` for real in a scratch venv and read
  its `findmyiphone.py` directly to confirm the `_server_ctx` gating claim
  above, rather than guessing at the fix. `pytest tests/` - 54 passed (53
  prior + the new `refresh(locate=True)` regression test), 21 skipped
  (Postgres-dependent, no live Postgres in this sandbox); confirmed via
  `git stash` that a pre-existing, unrelated fixture conflict between
  `test_app_shell_is_never_cached` and `test_fingerprinted_asset_is_cached_immutably`
  in this same sandbox (this repo's checked-in `web/static/icons/` means
  `test_web_auth.py`'s "stand in a placeholder index.html if absent"
  fixture never triggers, so one or the other fails depending on whether a
  real frontend build happened to run first) reproduces identically on
  the unmodified repo - unrelated to this change, not fixed here. `cd
  frontend && npx tsc -b && npx vite build` clean; `npx oxlint` shows only
  the same three pre-existing `set-state-in-effect` warnings, no new ones.
  `docker compose config` parses cleanly with a throwaway `.env`.
- Not verified in this sandbox (no real owner-tracking Apple account, same
  standing limitation as every prior owner-tracking entry): that the
  `refresh(locate=True)` fix actually produces a location end-to-end
  against a live account. The fix is grounded in reading the real
  installed library's source rather than speculation, and the new
  `_snapshot_devices` debug logging (`docker logs app` after a poll, once
  deployed) will show exactly what Apple returned per device
  (`location_available` plus, when false, whether the `LOC` feature flag
  or the `location` content key itself was missing) if it's still empty -
  that's the next diagnostic step if this alone doesn't fully resolve it.
  The new grouped Objekte list and DeviceDetail's map trail/history also
  need a real-account visual check.

## v25: Remove ntfy.sh notifier

Trigger: user request - drop the ntfy.sh backend entirely; Telegram and Web
Push already cover the same "push a movement alert somewhere" need without
a third-party relay topic to keep secret.

- [x] Deleted `airtag_sentry/notifiers/ntfy.py` and its `NtfyNotifier`
      class/test (`test_notifiers.py`).
- [x] `notifiers/__init__.py`'s `build_notifiers()` no longer imports or
      instantiates it.
- [x] `config.py`: dropped `NtfyConfig`, the `notifications.ntfy` field, and
      `NTFY_TOPIC_URL` env var parsing; the "no notifier configured" startup
      warning now only mentions Web Push/Telegram.
- [x] Dropped `NTFY_TOPIC_URL` from `docker-compose.yml` (both `app` and
      `dashboard` services), `.env.example`, and the README's notifiers
      table.
- [x] `tasks/roadmap.md`'s per-AirTag routing item updated to drop the
      now-gone backend from its notifier list.

## Review (v25)

- 7 files touched (2 backend, 1 deleted, 1 test, 3 docs/config), no new
  dependencies, no migration - a pure removal, no compat shim per this
  repo's established "no backward-compatibility shims" convention. Anyone
  with `NTFY_TOPIC_URL` still set in their `.env` just has it silently
  ignored, same treatment prior config-shape breaks in this changelog got.
- Verified: `pytest tests/` and `ruff`/type-checks pass with no leftover
  `ntfy` references; grepped the full repo (case-insensitive) for `ntfy`
  and confirmed only this changelog entry and the historical v21/pre-v21
  entries above (left as the historical record, not rewritten) still
  mention it.

## v26: Fix `ModuleNotFoundError: No module named 'cryptography'` in Getting Started

Trigger: real-user report - running the first commands in README's "Getting
started -> 1. Configure secrets" (`python -c "from cryptography.fernet
import Fernet..."` and `python scripts/generate_vapid_keys.py`) on a bare
host Python fails with `ModuleNotFoundError: No module named 'cryptography'`.

Root cause: not a missing dependency in the project itself -
`cryptography>=42` is already declared in `pyproject.toml` and `py-vapid` is
what `scripts/generate_vapid_keys.py` imports as `py_vapid`. The bug is in
the README's ordering: step 1 is the very first thing a new self-hoster
runs, on their host Python, before `docker compose up` even exists as an
option - but the only "install the project's Python deps" instruction
(`pip install -e ".[dev]"`) appears much later, under "## Development",
which a reader following the guide top-to-bottom hasn't reached yet. Anyone
without a pre-existing venv from unrelated project work hits this on the
very first command.

- [x] README: "1. Configure secrets" now installs `cryptography` and
      `py-vapid` (just the two packages those two commands need, not the
      full `.[dev]` extra with `pyicloud`/`findmy`/pytest, which are
      unrelated at this point and heavier) before the two key-generation
      commands.

## Review (v26)
- 1 file touched (README.md), no code/dependency/migration changes - the
  dependency was already correctly declared, only the setup doc was wrong.
- Verified: reproduced the exact reported traceback in a fresh venv with no
  packages installed; then followed the corrected README instructions
  verbatim (`pip install cryptography py-vapid` only) in a fresh venv and
  confirmed `python scripts/generate_vapid_keys.py` succeeds and prints
  `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY`/`VAPID_SUBJECT` as expected.

## v27: Inbound Telegram bot commands (/list, /where)

Trigger: the Telegram integration was outbound-only (movement alerts via
`notifiers/telegram.py`'s `sendMessage`) - user wanted to be able to *ask*
the bot for its tracked AirTags and their locations instead. Two explicit
requirements: `/list` so the user never has to remember AirTag names/ids,
and any device-taking command falls back to a two-step inline-keyboard
picker when the name is omitted rather than erroring.

- [x] New Alembic migration (`9d21b6f4a7c3`, `down_revision = f3a4c8e1d9b2`):
      `telegram_settings` gains `bot_commands_enabled BOOLEAN` and
      `webhook_secret TEXT` - the anti-spoofing token handed to Telegram's
      `setWebhook`, stored in plaintext (not user secret material, unlike
      `bot_token_encrypted`).
- [x] `db.py`: `TelegramCredentials` gained those two fields;
      `set_telegram_credentials` now also resets them on reconnect (a new
      bot token invalidates any webhook registered against the old one);
      new `set_telegram_bot_commands(conn, enabled, webhook_secret)`.
- [x] New `airtag_sentry/telegram_bot.py`: the inbound counterpart to
      `notifiers/telegram.py`. `handle_update()` routes `/help`, `/list`,
      `/where [name]` and `callback_query` picker selections. Every reply
      path is gated on the update's `chat.id` matching the one configured
      `chat_id` *before* touching any data - a stranger who finds/adds the
      bot elsewhere gets silence, not even a response that would confirm
      the bot exists. `/where` with no arg (or an ambiguous name) sends an
      inline keyboard built from `list_airtags()`'s order; the tap comes
      back as a `callback_query` with `callback_data="where:<index>"` -
      Telegram's own round-trip *is* the two-step state, no server-side
      "pending command" table needed.
- [x] `web/app.py`: `/api/telegram/webhook` (public - Telegram can't send
      the session cookie, so it authenticates itself via
      `X-Telegram-Bot-Api-Secret-Token` compared with `secrets.compare_digest`
      against the stored secret) plus `POST`/`DELETE
      /api/notifications/telegram/commands` to enable/disable it. The
      webhook URL is derived from the enabling request's own
      `request.base_url`, not a new config value - `cli.py`'s `serve`
      already runs uvicorn with `proxy_headers=True`, so it already
      reflects the public host behind Coolify's edge TLS. Disabling
      Telegram entirely (`telegram_disconnect`) now also tears down the
      webhook if one was registered.
- [x] Frontend: `TelegramPanel.tsx` gained an "Aktivieren/Deaktivieren"
      toggle for bot commands once connected; `api.ts` gained
      `enableTelegramCommands`/`disableTelegramCommands` and
      `TelegramStatus.bot_commands_enabled`.
- [x] Tests: `test_db.py` extended the Telegram round-trip test and added
      `test_telegram_bot_commands_set_round_trip` (including the
      reconnect-resets-state case). New `test_telegram_bot.py` unit-tests
      `handle_update`'s routing, name matching, the picker, callback-query
      resolution, and the unauthorized-chat-id silence, all via mocked
      `requests.post` (no real Telegram API calls).

Deliberately deferred: `/status` and `/alerts` (more read-only commands),
and `/mute`/`unmute` (snoozing alerts needs to be checked inside the shared
`notify_all()` pipeline in `tracker.py`, not just the Telegram bot, so it
would also silence web push - a separate change).

## Review (v27)
- 8 files touched (4 backend + 1 migration, 2 frontend, 2 tests), no new
  dependencies.
- Verified: started a local Postgres 16 in this sandbox (no Docker daemon
  available here), created `airtag_sentry`/`airtag_sentry_test`, ran the
  full suite in a scratch venv - `pytest`: 83 passed (81 prior + 2 new
  `test_db.py` cases), including the new `test_telegram_bot.py` (7 tests)
  and `test_web_auth.py` (exercises the full `web/app.py` import, so the
  new routes/imports are at least import-clean). `cd frontend && npx tsc -b
  && npx vite build` clean; `npx oxlint` shows the same three pre-existing
  `set-state-in-effect` warnings, none new. `docker compose config` parses
  cleanly with a throwaway `.env` containing no new env vars (by design -
  the webhook URL comes from the request, not config).
- Not verified: an actual Telegram bot end-to-end (no bot token available
  in this sandbox) - registering a real webhook via `setWebhook`, and then
  a real `/list`/`/where` round trip including tapping an inline-keyboard
  button, needs a live bot token + chat and a publicly reachable deployment
  to test against. Do that smoke test before relying on this in production.

## v28: Merge `app` service into `dashboard` (one container for poller + web)

Trigger: user request - two containers doing nothing but talking through
Postgres was unnecessary operational overhead (two things to deploy/watch
in Coolify), and it meant only `dashboard` had a Docker healthcheck since
`app`'s scheduler loop had no HTTP surface to probe.

- [x] `scheduler.py`: `run_forever()` (blocking, its own process) replaced
      with `start_scheduler(cfg)`, which uses APScheduler's
      `BackgroundScheduler` (own worker thread, non-blocking) and returns
      the scheduler instance instead of running forever.
- [x] `web/app.py`: `create_app()` now takes a `lifespan` hook that calls
      `start_scheduler(cfg)` on startup and `scheduler.shutdown(wait=False)`
      on shutdown - the poller and the dashboard are now one process, still
      only talking to each other through Postgres (`get_conn()` opens a
      fresh connection per call already, so no new concurrency handling
      needed between the scheduler thread and request-handling threads).
      The first poll is scheduled for "now" via `add_job` rather than run
      inline, so `/health` isn't blocked behind an Apple round-trip at
      startup.
- [x] `cli.py`: dropped the `run` subcommand entirely (no compat shim, per
      this repo's established convention) - `poll`/`serve` remain, `serve`
      now implicitly starts the poller too.
- [x] `Dockerfile`: default `CMD` changed from `["run"]` to `["serve"]`.
- [x] `docker-compose.yml`: deleted the `app` service; merged its
      `anisette` dependency and `ANISETTE_MODE`/`ANISETTE_REMOTE_URL` env
      vars into `dashboard`. Kept the service name `dashboard` (not `app`)
      and the `app_data` volume name unchanged, since Coolify's
      `SERVICE_FQDN_DASHBOARD_8000` and the persisted volume both key off
      those names - renaming either would cost the user their live
      deployment's public domain/TLS binding or (for the volume) their
      persisted Apple session data for no functional reason.
- [x] `README.md`, `CLAUDE.md`, `.env.example`: updated every place
      describing the two-service split (services table, CLI reference,
      Coolify section, migrations section, project-shape doc) to describe
      one `dashboard` service that runs both roles.

## Review (v28)

- 8 files touched (3 backend, 1 Dockerfile, 1 compose, 3 docs/config), no
  new dependencies (`apscheduler`'s `BackgroundScheduler` ships in the same
  `apscheduler>=3.10` already installed), no migration - a pure
  process/deployment topology change. No compat shim for the removed `run`
  command, per this repo's established "no backward-compatibility shims"
  convention - anyone with a script or Coolify config still invoking
  `python -m airtag_sentry run` needs to switch to `serve`.
- Verified: started a local Postgres and ran the full suite for real -
  `pytest -q` → 74 passed, 0 skipped (this sandbox normally has no
  Postgres, so DB-dependent tests usually skip; started one for this
  change specifically since it touches `create_app()`'s startup path).
  Confirmed none of the existing tests trigger the new lifespan hook at
  all (`TestClient(app_module.create_app(cfg), ...)` is never used as a
  context manager in this codebase, so ASGI lifespan/startup never runs
  during those HTTP-route tests - ruled out by reading `tests/test_web_auth.py`
  before assuming it was safe).
  Additionally wrote a standalone script exercising `create_app()` inside
  `with TestClient(app) as client:` (the one thing no existing test does)
  against the same local Postgres: confirmed `/health` returns 200
  immediately without waiting on a poll, and the scheduler shuts down
  cleanly on exit with no dangling thread errors.
  `docker compose config` (throwaway `.env`) parses cleanly and lists only
  `postgres`, `anisette`, `dashboard` - no `app`.
- Not re-run: frontend `tsc`/`vite build`/`oxlint` - this change touches no
  frontend code, so nothing there could have regressed. Re-run after
  merging in v27's Telegram changes: still nothing to verify there, since
  this merge touches no frontend code either.

## v29: Fix owner-device polling silently blocked by a missing AirTag session

- [x] `tracker.py`: `poll_once()` used to call `restore_account(cfg)` (the
      AirTag-tracking Apple session) as its very first line, before even
      opening a DB connection. If the AirTag session had never been
      connected (e.g. a user who only ever connected owner tracking from
      Settings ⚙️ → Apple-Konten), this raised `FileNotFoundError`
      immediately and aborted the whole poll - so `_update_owner_devices()`
      never ran and owner-device locations were never historized, even
      though `owner_tracking.py`'s own module docstring says it's "entirely
      optional" and independent of AirTag tracking. Reordered `poll_once()`
      to open the DB connection and run `_update_owner_devices()`
      unconditionally first, then check `auth.is_connected(cfg)` (already
      used by `/api/apple/status`) before restoring the AirTag session and
      polling AirTags - skipping with an `INFO` log instead of raising when
      no AirTag session exists yet. Also fixes noisy `ERROR [scheduler] Poll
      failed` log spam on every poll cycle for a user who hasn't connected
      AirTag tracking yet, since that's an expected "not configured" state,
      not a real failure.

## Review (v29)

- 1 file touched in `airtag_sentry/` (`tracker.py`), 1 new test file
  (`tests/test_tracker.py`), no migration, no frontend changes, no new
  dependencies - a pure control-flow fix.
- Root cause confirmed by reading the reported log: `POST
  /api/apple/owner/login` succeeded, but every subsequent poll still logged
  `FileNotFoundError: No saved Apple session at data/account.json` -
  the AirTag-tracking store path, not the owner-tracking one - because
  `poll_once()` never got past `restore_account()` regardless of what
  owner tracking was doing.
- Verified: wrote `tests/test_tracker.py` with a regression test that
  monkeypatches `restore_account`/`list_airtags` to raise if called, and
  asserts `_update_owner_devices()` still runs when `is_connected(cfg)` is
  `False`. Confirmed the test fails against the pre-fix code (`git stash`
  reproduces the exact bug: `is_connected` doesn't even exist as a name
  in the unpatched `tracker.py`, since it never checked it) and passes
  after the fix. Started a local Postgres and ran the full suite for
  real: `pytest` → 83 passed, 0 skipped. `docker compose config`
  (throwaway `.env`) parses cleanly.

## v30: Grouped Settings sub-panels, real toggle switches, push notifications now off-able

Trigger: `SettingsPanel.tsx` had grown into one long flat scroll - Darstellung,
Benachrichtigungen, Apple-Konten, Eigene Geräte, Abfrage, Bewegungserkennung,
Standort-Korrelation, Abmelden, eight sections stacked vertically. User asked
for Apple-typical grouped sub-menus instead, and called out a real bug while
at it: push notifications had no off switch. `usePushNotifications.ts` only
ever exposed `enable()`; the backend's `/api/push/unsubscribe` route
(`app.py`) already worked but nothing on the frontend called it, and `status`
always reset to `'idle'` on every reload regardless of whether a subscription
actually existed.

- [x] `SettingsPanel.tsx` rewritten as a small in-place router (`page: 'root'
      | 'notifications' | 'apple' | 'tracking'`, no URL/route change - same
      pattern `AirtagDetail.tsx` already uses for its own back-navigation).
      Root menu is now just: Erscheinungsbild (unchanged inline control) +
      one grouped `Section` of three nav rows (Benachrichtigungen,
      Apple-Konten, Tracking) + Abmelden - matching Apple's own short
      top-level Settings list that drills into dedicated screens.
- [x] Three new sub-screens, each with a `BackHeader` (reuses
      `AirtagDetail.tsx`'s existing chevron-back pattern): moved verbatim
      out of `SettingsPanel.tsx` - `SettingsNotifications.tsx` (push row +
      `TelegramPanel`), `SettingsAppleAccounts.tsx` (both
      `AppleConnectPanel`s + `OwnerDevicesPanel`), `SettingsTracking.tsx`
      (Abfrage/Bewegungserkennung/Standort-Korrelation, still owns nothing -
      `settings`/`errors`/`update` stay lifted in `SettingsPanel.tsx` and
      flow down as props, same as before).
- [x] New `Switch` component (`AirtagDetail.tsx`, alongside the existing
      `Section`/`Row` primitives): standard iOS pill switch,
      `role="switch"`/`aria-checked`, green when on. Replaces, one for one:
      the `movement_alert_on_backfill` checkbox, `OwnerDevicesPanel`'s
      per-device enable checkbox, and `TelegramPanel`'s Aktivieren/
      Deaktivieren pill button for bot commands. ("Trennen"/disconnect stays
      a plain button - it's an action, not a boolean state.)
- [x] Push notifications actually toggleable now:
      `usePushNotifications.ts` checks for an existing subscription on
      mount (`pushManager.getSubscription()`) instead of always starting
      `'idle'`; added `disable()` (calls the new `unsubscribePush()` in
      `api.ts`, then the browser-side `subscription.unsubscribe()`); added
      a `busy` flag so the switch can't be double-fired mid-flight. The
      push row in `SettingsNotifications.tsx` is now a real two-way
      `Switch` instead of a one-way "Aktivieren" button.

## Review (v30)
- 10 files touched (7 frontend components/hooks/api, 1 changelog), no
  backend changes - `/api/push/unsubscribe` already existed and needed no
  modification, no new dependencies.
- Verified: `cd frontend && npm install && npx tsc -b && npx vite build`
  clean; `npx oxlint` shows the same three pre-existing `set-state-in-effect`
  warnings in `App.tsx`, none new (confirmed via `git diff --stat` that
  those lines aren't part of this change). Started a local Postgres 16 in
  this sandbox, created `airtag_sentry`/`airtag_sentry_test`, ran the full
  suite in a scratch venv - `pytest`: 81 passed, 22 skipped (live
  Apple/owner-tracking tests needing real credentials, as documented
  elsewhere in this file), 1 failed
  (`test_fingerprinted_asset_is_cached_immutably`) - pre-existing and
  unrelated to this change: it assumes `airtag_sentry/web/static/assets/`
  (gitignored, normally empty) starts empty, which it wasn't after running
  `vite build` for this same verification pass. `docker compose config`
  parses cleanly with a throwaway `.env`.
- Not verified in a real browser: this app has no dev-mode auth bypass -
  every dashboard route requires a real GitHub OAuth login - so a full
  logged-in click-through (navigate root → each sub-screen → back, flip
  every new `Switch`) couldn't be done in this sandbox. User confirmed
  `tsc`/`build`/`lint`/`pytest` were sufficient for this change. Click
  through the new Settings screens and toggles once in a real browser
  before relying on this.

## v31: Owner devices reach parity with AirTags (Telegram /list, rename/icon, map)

Three bugs reported together, all rooted in owner devices (`owner_tracking.py`
/ `owner_devices` table - the owner's own Apple devices via `pyicloud`,
tracked separately from AirTags) never having gotten the same treatment
AirTags already had:

- [x] `telegram_bot.py`: `/list` only ever queried `list_airtags` - it was
      written before owner-device tracking existed and never got extended.
      Now fetches enabled owner devices too and lists them first, in their
      own "Deine Geräte" section (⭐ for the primary one) ahead of "Deine
      AirTags" - matching the dashboard's `ObjectsList.tsx`, which already
      groups them the same way. `/where` and the callback-query picker stay
      AirTag-only (out of scope - devices have no "where" concept there).
- [x] New migration `d4f19a6e3b2c` (revises `9d21b6f4a7c3`): adds nullable
      `display_name`/`icon`/`color` to `owner_devices`, mirroring
      `8a7b73c5121e`'s AirTag appearance columns. The real fix here is
      `display_name`: `owner_devices.name` is the Apple-synced *technical*
      name, silently overwritten by `upsert_owner_devices` on every live
      device listing - a plain rename onto that column would've been
      clobbered on the next dashboard load. `display_name` is a separate,
      app-owned column `upsert_owner_devices` never touches, so a user's
      chosen name survives every refresh; `None` falls back to showing the
      technical name (`deviceLabel()` in `format.ts`).
      `db.py`: `OwnerDevice` gained the three fields; new
      `rename_owner_device`/`set_owner_device_appearance` (mirroring
      `rename_airtag`/`set_airtag_appearance` exactly); `owner_tracking.py`
      got thin `rename_device`/`set_device_appearance` wrappers alongside
      its existing `set_device_enabled`/`set_device_primary`; `web/app.py`
      got `PATCH /api/owner-devices/rename` and `.../appearance` (device_id
      in the body, not the URL path, like the existing enabled/primary
      routes - Apple device ids can contain `/`). `DeviceDetail.tsx` gained
      "Umbenennen"/"Symbol & Farbe" sections copied from `AirtagDetail.tsx`
      (new `DeviceAvatar.tsx` mirrors `AirtagAvatar.tsx`); `ObjectsList.tsx`
      and every device name/pin (`DeviceMapCard.tsx`, `OverviewMap.tsx`,
      `MapCard.tsx`) now show the display name and the chosen icon/color
      (`airtagPinIcon`, already generic over `{id, icon, color}`, reused
      as-is for device pins instead of the plain "you are here" dot).
- [x] `DeviceMapCard.tsx` picked `positions[positions.length - 1]` as a
      device's current position, copied from `MapCard.tsx`'s AirTag logic -
      but `/api/owner-devices/history` is documented and tested
      (`fetch_owner_device_location_history`) to return **newest-first**,
      unlike AirTag reports (`fetch_reports`, oldest-first). This picked the
      *oldest* kept fix as "current", placing the marker at a stale spot -
      `DeviceDetail.tsx`'s own history list already `.reverse()`d for this,
      the map card just never did. Fixed to `positions[0]`. Also:
      `OverviewMap.tsx`'s empty-state guard checked only AirTag reports,
      hiding every device pin outright on a device-only setup or before any
      AirTag had reported yet - now guards on AirTags *and* device
      locations together, and includes device positions when centering/
      fitting the map. Device popups on `OverviewMap.tsx`/`MapCard.tsx` were
      also read-only (name + time); added the same "Details anzeigen"
      drill-in button AirTag popups have, wired to a new `onSelectDevice`
      prop from `App.tsx`.

## Review (v31)

- Backend: `telegram_bot.py`, `db.py`, `owner_tracking.py`, `web/app.py`, 1
  new migration. Frontend: `api.ts`, `format.ts`, `App.tsx`,
  `DeviceDetail.tsx`, `ObjectsList.tsx`, `DeviceMapCard.tsx`,
  `OverviewMap.tsx`, `MapCard.tsx`, new `DeviceAvatar.tsx`. No CLI changes
  (nothing here needed one - all of it was already reachable from the
  dashboard/bot).
- Root cause of the map bug confirmed by reading
  `fetch_owner_device_location_history`'s own docstring/test
  (`test_fetch_owner_device_location_history_returns_newest_first_and_respects_limit`
  in `test_db.py`) against `DeviceMapCard.tsx`'s `positions[length - 1]` -
  a straight ordering-assumption mismatch, not a data problem.
- Verified: added `test_db.py` cases for `rename_owner_device`,
  `set_owner_device_appearance`, and a dedicated
  `test_reupsert_does_not_clobber_display_name_or_appearance` proving a
  live Apple refresh leaves a user's rename/appearance alone; added
  `test_telegram_bot.py::test_list_command_shows_devices_before_airtags`.
  Started a local Postgres, applied the new migration, ran the full suite
  for real: `pytest` → 89 passed, 0 skipped. `cd frontend && npx tsc -b &&
  npx vite build && npx oxlint` clean (pre-existing `App.tsx` set-state-in-
  effect warnings only, unchanged by this diff). `docker compose config`
  (throwaway `.env`) parses cleanly.

## v32: Map/history navigation - jump-to-entry, prev/next trail stepping, address lookup

- [x] `App.tsx` gained a lifted `selectedReportId` (reset whenever the
      current AirTag's `reports` reload), passed into both `MapCard.tsx` and
      `AirtagDetail.tsx` - the two were previously independent siblings with
      no shared selection concept (`onSelectDevice` was the closest existing
      precedent, but that jumps *between devices*, not within one trail).
- [x] `AirtagDetail.tsx`'s `HistoryList` rows are now buttons: clicking one
      sets `selectedReportId`, highlighting the row (`bg-[var(--accent)]/15`,
      matching `ObjectsList.tsx`'s existing selected-row style) and moving
      the map marker to it. Rows were already newest-first (`reports`
      arrives oldest-first from `fetch_reports`, reversed for display) - no
      change needed there.
- [x] `MapCard.tsx`: the AirTag's single marker now sits on the selected
      report (falling back to the latest, unchanged default), panning to it
      via a new `PanToSelection` helper (separate from `FitBounds`, which
      only reframes the whole trail when the report list itself changes)
      and auto-opening its popup via a `markerRef`. The popup gained an
      absolute timestamp (`toLocaleString()`, matching `HistoryList`'s own
      formatting) and Previous/Next ("Älter"/"Neuer") buttons that step
      through `reports` by index, disabled at the trail's ends - the same
      `onSelectReport` callback drives both list-click and popup-button
      selection.
- [x] New `airtag_sentry/geocode.py`: best-effort reverse geocoding via OSM
      Nominatim (no separate API key needed - same OSM data already backing
      the map tiles), rate-limited to Nominatim's 1 req/s policy and cached
      in-process by rounded lat/lon (not persisted - a display nicety, not
      data worth a migration/table for). Never raises; a failed lookup just
      means no address line. New `GET /api/geocode?lat=&lon=` route;
      frontend `getAddress()` + `MapCard.tsx`'s `AddressLine` (own
      loading/cache state, renders nothing until/unless a result lands).

## Review (v32)

- Backend: new `airtag_sentry/geocode.py`, one new route in `web/app.py`.
  Frontend: `api.ts`, `App.tsx`, `AirtagDetail.tsx`, `MapCard.tsx`. No CLI
  or schema changes - this is a session-scoped UI/API addition, nothing
  persisted.
- Verified: new `tests/test_geocode.py` (4 cases: address returned, cache
  hit by rounded coordinates, network failure → `None`, missing
  `display_name` → `None`) via `pytest tests/test_geocode.py` - all pass.
  Full `pytest` against a real Postgres and `docker compose config` with a
  throwaway `.env` weren't runnable in this sandbox (no Docker daemon
  available here); ran the DB-independent suites
  (`test_movement.py`/`test_config.py`/`test_keystore.py`) and a plain
  `from airtag_sentry.web.app import create_app` import check instead, both
  clean. `docker compose config` (throwaway `.env`, syntax-only - doesn't
  need the daemon) parses cleanly. `cd frontend && npx tsc -b && npx vite
  build && npx oxlint` clean (same pre-existing `App.tsx` set-state-in-
  effect warnings as v31, plus one new one of the same class in
  `MapCard.tsx`'s `AddressLine` - consistent with the rest of the codebase,
  not a new warning category).

## v33: Extend v32's map navigation to owner devices; CLAUDE.md parity rule

v32 shipped jump-to-entry/marker-selection/timestamp/address/prev-next only
for AirTags - `DeviceDetail.tsx`/`DeviceMapCard.tsx` (the owner-device
counterparts) didn't get it, breaking the parity the dashboard otherwise
maintains between the two object types (see v31). Brought them up to the
same feature set, and added a hard-constraint section to CLAUDE.md so this
doesn't happen a third time.

- [x] `MapCard.tsx`'s `PanToSelection` and `AddressLine` are now exported
      (were previously module-private) so `DeviceMapCard.tsx` can reuse them
      instead of duplicating - matches how it already reuses `FitBounds`/
      `InvalidateSizeOnResize`/`NoReportsView` from the same file.
- [x] `DeviceMapCard.tsx` gained the same `selectedLocationKey`/
      `onSelectLocation` selection props as `MapCard.tsx`'s
      `selectedReportId`/`onSelectReport`, with the same marker-follows-
      selection, pan-on-select, popup-timestamp/address, and Previous/Next
      behavior. Selection is keyed by `recorded_at` (a stable string),
      not a numeric id - `OwnerLocation` has none in the API response,
      and `DeviceHistoryList` already used `recorded_at` as its row key.
      `/api/owner-devices/history` is newest-first (unlike AirTag reports),
      so "older"/"newer" step in the *opposite* array-index direction from
      `MapCard.tsx` - documented inline to head off re-introducing the same
      inverted-index bug the next section describes.
- [x] Fixed a pre-existing ordering bug found while doing this:
      `DeviceHistoryList` did `[...history].reverse()`, but `history` is
      already newest-first from the backend - the reverse silently flipped
      it to oldest-first, the wrong direction, unnoticed because nothing
      compared it against `AirtagDetail.tsx`'s `HistoryList` (correctly
      newest-first) side by side until now. Removed the reverse; rows are
      also now buttons (`onSelectLocation`), highlighted when selected,
      mirroring `HistoryList`'s row treatment exactly.
- [x] `App.tsx`: new `selectedDeviceLocationKey` state, lifted the same way
      as `selectedReportId`, reset in `handleSelectDevice` (device switch) -
      no reports-reload-triggered reset exists for devices since their
      history isn't fetched per-selection (see `ownerLocationHistories`
      effect), so device-switch is the only reset point, unlike AirTags'
      reset-on-`currentId`-change.
- [x] `CLAUDE.md`: new "AirTags and owner devices get the same user-facing
      features" hard-constraint section, naming the pairs expected to stay
      in lockstep (`AirtagDetail`/`DeviceDetail`, `MapCard`/`DeviceMapCard`,
      `api.ts` routes, `telegram_bot.py`'s `/list`) and calling out the two
      real implementation differences (report `id` vs. `recorded_at` key,
      opposite list ordering) that a future parity pass needs to account
      for without using them as an excuse to skip a side.

## Review (v33)

- Frontend only: `MapCard.tsx`, `DeviceMapCard.tsx`, `DeviceDetail.tsx`,
  `App.tsx`, plus `CLAUDE.md`. No backend/schema changes.
- Root cause of the `DeviceHistoryList` ordering bug: written before
  `fetch_owner_device_location_history` existed in its current newest-first
  form, likely copy-pasted from `AirtagDetail.tsx`'s `HistoryList` (which
  correctly reverses an oldest-first list) without re-deriving whether the
  reverse was still needed for owner-device data's different native order -
  the same class of ordering-assumption mismatch v31's review already
  flagged once for `DeviceMapCard.tsx`'s `positions[length - 1]` bug.
- Verified: `cd frontend && npx tsc -b && npx vite build && npx oxlint`
  clean (same 4 pre-existing set-state-in-effect warnings as before this
  diff, no new ones). Backend untouched by this change, so re-ran only the
  DB-independent suites already validated in v32
  (`test_geocode.py`/`test_movement.py`/`test_config.py`/`test_keystore.py`)
  as a sanity check, not a full run. Manual browser click-through (jump
  from a device's history row, Previous/Next stepping at both ends of a
  device's trail, address text appearing) not verified in this sandbox -
  same limitation noted in v32.

## v34: Fix `/where` only ever offering AirTags, never owner devices

v27 shipped `/where` AirTag-only (before owner devices existed as an
Objekt), and unlike `/list` it never got the parity pass v31 gave every
other user-facing surface - `_handle_where`/`_send_picker`/
`_format_location`/the callback handler all called `list_airtags` and
nothing else, so the picker, name search, and tap-to-select flow could
never surface a device no matter how it was invoked.

- [x] `telegram_bot.py`: replaced the AirTag-only list with `_where_items`,
      returning a combined `(kind, obj)` sequence - enabled devices
      (primary first), then AirTags - matching `_format_list`'s existing
      ordering. Picker buttons, name search, and `_format_location` now
      dispatch on `kind`; `_format_location`'s device branch reads
      `fetch_owner_device_location_history(..., limit=1)[0]` (newest-first,
      unlike `fetch_reports`, which is oldest-first hence `reports[-1]`).
- [x] Picker `callback_data` stays an index (`where:<n>`) into that same
      combined list, rebuilt identically by the callback handler - avoids
      embedding AirTag/device ids (arbitrary length/charset) in Telegram's
      64-byte callback_data, same reasoning as the pre-existing AirTag-only
      version.
- [x] Help text and the `/`-menu command description now say "Geräts oder
      AirTags" instead of just "AirTags".
- [x] `test_telegram_bot.py`: updated the `/where` tests to patch
      `list_owner_devices`, and added device-picker-ordering and
      device-name-search-to-location tests mirroring the existing AirTag
      ones.

## Review (v34)

- Backend only: `telegram_bot.py`, `test_telegram_bot.py`. No schema/DB
  changes - `fetch_owner_device_location_history` already existed.
- Verified: `pytest tests/test_telegram_bot.py` (10 tests, all passing).
  Did not re-run the full suite (unrelated modules untouched).

## v35: Owner-tracking connect dialog can exclude Family Sharing devices

pyicloud's `PyiCloudService` defaults to `with_family=True`, which pulls
Family Sharing members' devices into `api.devices` alongside the account's
own - `owner_tracking._build_api` never overrode this, so a connected
account with location sharing set up listed/tracked other people's devices
too, not just "mine."

- [x] New `owner_apple_credentials.include_family_devices` column (migration
      `7c1e2b6a4f0d`, defaults to `false`), threaded through
      `start_owner_login`/`submit_owner_2fa_code`/`_connect` into pyicloud's
      `with_family` flag.
- [x] `POST /api/apple/owner/login` takes an `include_family` field
      (default `false`).
- [x] Dashboard: the owner-tracking connect dialog (`AppleConnectPanel.tsx`)
      gained a "shared with me" checkbox, shown only for that adapter via a
      new `familySharingToggle` adapter flag - the AirTag login adapter
      (`FindMy.py`, no such concept) is unaffected.

## Review (v35)

- Backend: `db.py`, `owner_tracking.py`, `web/app.py`, new alembic
  migration. Frontend: `api.ts`, `AppleConnectPanel.tsx`,
  `SettingsAppleAccounts.tsx`. `tests/test_owner_tracking.py`'s
  `PyiCloudService` stub updated to accept the new `with_family` kwarg.
- Verified: `pytest` against a real local Postgres (migration applies
  cleanly to head, full suite green except one pre-existing, unrelated
  failure - `test_fingerprinted_asset_is_cached_immutably` fails identically
  on `main`, before this change, whenever `web/static/assets` already holds
  real built files instead of being empty). `cd frontend && npx tsc -b &&
  npx vite build && npx oxlint` clean (same 4 pre-existing set-state-in-
  effect warnings as v33, no new ones). `docker compose config` with a
  throwaway `.env` parses cleanly. Manual browser click-through of the new
  checkbox not verified in this sandbox (no real Apple ID available here).

## v36: Trail color, clickable history points, fix stepper's WebKit tap-through

Three map-navigation polish items, all applied to both `MapCard.tsx`
(AirTag) and `DeviceMapCard.tsx` (owner device) per CLAUDE.md's parity rule.

- [x] The selected item's own route (`Polyline`) now draws in its own
      chosen/hash-derived color (`mapIcons.ts`'s new `deviceColor()`,
      factored out of `airtagPinIcon`) instead of a hardcoded accent blue -
      matches its pin badge, so the trail reads as visually "theirs."
      Background trails for *other* devices shown for context (the dashed
      ones in `MapCard.tsx`/`OverviewMap.tsx`) are unchanged - those depict
      other objects, not the one just opened.
- [x] New `HistoryPoints` component (`MapCard.tsx`, shared with
      `DeviceMapCard.tsx`): small, low-opacity `CircleMarker` dots at every
      history point other than the currently-displayed one (which already
      has its own full pin/popup), clickable to select that point directly
      on the map instead of only via the sidebar history list. Wired to the
      same `onSelectReport`/`onSelectLocation` handlers `App.tsx` already
      used for the list, so map-click selection behaves identically
      (centers the pin, minimizes the sheet on mobile).
- [x] Fixed the title-bar Älter/Neuer stepper jumping back out to the
      all-devices overview when tapped at the oldest/newest report on iOS:
      the buttons were real `disabled` elements floating directly over the
      Leaflet map, and iOS Safari lets a tap on a disabled control fall
      through to whatever's rendered underneath rather than swallowing it -
      the tap was landing on the map itself, and `MapClickHandler` treated
      it as "tapped away from a pin," closing the whole detail view. Kept
      the buttons real (non-disabled, `aria-disabled` for a11y instead) so
      the tap stays on the button and `stepOlder?.()`/`stepNewer?.()` just
      no-op at the boundary, same dimmed look via conditional `opacity-30`.

## Review (v36)

- Frontend only: `mapIcons.ts`, `MapCard.tsx`, `DeviceMapCard.tsx`,
  `App.tsx`. No backend/schema changes.
- Verified: `cd frontend && npx tsc -b && npx vite build && npx oxlint`
  clean (same 4 pre-existing set-state-in-effect warnings, no new ones).
  Did not run a live browser click-through in this sandbox (no Apple
  ID/Postgres/OAuth setup available here to drive real report data) - the
  stepper fix is a diagnosed root-cause fix (WebKit's disabled-control
  tap-through) rather than one reproduced live; worth a real-device check
  on the next iOS test pass.
