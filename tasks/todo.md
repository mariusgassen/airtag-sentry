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
