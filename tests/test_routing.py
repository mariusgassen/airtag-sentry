from unittest.mock import Mock

import pytest

from airtag_sentry.routing import route_along_roads


@pytest.fixture(autouse=True)
def _no_rate_limit_and_cache(monkeypatch):
    # The 1 req/sec throttle is real-time and would make every test slow -
    # tests only concern themselves with the HTTP call/response mapping.
    # The lru_cache wrapping _fetch_route would also leak state between
    # tests that reuse the same point sequence - clear it each time.
    import airtag_sentry.routing as routing_module

    monkeypatch.setattr(routing_module, "_MIN_INTERVAL_SECONDS", 0.0)
    routing_module._fetch_route_cached.cache_clear()


def test_route_along_roads_returns_decoded_geometry(monkeypatch):
    mock_response = Mock()
    mock_response.json.return_value = {
        "code": "Ok",
        "routes": [
            {
                "geometry": {
                    "coordinates": [
                        [8.6512, 49.8728],
                        [8.6520, 49.8730],
                        [8.6530, 49.8735],
                    ]
                }
            }
        ],
    }
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr("requests.get", lambda *a, **k: mock_response)

    result = route_along_roads([(49.8728, 8.6512), (49.8735, 8.6530)])

    assert result == [(49.8728, 8.6512), (49.8730, 8.6520), (49.8735, 8.6530)]


def test_route_along_roads_returns_none_on_request_failure(monkeypatch):
    import requests

    def raise_error(*a, **k):
        raise requests.RequestException("boom")

    monkeypatch.setattr("requests.get", raise_error)

    assert route_along_roads([(49.8728, 8.6512), (49.8735, 8.6530)]) is None


def test_route_along_roads_returns_none_when_osrm_cannot_route(monkeypatch):
    mock_response = Mock()
    mock_response.json.return_value = {"code": "NoRoute", "routes": []}
    mock_response.raise_for_status = Mock()
    monkeypatch.setattr("requests.get", lambda *a, **k: mock_response)

    assert route_along_roads([(49.8728, 8.6512), (49.8735, 8.6530)]) is None


def test_route_along_roads_returns_none_for_a_single_point():
    assert route_along_roads([(49.8728, 8.6512)]) is None


def test_route_along_roads_returns_none_for_too_many_points():
    points = [(49.8728 + i * 0.0001, 8.6512) for i in range(101)]
    assert route_along_roads(points) is None
