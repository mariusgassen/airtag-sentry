import requests

from airtag_sentry import geocode


class _FakeResponse:
    def __init__(self, payload=None, status=200):
        self._payload = payload or {}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _reset(monkeypatch):
    monkeypatch.setattr(geocode, "_cache", {})
    monkeypatch.setattr(geocode, "_last_call", 0.0)
    # Skip Nominatim's real 1req/s throttle in tests.
    monkeypatch.setattr(geocode, "_MIN_INTERVAL_SECONDS", 0.0)


def test_reverse_geocode_returns_address(monkeypatch):
    _reset(monkeypatch)
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append((url, params))
        return _FakeResponse({"display_name": "Alexanderplatz, Berlin"})

    monkeypatch.setattr(geocode.requests, "get", fake_get)

    assert geocode.reverse_geocode(52.5219, 13.4132) == "Alexanderplatz, Berlin"
    assert len(calls) == 1


def test_reverse_geocode_caches_by_rounded_coordinates(monkeypatch):
    _reset(monkeypatch)
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append((url, params))
        return _FakeResponse({"display_name": "Alexanderplatz, Berlin"})

    monkeypatch.setattr(geocode.requests, "get", fake_get)

    geocode.reverse_geocode(52.52190, 13.41320)
    geocode.reverse_geocode(52.521900001, 13.413200001)  # rounds to the same cache key

    assert len(calls) == 1


def test_reverse_geocode_returns_none_on_request_failure(monkeypatch):
    _reset(monkeypatch)

    def fake_get(url, params, headers, timeout):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(geocode.requests, "get", fake_get)

    assert geocode.reverse_geocode(52.5, 13.4) is None


def test_reverse_geocode_returns_none_on_missing_display_name(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setattr(geocode.requests, "get", lambda *a, **k: _FakeResponse({}))

    assert geocode.reverse_geocode(0.0, 0.0) is None
