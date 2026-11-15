import contextlib
import datetime as dt
import os
import shutil
import time
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import psycopg
import pytest
from fastapi.testclient import TestClient

from airtag_sentry.config import load_config
from airtag_sentry.db import (
    OwnerLocation,
    Report,
    create_airtag,
    create_named_place,
    get_conn,
    insert_reports,
    record_owner_device_location,
    set_owner_device_enabled,
    set_place_label_correction,
    store_geocoded_point,
    upsert_owner_devices,
)
from airtag_sentry.migrate import upgrade_to_head
from airtag_sentry.web import app as app_module

TEST_DATABASE_URL = os.environ.setdefault(
    "TEST_DATABASE_URL", "postgresql://airtag:airtag@localhost:5432/airtag_sentry_test"
)


@pytest.fixture(autouse=True, scope="module")
def _static_dir():
    """create_app() mounts StaticFiles(STATIC_DIR) unconditionally; the frontend
    build normally provides it. Stand in a placeholder when it's absent so this
    module doesn't require a frontend build just to test the history routes -
    same approach as test_web_auth.py's identical fixture (duplicated rather
    than shared: tests/ has no conftest.py/__init__.py, see _login's docstring)."""
    created = not app_module.STATIC_DIR.exists()
    if created:
        app_module.STATIC_DIR.mkdir(parents=True)
        (app_module.STATIC_DIR / "index.html").write_text("<html></html>")
    yield
    if created:
        shutil.rmtree(app_module.STATIC_DIR)


@pytest.fixture()
def conn():
    try:
        with get_conn(TEST_DATABASE_URL) as connection:
            upgrade_to_head()
            with connection.cursor() as cur:
                cur.execute(
                    "TRUNCATE airtags, location_reports, owner_devices, owner_device_locations, "
                    "named_places, geocoded_points, place_label_corrections RESTART IDENTITY CASCADE"
                )
            connection.commit()
            create_airtag(connection, "bike", "Fahrrad")
            yield connection
    except psycopg.OperationalError:
        pytest.skip(f"Postgres not reachable at {TEST_DATABASE_URL}; start it to run this test.")


@pytest.fixture()
def cfg(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "airtag")
    monkeypatch.setenv("POSTGRES_PASSWORD", "change-me")
    monkeypatch.setenv("POSTGRES_DB", "airtag_sentry")
    monkeypatch.setenv("OIDC_ISSUER", "https://authentik.example.com/application/o/airtag-sentry/")
    monkeypatch.setenv("OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OIDC_ALLOWED_USERNAME", "octocat")
    monkeypatch.setenv("SESSION_SECRET_KEY", "session-secret")
    monkeypatch.setenv("AIRTAG_KEY_ENCRYPTION_KEY", "PTx2A3nrHR9wKR_hqK0YtxHZgHqEeZOo8VvV3XwZjxA=")
    return load_config()


@pytest.fixture()
def client(cfg, conn, monkeypatch):
    app = app_module.create_app(cfg)
    monkeypatch.setattr(app_module, "get_conn", lambda _url: contextlib.nullcontext(conn))
    # Real OIDC discovery is lazy - pre-seed it (see test_web_auth.py's
    # identical fixture) so _login below can drive a real /auth/login ->
    # /auth/callback round trip without hitting the network.
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


def _login(client, monkeypatch):
    """Drives a real login round-trip so AuthMiddleware accepts subsequent
    requests - same approach as test_web_auth.py's identical helper
    (duplicated rather than imported: tests/ has no __init__.py, so
    cross-module test imports aren't a stable pattern here)."""
    authentik = client.app.state.oauth.authentik
    monkeypatch.setattr(
        authentik, "fetch_access_token", AsyncMock(return_value={"access_token": "tok", "token_type": "Bearer"})
    )
    monkeypatch.setattr(authentik, "userinfo", AsyncMock(return_value={"preferred_username": "octocat"}))

    login_resp = client.get("/auth/login")
    state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]
    client.get(f"/auth/callback?code=abc&state={state}")


