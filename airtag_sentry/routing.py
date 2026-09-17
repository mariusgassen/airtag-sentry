"""Road-following trail geometry, via OSRM's public routing API - same "reuse
free OSM infra, no API key" spirit as geocode.py's Nominatim calls. Turns an
ordered list of report/stay positions into a route that follows actual
streets, instead of the straight lines directly connecting them.

Best-effort only, like geocode.py: a failed, rate-limited, or oversized
request returns None rather than raising, so callers (the /api/route route)
fall back to the original straight-line positions - a routed trail is a
cosmetic improvement over the raw points, never load-bearing.
"""

from __future__ import annotations

import functools
import math
import threading
import time

import requests

_OSRM_ROUTE_URL = "https://router.project-osrm.org/route/v1/driving/{coords}"
_MIN_INTERVAL_SECONDS = 1.0
_USER_AGENT = "AirTagSentry (self-hosted dashboard, road-following trail)"
# OSRM's public demo server rejects requests with too many coordinates;
# a trail this long is also unreadable as a single route line anyway - the
# straight-line fallback is a fine substitute at that point. Applied after
# _dedupe_consecutive, not to the raw point count.
_MAX_POINTS = 100
# A device sitting still still gets a new location row every poll (see
# owner_tracking.py) - unlike an AirTag's sparser, crowd-sourced Find My
# reports, an owner device's history is routinely mostly near-duplicate
# points, which blew past _MAX_POINTS on stationary noise alone and fell
# back to a straight line far more often than for an AirTag (see CLAUDE.md's
# AirTag/device parity constraint - this dedup is what keeps that parity in
# practice, not just in the code path).
_DEDUPE_MIN_DISTANCE_METERS = 25.0

_lock = threading.Lock()
_last_call = 0.0


def _haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    earth_radius_m = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * earth_radius_m * math.asin(math.sqrt(h))


def _dedupe_consecutive(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Collapses a run of consecutive points that are effectively the same
    spot (GPS jitter while stationary) down to the first of the run."""
    if not points:
        return points
    deduped = [points[0]]
    for point in points[1:]:
        if _haversine_meters(deduped[-1], point) >= _DEDUPE_MIN_DISTANCE_METERS:
            deduped.append(point)
    return deduped


def _fetch_route(points: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...] | None:
    """Cached on the exact ordered point sequence - the frontend re-requests
    the same trail on every detail-view open/tab switch without new data in
    between, so this avoids hitting OSRM again for an unchanged trail."""
    global _last_call
    coords = ";".join(f"{lon},{lat}" for lat, lon in points)
    url = _OSRM_ROUTE_URL.format(coords=coords)
    with _lock:
        wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = requests.get(
                url,
                params={"overview": "full", "geometries": "geojson"},
                headers={"User-Agent": _USER_AGENT},
                timeout=10.0,
            )
            _last_call = time.monotonic()
            resp.raise_for_status()
            body = resp.json()
        except (requests.RequestException, ValueError):
            return None
    if body.get("code") != "Ok" or not body.get("routes"):
        return None
    try:
        coordinates = body["routes"][0]["geometry"]["coordinates"]
        return tuple((lat, lon) for lon, lat in coordinates)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


_fetch_route_cached = functools.lru_cache(maxsize=64)(_fetch_route)


def route_along_roads(points: list[tuple[float, float]]) -> list[tuple[float, float]] | None:
    """Ordered (lat, lon) waypoints -> the road-following geometry OSRM routes
    through them, in the same order. None if there's nothing to route (fewer
    than 2 distinct points after dedup), the trail is too long to route, or
    the request fails."""
    if len(points) < 2:
        return None
    deduped = _dedupe_consecutive(points)
    if len(deduped) < 2 or len(deduped) > _MAX_POINTS:
        return None
    result = _fetch_route_cached(tuple(deduped))
    return list(result) if result is not None else None
