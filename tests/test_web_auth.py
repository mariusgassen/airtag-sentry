import contextlib
import dataclasses
import datetime as dt
import shutil
import time
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from airtag_sentry.config import load_config
from airtag_sentry.db import OwnerAppleCredentials, OwnerDevice
from airtag_sentry.web import app as app_module


@pytest.fixture(autouse=True, scope="module")
def _static_dir():
    """create_app() mounts StaticFiles(STATIC_DIR) unconditionally; the frontend
    build normally provides it. Stand in a placeholder when it's absent so this
    module doesn't require a frontend build just to test the auth routes."""
    created = not app_module.STATIC_DIR.exists()
    if created:
        app_module.STATIC_DIR.mkdir(parents=True)
        (app_module.STATIC_DIR / "index.html").write_text("<html></html>")
    yield
    if created:
        shutil.rmtree(app_module.STATIC_DIR)


@pytest.fixture()
def cfg(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "airtag")
    monkeypatch.setenv("POSTGRES_PASSWORD", "change-me")
    monkeypatch.setenv("POSTGRES_DB", "airtag_sentry")
    monkeypatch.setenv("OIDC_ISSUER", "https://authentik.example.com/application/o/airtag-sentry/")
    monkeypatch.setenv("OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OIDC_ALLOWED_EMAIL", "octocat@example.com")
    monkeypatch.setenv("SESSION_SECRET_KEY", "session-secret")
    monkeypatch.setenv(
        "AIRTAG_KEY_ENCRYPTION_KEY", "PTx2A3nrHR9wKR_hqK0YtxHZgHqEeZOo8VvV3XwZjxA="
    )
    return load_config()


@pytest.fixture()
def client(cfg):
    app = app_module.create_app(cfg)
    # Real discovery (fetching /.well-known/openid-configuration from
    # Authentik) is lazy - it only happens on the first real login attempt.
    # Pre-seed it here (with `_loaded_at` already set) so tests exercise
    # authlib's real state/PKCE/nonce handling without ever hitting the
    # network; only the actual token exchange and userinfo calls are
    # stubbed per-test via _mock_oidc.
    app.state.oauth.authentik.server_metadata.update(
        {
            "issuer": "https://authentik.example.com/application/o/airtag-sentry/",
            "authorization_endpoint": "https://authentik.example.com/application/o/authorize/",
            "token_endpoint": "https://authentik.example.com/application/o/token/",
            "userinfo_endpoint": "https://authentik.example.com/application/o/userinfo/",
            "_loaded_at": time.time(),
        }
    )
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def _extract_state(auth_login_resp) -> str:
    location = auth_login_resp.headers["location"]
    return parse_qs(urlparse(location).query)["state"][0]


def _mock_oidc(client, monkeypatch, email: str = "octocat@example.com"):
    """Stub the two calls that actually leave the process during the OIDC
    exchange (token endpoint + userinfo endpoint), while leaving authlib's
    own state/PKCE/nonce validation in authorize_access_token() to run for
    real - that's what the state-handling regression tests below exercise."""
    authentik = client.app.state.oauth.authentik
    monkeypatch.setattr(
        authentik,
        "fetch_access_token",
        AsyncMock(return_value={"access_token": "tok", "token_type": "Bearer"}),
    )
    monkeypatch.setattr(authentik, "userinfo", AsyncMock(return_value={"email": email}))


def _login(client, monkeypatch, email: str = "octocat@example.com") -> None:
    _mock_oidc(client, monkeypatch, email=email)
    state = _extract_state(client.get("/auth/login"))
    client.get(f"/auth/callback?code=abc&state={state}")


def test_login_then_callback_succeeds(client, monkeypatch):
    _mock_oidc(client, monkeypatch)
    state = _extract_state(client.get("/auth/login"))

    resp = client.get(f"/auth/callback?code=abc&state={state}")

    assert resp.status_code == 302
    assert resp.headers["location"] == "/"


