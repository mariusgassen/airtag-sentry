from unittest.mock import Mock

import pytest

from airtag_sentry.geocode import GeocodeResult, reverse_geocode


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    # The 1 req/sec throttle is real-time and would make every test slow -
    # tests only concern themselves with the HTTP call/response mapping.
    import airtag_sentry.geocode as geocode_module

    monkeypatch.setattr(geocode_module, "_MIN_INTERVAL_SECONDS", 0.0)


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


def test_reverse_geocode_returns_empty_result_on_missing_display_name(monkeypatch):
    mock_response = Mock()
    mock_response.json.return_value = {}
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr("requests.get", lambda *a, **k: mock_response)

    result = reverse_geocode(49.8728, 8.6512)

    assert result == GeocodeResult(address=None, poi_name=None)
