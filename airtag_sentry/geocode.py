"""Reverse geocoding for report/location markers, via OpenStreetMap's
Nominatim - the same OSM data already backing the map tiles, so no separate
API key/account is needed. Best-effort only: a failed or rate-limited lookup
returns an empty GeocodeResult rather than raising, since this is a "nice to
have" label for a marker that already has its lat/lon, never load-bearing.

Results are persisted by callers via db.py's geocoded_points table (the
poller, see tracker.py) rather than cached here - this module now only ever
makes the HTTP call, rate-limited.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
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


@dataclasses.dataclass(frozen=True)
class GeocodeResult:
    address: str | None  # Nominatim's display_name - the full formatted address.
    poi_name: str | None  # Nominatim's name - only present for a named POI (shop, amenity, ...).


def reverse_geocode(lat: float, lon: float, timeout: float = 5.0) -> GeocodeResult:
    global _last_call
    with _lock:
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
            body = resp.json()
        except (requests.RequestException, ValueError):
            return GeocodeResult(address=None, poi_name=None)

        return GeocodeResult(address=body.get("display_name"), poi_name=body.get("name"))


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