def test_login_page_is_never_cached(client):
    resp = client.get("/login")

    assert resp.headers["cache-control"] == "no-store"


def test_second_login_link_supersedes_the_first(client, monkeypatch):
    # authlib's Starlette integration keeps only the most recently minted
    # state per session (it drops older _state_authentik_* keys itself, to
    # bound the signed session cookie's size) - unlike the old hand-rolled
    # GitHub flow, which had to tolerate many concurrent pending states
    # because every hit to /login (including background PWA wake-ups
    # redirected there while logged out) minted a fresh one. That's no
    # longer true here: only an explicit click on /auth/login's button mints
    # a state, so this single-slot behavior is a non-issue in practice, not
    # a regression to guard against - this test just documents it.
    _mock_oidc(client, monkeypatch)

    first_state = _extract_state(client.get("/auth/login"))
    second_state = _extract_state(client.get("/auth/login"))
    assert first_state != second_state

    stale = client.get(f"/auth/callback?code=abc&state={first_state}")
    assert stale.status_code == 403

    current = client.get(f"/auth/callback?code=abc&state={second_state}")
    assert current.status_code == 302
    assert current.headers["location"] == "/"


def test_callback_rejects_unknown_state(client, monkeypatch):
    _mock_oidc(client, monkeypatch)
    client.get("/auth/login")

    resp = client.get("/auth/callback?code=abc&state=forged")

    assert resp.status_code == 403


def test_callback_state_is_single_use(client, monkeypatch):
    _mock_oidc(client, monkeypatch)
    state = _extract_state(client.get("/auth/login"))

    first = client.get(f"/auth/callback?code=abc&state={state}")
    assert first.status_code == 302

    replay = client.get(f"/auth/callback?code=abc&state={state}")
    assert replay.status_code == 403


def test_callback_rejects_a_disallowed_account(client, monkeypatch):
    _mock_oidc(client, monkeypatch, email="someone-else@example.com")
    state = _extract_state(client.get("/auth/login"))

    resp = client.get(f"/auth/callback?code=abc&state={state}")

    assert resp.status_code == 403


def test_background_fetch_to_protected_path_gets_401_not_login_redirect(client):
    # A service worker's precache fetch sends Sec-Fetch-Mode other than
    # "navigate". It must never be redirected to /login (which would
    # regenerate the OAuth state), just rejected outright.
    resp = client.get("/", headers={"sec-fetch-mode": "cors"})

    assert resp.status_code == 401


def test_repeated_background_fetches_do_not_evict_in_flight_state(client, monkeypatch):
    # fetch() follows redirects by default, so a real service worker's
    # background hit to a protected path would chase the 302 all the way to
    # /login - which no longer touches any OAuth state at all (that only
    # happens on /auth/login), so this can't evict an in-flight login.
    _mock_oidc(client, monkeypatch)
    state = _extract_state(client.get("/auth/login"))

    for _ in range(10):
        client.get("/", headers={"sec-fetch-mode": "cors"}, follow_redirects=True)

    resp = client.get(f"/auth/callback?code=abc&state={state}")

    assert resp.status_code == 302


def test_real_navigation_to_protected_path_still_redirects_to_login(client):
    resp = client.get("/", headers={"sec-fetch-mode": "navigate", "sec-fetch-user": "?1"})

    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


def test_navigation_without_user_gesture_still_redirects_to_login(client):
    # iOS periodically wakes an installed PWA in the background (for
    # push/badge refresh) and does a real top-level navigation to "/" with
    # no user present - still Sec-Fetch-Mode: navigate, but never carrying
    # Sec-Fetch-User: ?1. A plain browser reload of "/" *also* never carries
    # Sec-Fetch-User: ?1 (it's a reload, not a link/bookmark activation), so
    # gating the redirect on that header 401'd real users reloading the
    # dashboard instead of sending them to /login. Both cases now redirect.
    resp = client.get("/", headers={"sec-fetch-mode": "navigate"})

    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


