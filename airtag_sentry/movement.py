"""Pure movement-detection logic: Haversine distance + threshold/stillstand rules.

No DB or network access here on purpose, so this stays trivially unit-testable.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import math

from airtag_sentry.db import OwnerLocation, Report

EARTH_RADIUS_METERS = 6_371_000.0


@dataclasses.dataclass(frozen=True)
class MovementConfig:
    distance_threshold_meters: float
    stillstand_hours: float
    stillstand_movement_meters: float
    alert_on_backfill: bool
    away_distance_threshold_meters: float
    owner_location_max_age_minutes: float


@dataclasses.dataclass(frozen=True)
class MovementAlert:
    reason: str  # "distance_threshold" | "stillstand_movement"
    distance_meters: float


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_METERS * c


def _stillstand_anchor(prior_reports: list[Report], cfg: MovementConfig) -> Report:
    """Walk backward through the stationary streak and return its earliest report."""
    anchor = prior_reports[-1]
    for report in reversed(prior_reports[:-1]):
        if haversine_distance(report.lat, report.lon, anchor.lat, anchor.lon) > cfg.distance_threshold_meters:
            break
        anchor = report
    return anchor


def evaluate_movement(
    new_report: Report,
    prior_reports: list[Report],
    cfg: MovementConfig,
) -> MovementAlert | None:
    """Decide whether `new_report` should trigger a movement alert.

    `prior_reports` must be sorted ascending and contain only reports already in
    the DB before `new_report` was inserted (i.e. not including `new_report` itself).
    """
    if not prior_reports:
        return None

    last = prior_reports[-1]
    distance = haversine_distance(new_report.lat, new_report.lon, last.lat, last.lon)

    if distance > cfg.distance_threshold_meters:
        return MovementAlert(reason="distance_threshold", distance_meters=distance)

    if distance > cfg.stillstand_movement_meters:
        anchor = _stillstand_anchor(prior_reports, cfg)
        stillstand_duration = new_report.timestamp - anchor.timestamp
        if stillstand_duration >= dt.timedelta(hours=cfg.stillstand_hours):
            return MovementAlert(reason="stillstand_movement", distance_meters=distance)

    return None


def evaluate_away(
    new_report: Report,
    owner_location: OwnerLocation | None,
    now: dt.datetime,
    cfg: MovementConfig,
) -> float | None:
    """Distance from the owner's last-known phone location if `new_report`
    qualifies as "moved without the owner nearby", else None.

    Only meaningful to call once a real movement alert has already fired for
    `new_report` - this doesn't independently decide whether the tag moved,
    only whether the owner was with it when it did.
    """
    if owner_location is None:
        return None
    if now - owner_location.recorded_at > dt.timedelta(minutes=cfg.owner_location_max_age_minutes):
        return None  # stale owner fix - don't classify off data that's too old to trust

    distance = haversine_distance(
        new_report.lat, new_report.lon, owner_location.lat, owner_location.lon
    )
    return distance if distance > cfg.away_distance_threshold_meters else None
