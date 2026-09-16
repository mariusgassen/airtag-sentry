"""Pure "stay" clustering and place-label resolution logic.

No DB or network access here on purpose, so this stays trivially
unit-testable - same rationale as movement.py. Ported from
frontend/src/clustering.ts's clusterByProximity, now the single
implementation both AirTag reports and owner-device locations share (see
docs/superpowers/specs/2026-09-14-named-places-design.md for why this moved
server-side).
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Generic, TypeVar

from airtag_sentry.db import NamedPlace
from airtag_sentry.movement import haversine_distance

T = TypeVar("T")


@dataclasses.dataclass(frozen=True)
class Stay(Generic[T]):
    """A run of consecutive points that stayed within a radius of their
    anchor - see cluster_by_proximity. `points` preserves the input array's
    order (oldest-first for Report, newest-first for OwnerLocation - see
    CLAUDE.md's asymmetry), so callers know which end is "earliest"."""

    points: list[T]
    anchor: T


def cluster_by_proximity(
    points: list[T],
    get_lat_lon: Callable[[T], tuple[float, float]],
    radius_meters: float,
) -> list[Stay[T]]:
    """Groups consecutive points that stay within `radius_meters` of a shared
    anchor into one Stay. Anchor-based (not point-to-point): each point is
    compared to the anchor that started its stay, not the previous point, so
    slow drift can't chain a stay indefinitely away from where it started
    (same idea as movement.py's stillstand-anchor walk). Direction-agnostic -
    only neighboring array entries are ever compared, so this works the same
    for an oldest-first array (Report) or a newest-first one (OwnerLocation).
    """
    stays: list[Stay[T]] = []

    for point in points:
        current = stays[-1] if stays else None
        if current is not None:
            a_lat, a_lon = get_lat_lon(current.anchor)
            lat, lon = get_lat_lon(point)
            if haversine_distance(a_lat, a_lon, lat, lon) <= radius_meters:
                current.points.append(point)
                continue
        stays.append(Stay(points=[point], anchor=point))

    return stays


def match_place(lat: float, lon: float, places: list[NamedPlace]) -> NamedPlace | None:
    """Which geofence (if any) contains this point - smallest-radius match
    wins on overlap, so a small place nested inside a larger one (e.g. "Home
    office" inside "Home") takes priority for points inside the smaller one.
    """
    matches = [p for p in places if haversine_distance(lat, lon, p.lat, p.lon) <= p.radius_meters]
    if not matches:
        return None
    return min(matches, key=lambda p: p.radius_meters)


def resolve_label(
    place: NamedPlace | None,
    corrected_name: str | None,
    poi_name: str | None,
    address: str | None,
) -> str | None:
    """geofence name > user correction > cached POI name > cached address > None."""
    if place is not None:
        return place.name
    if corrected_name is not None:
        return corrected_name
    if poi_name is not None:
        return poi_name
    return address
