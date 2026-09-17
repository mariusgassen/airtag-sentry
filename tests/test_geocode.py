import os
from unittest.mock import Mock

import psycopg
import pytest

from airtag_sentry.db import get_conn, get_geocoded_point, store_geocoded_point
from airtag_sentry.geocode import (
    GeocodeResult,
    GeocodeSearchResult,
    get_or_fetch_geocode,
    reverse_geocode,
    search_address,
)
from airtag_sentry.migrate import upgrade_to_head

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://airtag:airtag@localhost:5432/airtag_sentry_test"
)
os.environ.setdefault("TEST_DATABASE_URL", TEST_DATABASE_URL)


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    # The 1 req/sec throttle is real-time and would make every test slow -
    # tests only concern themselves with the HTTP call/response mapping.
    import airtag_sentry.geocode as geocode_module

    monkeypatch.setattr(geocode_module, "_MIN_INTERVAL_SECONDS", 0.0)


@pytest.fixture()
def conn():
    """Real Postgres connection, test_tracker.py-style: get_or_fetch_geocode's
    tests exercise genuine DB round-tripping (geocoded_points), not just call
    wiring."""
    try:
        with get_conn(TEST_DATABASE_URL) as connection:
            upgrade_to_head()
            with connection.cursor() as cur:
                cur.execute("TRUNCATE geocoded_points RESTART IDENTITY CASCADE")
            connection.commit()
            yield connection
    except psycopg.OperationalError:
        pytest.skip(f"Postgres not reachable at {TEST_DATABASE_URL}; start it to run this test.")


def test_reverse_geocode_returns_address_and_poi_name(monkeypatch):
    mock_response = Mock()
    mock_response.json.return_value = {
        "display_name": "REWE, 12, Musterstraße, Darmstadt, Hessen, 64283, Deutschland",
        "name": "REWE",
    }
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr("requests.get", lambda *a, **k: mock_response)

    result = reverse_geocode(49.8728, 8.6512)

    assert result == GeocodeResult(
        address="REWE, 12, Musterstraße, Darmstadt, Hessen, 64283, Deutschland",
        poi_name="REWE",
    )


def test_reverse_geocode_builds_a_compact_address_from_structured_fields(monkeypatch):
    mock_response = Mock()
    mock_response.json.return_value = {
        "display_name": "REWE, 12, Musterstraße, Bessungen, Darmstadt, Hessen, 64283, Deutschland",
        "name": "REWE",
        "address": {
            "house_number": "12",
            "road": "Musterstraße",
            "suburb": "Bessungen",
            "city": "Darmstadt",
            "state": "Hessen",
            "postcode": "64283",
            "country": "Deutschland",
        },
    }
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr("requests.get", lambda *a, **k: mock_response)

    result = reverse_geocode(49.8728, 8.6512)

    assert result == GeocodeResult(address="Musterstraße 12, Darmstadt", poi_name="REWE")


def test_reverse_geocode_falls_back_to_display_name_without_addressdetails(monkeypatch):
    # A Nominatim response with no "address" breakdown at all (e.g. an older
    # cached response shape) - the full display_name is still better than
    # nothing.
    mock_response = Mock()
    mock_response.json.return_value = {"display_name": "Musterstraße 5, Darmstadt", "name": "REWE"}
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr("requests.get", lambda *a, **k: mock_response)

    result = reverse_geocode(49.8728, 8.6512)

    assert result == GeocodeResult(address="Musterstraße 5, Darmstadt", poi_name="REWE")


def test_reverse_geocode_returns_none_poi_name_for_a_plain_address(monkeypatch):
    # Nominatim omits "name" entirely for a point that isn't a named POI.
    mock_response = Mock()
    mock_response.json.return_value = {"display_name": "Musterstraße 5, Darmstadt"}
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr("requests.get", lambda *a, **k: mock_response)

    result = reverse_geocode(49.8728, 8.6512)

    assert result == GeocodeResult(address="Musterstraße 5, Darmstadt", poi_name=None)