def test_reports_route_returns_raw_points_and_a_labeled_stay(client, conn, monkeypatch):
    _login(client, monkeypatch)
    reports = [
        Report(
            id=None, airtag_id="bike", timestamp=dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc),
            lat=49.8728, lon=8.6512, accuracy=5.0, confidence=3, battery_level="full",
        ),
        Report(
            id=None, airtag_id="bike", timestamp=dt.datetime(2026, 1, 1, 13, 0, tzinfo=dt.timezone.utc),
            lat=49.8728, lon=8.6512, accuracy=5.0, confidence=3, battery_level="full",
        ),
    ]
    insert_reports(conn, reports)
    create_named_place(conn, "Home", 49.8728, 8.6512, 50.0)

    resp = client.get("/api/reports?airtag_id=bike")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["raw"]) == 2
    assert len(body["stays"]) == 1
    stay = body["stays"][0]
    assert stay["count"] == 2
    assert stay["label"] == "Home"
    assert stay["place_id"] is not None
    assert stay["start"] == "2026-01-01T12:00:00+00:00"
    assert stay["end"] == "2026-01-01T13:00:00+00:00"


def test_reports_route_falls_back_to_correction_then_poi_then_address(client, conn, monkeypatch):
    _login(client, monkeypatch)
    insert_reports(
        conn,
        [
            Report(
                id=None, airtag_id="bike", timestamp=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
                lat=49.8728, lon=8.6512, accuracy=None, confidence=None, battery_level=None,
            )
        ],
    )
    store_geocoded_point(conn, 49.8728, 8.6512, "12 Main St", "REWE")

    resp = client.get("/api/reports?airtag_id=bike")
    assert resp.json()["stays"][0]["label"] == "REWE"

    set_place_label_correction(conn, 49.8728, 8.6512, "My Corner Store")
    resp = client.get("/api/reports?airtag_id=bike")
    assert resp.json()["stays"][0]["label"] == "My Corner Store"


def test_owner_device_history_route_returns_raw_points_and_a_labeled_stay(client, conn, monkeypatch):
    _login(client, monkeypatch)
    upsert_owner_devices(conn, [{"id": "d1", "name": "iPhone", "device_type": "iPhone"}], dt.datetime.now(dt.timezone.utc))
    record_owner_device_location(
        conn,
        OwnerLocation(
            id=None, device_id="d1", recorded_at=dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc),
            lat=49.8728, lon=8.6512, horizontal_accuracy=5.0,
        ),
    )
    create_named_place(conn, "Home", 49.8728, 8.6512, 50.0)

    resp = client.get("/api/owner-devices/history?device_id=d1")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["raw"]) == 1
    assert body["stays"][0]["label"] == "Home"
    assert body["stays"][0]["anchor_recorded_at"] == "2026-01-01T12:00:00+00:00"


def test_owner_device_history_route_maps_start_and_end_to_earliest_and_latest(client, conn, monkeypatch):
    """Regression test: owner-device locations arrive newest-first (unlike
    AirTag reports, oldest-first - see CLAUDE.md), so a stay's start/end
    mapping is reversed relative to the AirTag-side route. A single-point
    stay can't distinguish a correct reversal from an accidental one (both
    collapse to the same timestamp), so this uses three distinct times -
    mirrors test_reports_route_returns_raw_points_and_a_labeled_stay's
    two-point proof on the AirTag side."""
    _login(client, monkeypatch)
    upsert_owner_devices(conn, [{"id": "d1", "name": "iPhone", "device_type": "iPhone"}], dt.datetime.now(dt.timezone.utc))
    for hour, minute in [(12, 0), (12, 30), (13, 0)]:
        record_owner_device_location(
            conn,
            OwnerLocation(
                id=None, device_id="d1", recorded_at=dt.datetime(2026, 1, 1, hour, minute, tzinfo=dt.timezone.utc),
                lat=49.8728, lon=8.6512, horizontal_accuracy=5.0,
            ),
        )

    resp = client.get("/api/owner-devices/history?device_id=d1")

    assert resp.status_code == 200
    stay = resp.json()["stays"][0]
    assert stay["count"] == 3
    assert stay["start"] == "2026-01-01T12:00:00+00:00"
    assert stay["end"] == "2026-01-01T13:00:00+00:00"