def test_repeated_background_navigations_do_not_evict_in_flight_state(client, monkeypatch):
    _mock_oidc(client, monkeypatch)
    state = _extract_state(client.get("/auth/login"))

    for _ in range(10):
        client.get("/", headers={"sec-fetch-mode": "navigate"}, follow_redirects=True)

    resp = client.get(f"/auth/callback?code=abc&state={state}")

    assert resp.status_code == 302


def test_health_is_reachable_without_a_session(client, monkeypatch):
    # Coolify's Docker healthcheck probes this directly, with no session cookie.
    # Stub the DB round-trip so this test doesn't need a real Postgres (this
    # file's `cfg` fixture uses made-up Postgres creds, like every other test
    # here) - the real round-trip is exercised by test_health_reports_503_*
    # below and by test_db.py's live-Postgres suite.
    monkeypatch.setattr(
        app_module, "get_conn", lambda _url: contextlib.nullcontext(Mock(execute=lambda *a: None))
    )

    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_reports_503_when_database_is_unreachable(cfg):
    broken_cfg = dataclasses.replace(
        cfg, database_url=cfg.database_url.replace(cfg.database_url.rsplit("/", 1)[-1], "does-not-exist")
    )
    client = TestClient(
        app_module.create_app(broken_cfg), base_url="https://testserver", follow_redirects=False
    )

    resp = client.get("/health")

    assert resp.status_code == 503


def test_fingerprinted_asset_is_cached_immutably(client, monkeypatch):
    # Vite fingerprints everything under /assets/ with a content hash, so a
    # given filename's content never changes - safe to cache forever.
    _login(client, monkeypatch)

    assets_dir = app_module.STATIC_DIR / "assets"
    assets_dir.mkdir(exist_ok=True)
    asset = assets_dir / "index-deadbeef.js"
    asset.write_text("console.log('hi')")
    try:
        resp = client.get("/assets/index-deadbeef.js")
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"
    finally:
        asset.unlink()
        assets_dir.rmdir()


def test_app_shell_is_never_cached(client, monkeypatch):
    # index.html is unhashed and points the browser at the current
    # fingerprinted asset filenames. Vite's emptyOutDir deletes the old
    # assets on every build, so a browser holding a stale cached index.html
    # after a new deploy gets 404s on its own <script>/<link> tags until a
    # hard refresh - it must always be revalidated.
    _login(client, monkeypatch)

    resp = client.get("/")

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-cache"


def test_service_worker_script_is_never_cached(client):
    sw = app_module.STATIC_DIR / "sw.js"
    sw.write_text("// service worker")
    try:
        resp = client.get("/sw.js")
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "no-cache"
    finally:
        sw.unlink()


def test_owner_devices_route_reads_persisted_devices_without_a_live_apple_call(client, monkeypatch):
    # Regression test: GET /api/owner-devices used to do a *live* Apple call on
    # every request (owner_tracking.list_owner_devices) with no caching - a
    # lapsed pyicloud session, a transient network error, or Apple rate
    # limiting all blanked the dashboard's whole device list, since the
    # frontend treats a failed fetch as "no devices" (see tasks/todo.md).
    # Identity is now persisted by the background poller instead
    # (owner_tracking.fetch_owner_device_locations), so this route just reads
    # Postgres and can't fail because of Apple at all.
    _login(client, monkeypatch)

    monkeypatch.setattr(
        app_module, "get_conn", lambda _url: contextlib.nullcontext(Mock())
    )

    # owner_tracking.list_owner_devices (the old live-Apple-call path) was
    # removed entirely - nothing to stub out here, this route now only ever
    # touches Postgres.
    last_sync = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(
        app_module,
        "db_list_owner_devices",
        lambda _conn: [
            # Seen in the most recent successful sync (same timestamp).
            OwnerDevice(
                id="d1", name="MacBook", device_type="Mac", enabled=True, is_primary=False, last_seen_at=last_sync
            ),
            # Not seen in the most recent sync (stale last_seen_at) - e.g.
            # removed from iCloud.
            OwnerDevice(
                id="d2",
                name="iPad",
                device_type="iPad",
                enabled=False,
                is_primary=False,
                last_seen_at=last_sync - dt.timedelta(hours=1),
            ),
        ],
    )
    monkeypatch.setattr(
        app_module,
        "get_owner_apple_credentials",
        lambda _conn: OwnerAppleCredentials(
            apple_id="owner@example.com", encrypted_password="enc", last_sync_at=last_sync, last_sync_error=None
        ),
    )

    resp = client.get("/api/owner-devices")

    assert resp.status_code == 200
    body = resp.json()
    assert [d["id"] for d in body] == ["d1", "d2"]
    assert [d["on_account"] for d in body] == [True, False]