def test_reverse_geocode_returns_empty_result_on_request_failure(monkeypatch):
    import requests

    def raise_error(*a, **k):
        raise requests.RequestException("boom")

    monkeypatch.setattr("requests.get", raise_error)

    result = reverse_geocode(49.8728, 8.6512)

    assert result == GeocodeResult(address=None, poi_name=None)


def test_get_or_fetch_geocode_returns_cached_result_without_a_network_call(monkeypatch, conn):
    store_geocoded_point(conn, 49.8728, 8.6512, "Cached Address", "Cached POI")

    def fail_if_called(*a, **k):
        raise AssertionError("reverse_geocode should not be called for an already-cached coordinate")

    monkeypatch.setattr("airtag_sentry.geocode.reverse_geocode", fail_if_called)

    result = get_or_fetch_geocode(conn, 49.8728, 8.6512)

    assert result == GeocodeResult(address="Cached Address", poi_name="Cached POI")


def test_get_or_fetch_geocode_fetches_and_stores_on_a_cache_miss(monkeypatch, conn):
    monkeypatch.setattr(
        "airtag_sentry.geocode.reverse_geocode",
        lambda lat, lon: GeocodeResult(address="Fresh Address", poi_name="Fresh POI"),
    )

    result = get_or_fetch_geocode(conn, 49.8728, 8.6512)

    assert result == GeocodeResult(address="Fresh Address", poi_name="Fresh POI")
    stored = get_geocoded_point(conn, 49.8728, 8.6512)
    assert stored is not None
    assert stored.address == "Fresh Address"
    assert stored.poi_name == "Fresh POI"


def test_get_or_fetch_geocode_does_not_store_an_empty_result(monkeypatch, conn):
    monkeypatch.setattr(
        "airtag_sentry.geocode.reverse_geocode",
        lambda lat, lon: GeocodeResult(address=None, poi_name=None),
    )

    result = get_or_fetch_geocode(conn, 49.8728, 8.6512)

    assert result == GeocodeResult(address=None, poi_name=None)
    assert get_geocoded_point(conn, 49.8728, 8.6512) is None


def test_reverse_geocode_returns_empty_result_on_missing_display_name(monkeypatch):
    mock_response = Mock()
    mock_response.json.return_value = {}
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr("requests.get", lambda *a, **k: mock_response)

    result = reverse_geocode(49.8728, 8.6512)

    assert result == GeocodeResult(address=None, poi_name=None)


def test_search_address_returns_matching_results(monkeypatch):
    mock_response = Mock()
    mock_response.json.return_value = [
        {"display_name": "Mornewegstraße 30, Darmstadt, Hessen, 64293, Deutschland", "lat": "49.8728", "lon": "8.6512"},
        {"display_name": "Mornewegstraße 1, Darmstadt, Hessen, 64293, Deutschland", "lat": "49.87", "lon": "8.65"},
    ]
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr("requests.get", lambda *a, **k: mock_response)

    result = search_address("Mornewegstraße Darmstadt")

    assert result == [
        GeocodeSearchResult(
            display_name="Mornewegstraße 30, Darmstadt, Hessen, 64293, Deutschland", lat=49.8728, lon=8.6512
        ),
        GeocodeSearchResult(
            display_name="Mornewegstraße 1, Darmstadt, Hessen, 64293, Deutschland", lat=49.87, lon=8.65
        ),
    ]


def test_search_address_returns_empty_list_for_no_matches(monkeypatch):
    mock_response = Mock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr("requests.get", lambda *a, **k: mock_response)

    assert search_address("asdkjaskdjaskjd") == []


def test_search_address_returns_empty_list_on_request_failure(monkeypatch):
    import requests

    def raise_error(*a, **k):
        raise requests.RequestException("boom")

    monkeypatch.setattr("requests.get", raise_error)

    assert search_address("Darmstadt") == []
