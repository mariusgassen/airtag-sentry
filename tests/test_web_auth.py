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
    resp = client.get("/", headers={"sec-fetch-mode": "navigate"})

    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"