def test_timeline_route_merges_airtag_and_owner_device_visits_newest_first(client, conn, monkeypatch):
    _login(client, monkeypatch)
    insert_reports(
        conn,
        [
            Report(
                id=None, airtag_id="bike", timestamp=dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.timezone.utc),
                lat=49.8728, lon=8.6512, accuracy=5.0, confidence=3, battery_level="full",
            )
        ],
    )
    create_named_place(conn, "Home", 49.8728, 8.6512, 50.0)
    upsert_owner_devices(conn, [{"id": "d1", "name": "iPhone", "device_type": "iPhone"}], dt.datetime.now(dt.timezone.utc))
    set_owner_device_enabled(conn, "d1", True)
    record_owner_device_location(
        conn,
        OwnerLocation(
            id=None, device_id="d1", recorded_at=dt.datetime(2026, 1, 1, 15, 0, tzinfo=dt.timezone.utc),
            lat=49.9, lon=8.7, horizontal_accuracy=5.0,
        ),
    )
    store_geocoded_point(conn, 49.9, 8.7, "12 Main St", "REWE")

    resp = client.get("/api/timeline")

    assert resp.status_code == 200
    visits = resp.json()["visits"]
    assert len(visits) == 2
    # Newest first: the owner device's 15:00 visit before the AirTag's 09:00 one.
    assert visits[0]["object_type"] == "device"
    assert visits[0]["object_id"] == "d1"
    assert visits[0]["object_name"] == "iPhone"
    assert visits[0]["label"] == "REWE"
    assert visits[0]["address"] == "12 Main St"
    assert visits[0]["poi_name"] == "REWE"
    assert visits[0]["anchor_id"] is None
    assert visits[0]["anchor_recorded_at"] == "2026-01-01T15:00:00+00:00"
    assert visits[1]["object_type"] == "airtag"
    assert visits[1]["object_id"] == "bike"
    assert visits[1]["label"] == "Home"
    assert visits[1]["place_id"] is not None
    assert visits[1]["anchor_id"] is not None
    assert visits[1]["anchor_recorded_at"] is None


def test_timeline_route_excludes_disabled_owner_devices(client, conn, monkeypatch):
    """A device newly discovered by owner_tracking.upsert_owner_devices starts
    disabled (see its docstring: "discovering a device never opts it into
    tracking on its own") - the timeline should never surface its history."""
    _login(client, monkeypatch)
    upsert_owner_devices(conn, [{"id": "d1", "name": "iPhone", "device_type": "iPhone"}], dt.datetime.now(dt.timezone.utc))
    record_owner_device_location(
        conn,
        OwnerLocation(
            id=None, device_id="d1", recorded_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
            lat=49.9, lon=8.7, horizontal_accuracy=5.0,
        ),
    )

    resp = client.get("/api/timeline")

    assert resp.status_code == 200
    assert resp.json()["visits"] == []


def test_timeline_route_defaults_to_all_history_and_days_filters_older_visits(client, conn, monkeypatch):
    """Regression test: /api/timeline used to cap each object at its last
    500/200 points regardless of age, which for a frequently-polling object
    could cover well under a day - making "no more history" indistinguishable
    from "there's more, just not fetched". Default (no `days`) must return
    everything; `days` narrows to a recent window."""
    _login(client, monkeypatch)
    now = dt.datetime.now(dt.timezone.utc)
    insert_reports(
        conn,
        [
            Report(
                id=None, airtag_id="bike", timestamp=now - dt.timedelta(days=40),
                lat=49.8728, lon=8.6512, accuracy=5.0, confidence=3, battery_level="full",
            ),
            Report(
                id=None, airtag_id="bike", timestamp=now - dt.timedelta(days=1),
                lat=49.9, lon=8.7, accuracy=5.0, confidence=3, battery_level="full",
            ),
        ],
    )

    resp = client.get("/api/timeline")
    assert resp.status_code == 200
    assert len(resp.json()["visits"]) == 2

    resp = client.get("/api/timeline", params={"days": 7})
    assert resp.status_code == 200
    visits = resp.json()["visits"]
    assert len(visits) == 1
    assert visits[0]["lat"] == 49.9


def test_reports_export_returns_csv_and_gpx_with_days_filter(client, conn, monkeypatch):
    _login(client, monkeypatch)
    now = dt.datetime.now(dt.timezone.utc)
    insert_reports(
        conn,
        [
            Report(
                id=None, airtag_id="bike", timestamp=now - dt.timedelta(days=20),
                lat=49.8728, lon=8.6512, accuracy=5.0, confidence=3, battery_level="low",
            ),
            Report(
                id=None, airtag_id="bike", timestamp=now - dt.timedelta(hours=2),
                lat=49.9, lon=8.7, accuracy=8.0, confidence=2, battery_level="full",
            ),
        ],
    )

    csv_resp = client.get("/api/reports/export", params={"airtag_id": "bike", "format": "csv"})
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert 'attachment; filename="Fahrrad.csv"' == csv_resp.headers["content-disposition"]
    lines = csv_resp.text.strip().splitlines()
    assert lines[0] == "timestamp,lat,lon,accuracy,confidence,battery_level"
    assert len(lines) == 3

    gpx_resp = client.get("/api/reports/export", params={"airtag_id": "bike", "format": "gpx", "days": 7})
    assert gpx_resp.status_code == 200
    assert "application/gpx+xml" in gpx_resp.headers["content-type"]
    assert 'attachment; filename="Fahrrad.gpx"' == gpx_resp.headers["content-disposition"]
    assert "<name>Fahrrad</name>" in gpx_resp.text
    assert 'lat="49.9000000" lon="8.7000000"' in gpx_resp.text
    assert "49.8728" not in gpx_resp.text