def test_owner_device_routes_accept_ids_containing_a_slash(client, monkeypatch):
    # Regression test: Apple's own device ids (pyicloud AppleDevice.id) are
    # opaque base64-ish blobs that can contain a literal "/" - previously
    # these three routes took device_id as a URL *path* segment, and even
    # though the frontend correctly percent-encoded it (encodeURIComponent),
    # ASGI/uvicorn decodes "%2F" back into a literal "/" while building the
    # request path *before* routing runs, splitting one {device_id} segment
    # into two and breaking route matching (a 405, since the split path
    # happened to collide with another route's static segments/methods).
    # device_id now travels in the body (PUT routes) or as a query param (GET
    # history), neither of which treats "/" as a delimiter.
    _login(client, monkeypatch)

    monkeypatch.setattr(app_module, "get_conn", lambda _url: contextlib.nullcontext(Mock()))

    slashy_id = "AYPwQofdb4u+u4RpzfkAFj9WaXtGuR3ffJRt3OMwic/XrQDUiWs5dCtra9prAfRuX3bA=="

    seen_enabled = {}
    monkeypatch.setattr(
        app_module.owner_tracking,
        "set_device_enabled",
        lambda _conn, device_id, enabled: seen_enabled.update(device_id=device_id, enabled=enabled)
        or OwnerDevice(id=device_id, name="MacBook", device_type="Mac", enabled=enabled, is_primary=False),
    )
    resp = client.put("/api/owner-devices", json={"device_id": slashy_id, "enabled": True})
    assert resp.status_code == 200
    assert seen_enabled == {"device_id": slashy_id, "enabled": True}

    seen_primary = {}
    monkeypatch.setattr(
        app_module.owner_tracking,
        "set_device_primary",
        lambda _conn, device_id: seen_primary.update(device_id=device_id)
        or OwnerDevice(id=device_id, name="MacBook", device_type="Mac", enabled=True, is_primary=True),
    )
    resp = client.put("/api/owner-devices/primary", json={"device_id": slashy_id})
    assert resp.status_code == 200
    assert seen_primary == {"device_id": slashy_id}

    seen_history = {}
    monkeypatch.setattr(
        app_module,
        "fetch_owner_device_location_history",
        lambda _conn, device_id, limit: seen_history.update(device_id=device_id, limit=limit) or [],
    )
    resp = client.get("/api/owner-devices/history", params={"device_id": slashy_id, "limit": 50})
    assert resp.status_code == 200
    assert seen_history == {"device_id": slashy_id, "limit": 50}


def test_favicon_is_servable_without_a_session(client):
    # Browsers/bookmark tools request /favicon.ico directly, independent of
    # the page's own <link rel="icon"> and outside any authenticated fetch
    # context - it must not be redirected behind login like the app shell.
    favicon = app_module.STATIC_DIR / "favicon.ico"
    favicon.write_bytes(b"\x00\x00\x01\x00")
    try:
        resp = client.get("/favicon.ico", headers={"sec-fetch-mode": "navigate"})
        assert resp.status_code == 200
    finally:
        favicon.unlink()
