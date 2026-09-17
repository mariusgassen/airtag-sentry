"""Reverse geocoding for report/location markers, via OpenStreetMap's
Nominatim - the same OSM data already backing the map tiles, so no separate
API key/account is needed. Best-effort only: a failed or rate-limited lookup
returns an empty GeocodeResult rather than raising, since this is a "nice to
have" label for a marker that already has its lat/lon, never load-bearing.

Results are persisted by callers via db.py's geocoded_points table (the
poller, see tracker.py) rather than cached here - this module now only ever
makes the HTTP call, rate-limited. get_or_fetch_geocode() below is the
cache-aware entry point every *request-time* caller (the /api/geocode route,
the Telegram bot) should use instead of calling reverse_geocode() directly,
so those paths get the same persisted cache tracker.py's poller already
benefits from - both for latency (skip the live Nominatim round-trip
entirely on a cache hit) and consistency (Nominatim only; the geofence/
correction priority chain lives in stays.py and is layered on top by web/app.py).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import threading
import time
from typing import Any

import psycopg
import requests

from airtag_sentry.db import get_geocoded_point, store_geocoded_point

_NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
_NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy caps unauthenticated public use at 1 request/sec
# and requires an identifying User-Agent.
_MIN_INTERVAL_SECONDS = 1.0
_USER_AGENT = "AirTagSentry (self-hosted dashboard, reverse-geocode)"
_SEARCH_RESULT_LIMIT = 5

_lock = threading.Lock()
_last_call = 0.0


@dataclasses.dataclass(frozen=True)
class GeocodeResult:
    address: str | None  # Compact "Straße Hausnummer, Ort" (see _compact_address), or Nominatim's full display_name as a fallback.
    poi_name: str | None  # Nominatim's name - only present for a named POI (shop, amenity, ...).


@dataclasses.dataclass(frozen=True)
class GeocodeSearchResult:
    display_name: str
    lat: float
    lon: float


def _rate_limited_get(url: str, params: dict[str, Any], timeout: float) -> Any | None:
    """Shared rate limiter for both Nominatim endpoints - they're the same
    host under the same 1 request/sec usage-policy cap, so reverse and
    forward lookups queue behind one shared `_last_call`/`_lock` rather than
    each getting their own budget."""
    global _last_call
    with _lock:
        wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = requests.get(url, params=params, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
            _last_call = time.monotonic()
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError):
            return None


def _compact_address(address: dict[str, str] | None) -> str | None:
    """Nominatim's display_name crams every administrative level - suburb,
    city, county, state, postcode, country - into one comma list, most of it
    redundant next to a marker that already has a name/label above it and a
    lat/lon behind it. Build a short "Straße Hausnummer, Ort" line instead
    from the structured breakdown (addressdetails=1), falling back through
    the locality types Nominatim uses depending on how built-up the area is
    (city/town/village/...), and gracefully to just one part - or None -
    when a component is missing (e.g. open countryside has no street)."""
    if not address:
        return None
    road = address.get("road") or address.get("pedestrian") or address.get("footway") or address.get("cycleway")
    house_number = address.get("house_number")
    street_line = f"{road} {house_number}" if road and house_number else road
    locality = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("suburb")
        or address.get("county")
    )
    parts = [p for p in (street_line, locality) if p]
    return ", ".join(parts) or None


def reverse_geocode(lat: float, lon: float, timeout: float = 5.0) -> GeocodeResult:
    body = _rate_limited_get(
        _NOMINATIM_REVERSE_URL,
        {"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1},
        timeout,
    )
    if body is None:
        return GeocodeResult(address=None, poi_name=None)
    address = _compact_address(body.get("address")) or body.get("display_name")
    return GeocodeResult(address=address, poi_name=body.get("name"))


def search_address(query: str, timeout: float = 5.0) -> list[GeocodeSearchResult]:
    """Forward geocoding for the "Ort hinzufügen" address search (dashboard
    only, see CLAUDE.md's UI-first constraint) - lets a user find a geofence
    center by typing an address instead of only panning the map or relying
    on the browser's current position. Best-effort like reverse_geocode: a
    failed or rate-limited lookup returns an empty list rather than raising."""
    body = _rate_limited_get(
        _NOMINATIM_SEARCH_URL, {"format": "jsonv2", "q": query, "limit": _SEARCH_RESULT_LIMIT}, timeout
    )
    if not body:
        return []
    return [
        GeocodeSearchResult(display_name=item["display_name"], lat=float(item["lat"]), lon=float(item["lon"]))
        for item in body
    ]


def format_location_line(
    lat: float, lon: float, timestamp: dt.datetime, address: str | None, tz: dt.tzinfo
) -> str:
    """Timestamp + optional reverse-geocoded address + a Google Maps link, one
    per line - the shared "where/when" tail for anything telling a human
    about a location (telegram_bot.py's /where reply, tracker.py's movement
    alerts). Callers fetch `address` themselves (via get_or_fetch_geocode())
    so this stays a pure formatter.

    `timestamp` comes from Postgres as a UTC-aware datetime (TIMESTAMPTZ) -
    always convert it to the caller's `tz` (Config.display_timezone) before
    formatting, or the printed clock time is UTC mislabeled as local."""
    lines = [timestamp.astimezone(tz).strftime("%d.%m.%Y %H:%M")]
    if address:
        lines.append(address)
    lines.append(f"https://maps.google.com/?q={lat},{lon}")
    return "\n".join(lines)


def get_or_fetch_geocode(conn: psycopg.Connection, lat: float, lon: float) -> GeocodeResult:
    """Cache-aware wrapper for request-time geocode lookups (the /api/geocode
    route, the Telegram bot) - mirrors tracker.py's _geocode_new_points'
    "only cache a successful lookup" behavior, just for a single point rather
    than a batch. Checks the geocoded_points table first so a coordinate the
    poller (or an earlier request) already resolved never triggers another
    live, rate-limited Nominatim call."""
    cached = get_geocoded_point(conn, lat, lon)
    if cached is not None:
        return GeocodeResult(address=cached.address, poi_name=cached.poi_name)

    result = reverse_geocode(lat, lon)
    if result.address is not None or result.poi_name is not None:
        store_geocoded_point(conn, lat, lon, result.address, result.poi_name)
    return result