def test_owner_device_history_export_supports_csv_gpx_and_slashy_ids(client, conn, monkeypatch):
    _login(client, monkeypatch)
    slashy_id = "dev/abc+123=="
    now = dt.datetime.now(dt.timezone.utc)
    upsert_owner_devices(
        conn,
        [{"id": slashy_id, "name": "MacBook Pro", "device_type": "Mac"}],
        now,
    )
    record_owner_device_location(
        conn,
        OwnerLocation(
            id=None, device_id=slashy_id, recorded_at=now - dt.timedelta(days=15),
            lat=52.5, lon=13.4, horizontal_accuracy=10.0, battery_level=0.8, battery_status="Unplugged",
        ),
    )
    record_owner_device_location(
        conn,
        OwnerLocation(
            id=None, device_id=slashy_id, recorded_at=now - dt.timedelta(minutes=30),
            lat=52.52, lon=13.42, horizontal_accuracy=5.0, battery_level=0.75, battery_status="Charging",
        ),
    )

    csv_resp = client.get("/api/owner-devices/history/export", params={"device_id": slashy_id, "format": "csv"})
    assert csv_resp.status_code == 200
    assert 'attachment; filename="MacBook-Pro.csv"' == csv_resp.headers["content-disposition"]
    lines = csv_resp.text.strip().splitlines()
    assert lines[0] == "timestamp,lat,lon,horizontal_accuracy,battery_level,battery_status,battery_reported"
    assert len(lines) == 3

    gpx_resp = client.get(
        "/api/owner-devices/history/export",
        params={"device_id": slashy_id, "format": "gpx", "days": 7},
    )
    assert gpx_resp.status_code == 200
    assert 'attachment; filename="MacBook-Pro.gpx"' == gpx_resp.headers["content-disposition"]
    assert "<name>MacBook Pro</name>" in gpx_resp.text
    assert 'lat="52.5200000" lon="13.4200000"' in gpx_resp.text
    assert "52.5000000" not in gpx_resp.text

    missing = client.get("/api/owner-devices/history/export", params={"device_id": "nope"})
    assert missing.status_code == 404


def test_settings_route_persists_history_retention_days(client, conn, monkeypatch):
    _login(client, monkeypatch)
    current = client.get("/api/settings").json()
    assert current["history_retention_days"] is None

    try:
        updated = client.put("/api/settings", json={**current, "history_retention_days": 90})
        assert updated.status_code == 200
        assert updated.json()["history_retention_days"] == 90

        cleared = client.put("/api/settings", json={**current, "history_retention_days": None})
        assert cleared.status_code == 200
        assert cleared.json()["history_retention_days"] is None
    finally:
        client.put("/api/settings", json=current)


def test_statuses_route_returns_bulk_status_map(client, conn, monkeypatch):
    _login(client, monkeypatch)
    create_airtag(conn, "keys", "Schlüssel")
    with conn.cursor() as cur:
        cur.execute("UPDATE airtags SET enabled = FALSE WHERE id = 'keys'")
    conn.commit()

    ts = dt.datetime(2026, 2, 1, 12, 0, tzinfo=dt.timezone.utc)
    insert_reports(
        conn,
        [
            Report(
                id=None, airtag_id="bike", timestamp=ts,
                lat=49.87, lon=8.65, accuracy=12.0, confidence=3, battery_level="medium",
            ),
        ],
    )

    resp = client.get("/api/statuses")
    assert resp.status_code == 200
    body = resp.json()
    assert list(body.keys()) == ["bike"]
    assert body["bike"]["airtag_id"] == "bike"
    assert body["bike"]["airtag_name"] == "Fahrrad"
    assert body["bike"]["last_report"]["lat"] == 49.87
    assert body["bike"]["last_report"]["battery_level"] == "medium"
    assert body["bike"]["last_alert"] is None
    assert body["bike"]["poll_interval_minutes"] >= 1

