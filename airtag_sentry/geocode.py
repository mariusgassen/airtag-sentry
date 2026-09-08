"""Reverse geocoding for report/location markers, via OpenStreetMap's
Nominatim - the same OSM data already backing the map tiles, so no separate
API key/account is needed. Best-effort only: a failed or rate-limited lookup
returns None rather than raising, since this is a "nice to have" address
label for a marker that already has its lat/lon, never load-bearing.
"""

from __future__ import annotations

import threading
import time

import requests

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
# Nominatim's usage policy caps unauthenticated public use at 1 request/sec
# and requires an identifying User-Agent.
_MIN_INTERVAL_SECONDS = 1.0
_USER_AGENT = "AirTagSentry (self-hosted dashboard, reverse-geocode)"

_lock = threading.Lock()
_last_call = 0.0
# Small in-process cache, not persisted across restarts - reverse geocoding
# is a display nicety, not data worth a migration/table for.
_cache: dict[tuple[float, float], str | None] = {}
_CACHE_MAX = 500


def _cache_key(lat: float, lon: float) -> tuple[float, float]:
    # ~1m precision, so AirTag fixes a few meters apart share one lookup/
    # cache entry and one street-level address.
    return (round(lat, 5), round(lon, 5))


def reverse_geocode(lat: float, lon: float, timeout: float = 5.0) -> str | None:
    key = _cache_key(lat, lon)
    if key in _cache:
        return _cache[key]

    global _last_call
    with _lock:
        if key in _cache:  # re-check: another thread may have filled it while we waited on the lock
            return _cache[key]
        wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = requests.get(
                _NOMINATIM_URL,
                params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 18},
                headers={"User-Agent": _USER_AGENT},
                timeout=timeout,
            )
            _last_call = time.monotonic()
            resp.raise_for_status()
            address = resp.json().get("display_name")
        except (requests.RequestException, ValueError):
            address = None

        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[key] = address
        return address
