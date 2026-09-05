import contextlib
import dataclasses
import shutil
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from airtag_sentry.config import load_config
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
    monkeypatch.setenv("GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GITHUB_ALLOWED_LOGIN", "octocat")
    monkeypatch.setenv("SESSION_SECRET_KEY", "session-secret")
    monkeypatch.setenv(
        "AIRTAG_KEY_ENCRYPTION_KEY", "PTx2A3nrHR9wKR_hqK0YtxHZgHqEeZOo8VvV3XwZjxA="
    )
    return load_config()


@pytest.fixture()
def client(cfg):
    return TestClient(
        app_module.create_app(cfg), base_url="https://testserver", follow_redirects=False
    )


def _extract_state(login_html: str) -> str:
    marker = "state="
    start = login_html.index(marker) + len(marker)
    end = login_html.index('"', start)
    return login_html[start:end]


def _mock_github(monkeypatch):
    token_res = Mock(json=lambda: {"access_token": "tok"})
    token_res.raise_for_status = lambda: None
    user_res = Mock(json=lambda: {"login": "octocat"})
    user_res.raise_for_status = lambda: None
    monkeypatch.setattr(app_module.requests, "post", lambda *a, **kw: token_res)
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **kw: user_res)


def test_login_then_callback_succeeds(client, monkeypatch):
    _mock_github(monkeypatch)
    state = _extract_state(client.get("/login").text)

    resp = client.get(f"/auth/callback?code=abc&state={state}")

    assert resp.status_code == 302
    assert resp.headers["location"] == "/"


def test_login_page_is_never_cached(client):
    # Each visit mints a fresh, single-use state baked into the page's link.
    # A cached copy would hand out a stale state that no longer matches
    # anything pending, once the browser or a proxy served it from cache
    # instead of hitting the server again.
    resp = client.get("/login")

    assert resp.headers["cache-control"] == "no-store"


def test_concurrent_login_hit_does_not_invalidate_in_flight_state(client, monkeypatch):
    # Regression test: a background fetch to /login (e.g. the PWA service
    # worker's Workbox precache hitting a protected path and getting
    # redirected here) must not invalidate a login already in flight.
    _mock_github(monkeypatch)

    state = _extract_state(client.get("/login").text)
    client.get("/login")  # incidental second hit, races with the user's own flow

    resp = client.get(f"/auth/callback?code=abc&state={state}")

    assert resp.status_code == 302
    assert resp.headers["location"] == "/"


def test_callback_rejects_unknown_state(client, monkeypatch):
    _mock_github(monkeypatch)
    client.get("/login")

    resp = client.get("/auth/callback?code=abc&state=forged")

    assert resp.status_code == 403


def test_callback_state_is_single_use(client, monkeypatch):
    _mock_github(monkeypatch)
    state = _extract_state(client.get("/login").text)

    first = client.get(f"/auth/callback?code=abc&state={state}")
    assert first.status_code == 302

    replay = client.get(f"/auth/callback?code=abc&state={state}")
    assert replay.status_code == 403


def test_background_fetch_to_protected_path_gets_401_not_login_redirect(client):
    # A service worker's precache fetch sends Sec-Fetch-Mode other than
    # "navigate". It must never be redirected to /login (which would
    # regenerate the OAuth state), just rejected outright.
    resp = client.get("/", headers={"sec-fetch-mode": "cors"})

    assert resp.status_code == 401


def test_repeated_background_fetches_do_not_evict_in_flight_state(client, monkeypatch):
    # fetch() follows redirects by default, so a real service worker's
    # background hit to a protected path would previously chase the 302
    # all the way to /login and regenerate the state there too.
    _mock_github(monkeypatch)
    state = _extract_state(client.get("/login").text)

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
    # dashboard instead of sending them to /login. Both cases now redirect;
    # what actually needed fixing was the OAuth state list evicting an
    # in-flight login under a burst of these (see
    # test_repeated_background_navigations_do_not_evict_in_flight_state).
    resp = client.get("/", headers={"sec-fetch-mode": "navigate"})

    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


def test_repeated_background_navigations_do_not_evict_in_flight_state(client, monkeypatch):
    _mock_github(monkeypatch)
    state = _extract_state(client.get("/login").text)

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
    _mock_github(monkeypatch)
    state = _extract_state(client.get("/login").text)
    client.get(f"/auth/callback?code=abc&state={state}")

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
    _mock_github(monkeypatch)
    state = _extract_state(client.get("/login").text)
    client.get(f"/auth/callback?code=abc&state={state}")

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
