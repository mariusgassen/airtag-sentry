import contextlib
import datetime as dt
import os
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
    set_place_label_correction,
    store_geocoded_point,
    upsert_owner_devices,
)
from airtag_sentry.migrate import upgrade_to_head
from airtag_sentry.web import app as app_module

TEST_DATABASE_URL = os.environ.setdefault(
    "TEST_DATABASE_URL", "postgresql://airtag:airtag@localhost:5432/airtag_sentry_test"
)


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
