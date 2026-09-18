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
    max_speed_kmh: float


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


def _accuracy_adjusted_distance(distance: float, accuracy1: float | None, accuracy2: float | None) -> float:
    """Discount a raw haversine distance by the two points' combined
    position-uncertainty radii, so a single noisy/low-accuracy fix can't look
    like real movement that's actually within both points' error margins.
    Missing accuracy (None) gets no discount, never a more permissive read
    than before this existed.
    """
    slack = (accuracy1 or 0.0) + (accuracy2 or 0.0)
    return max(distance - slack, 0.0)


def is_object_displaced(
    lat1: float,
    lon1: float,
    accuracy1: float | None,
    lat2: float,
    lon2: float,
    accuracy2: float | None,
    cfg: MovementConfig,
) -> bool:
    """Whether two readings of the *same tracked object's own position*
    (not object-vs-owner) differ enough to count as real movement rather
    than GPS/BLE noise - the same accuracy-adjusted distance_threshold_meters
    check evaluate_movement uses for an AirTag's own reports, generalized to
    plain lat/lon/accuracy so it also works for an owner device's own two
    readings (see tracker._evaluate_device_away_alerts).

    This is the classification signal behind CLAUDE.md's "you left it" vs
    "it left you" constraint: called only once an object is already known to
    be far from the primary owner device, to decide whether the object
    itself moved there on its own (alert as autonomous movement - the actual
    signal this app exists to catch) or stayed put while the owner moved
    away from it (alert as left-behind - routine, not urgent).
    """
    raw_distance = haversine_distance(lat1, lon1, lat2, lon2)
    distance = _accuracy_adjusted_distance(raw_distance, accuracy1, accuracy2)
    return distance > cfg.distance_threshold_meters


def implied_speed_kmh(lat1: float, lon1: float, t1: dt.datetime, lat2: float, lon2: float, t2: dt.datetime) -> float:
    """Average speed implied by traveling between two points/timestamps, in
    km/h. `math.inf` for two points at (or effectively at) the same instant -
    any nonzero distance there is an infinite implied speed, not a division
    error to hide.
    """
    elapsed_hours = abs((t2 - t1).total_seconds()) / 3600
    if elapsed_hours <= 0:
        return math.inf
    distance_km = haversine_distance(lat1, lon1, lat2, lon2) / 1000
    return distance_km / elapsed_hours


def is_speed_outlier(new_report: Report, prior_report: Report | None, cfg: MovementConfig) -> bool:
    """Whether `new_report`'s implied travel speed from `prior_report` (the
    last *kept*, i.e. already-not-an-outlier, report) is physically
    implausible for an AirTag - a bad crowd-sourced Bluetooth relay, not real
    movement. `prior_report` being None (first-ever report) is never an
    outlier: there's nothing to compare against.
    """
    if prior_report is None:
        return False
    speed = implied_speed_kmh(
        prior_report.lat, prior_report.lon, prior_report.timestamp, new_report.lat, new_report.lon, new_report.timestamp
    )
    return speed > cfg.max_speed_kmh


def _stillstand_anchor(prior_reports: list[Report], cfg: MovementConfig) -> Report:
    """Walk backward through the stationary streak and return its earliest report."""
    anchor = prior_reports[-1]
    for report in reversed(prior_reports[:-1]):
        step_distance = _accuracy_adjusted_distance(
            haversine_distance(report.lat, report.lon, anchor.lat, anchor.lon), report.accuracy, anchor.accuracy
        )
        if step_distance > cfg.distance_threshold_meters:
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
    raw_distance = haversine_distance(new_report.lat, new_report.lon, last.lat, last.lon)
    distance = _accuracy_adjusted_distance(raw_distance, new_report.accuracy, last.accuracy)

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
    cfg: MovementConfig,
) -> float | None:
    """Distance from the primary owner device's location around the same time
    as `new_report`, if `new_report` qualifies as "moved without the owner
    nearby", else None.

    Only meaningful to call once a real movement alert has already fired for
    `new_report` - this doesn't independently decide whether the tag moved,
    only whether the owner was with it when it did. `owner_location` is
    always the *primary* tracked device (see owner_tracking.py) - other
    tracked-but-not-primary devices don't factor into this at all, so there's
    exactly one definite answer to "where does the app think the owner is."

    `owner_location` must be the primary device's reading closest in time to
    `new_report.timestamp` (see db.py's `primary_owner_device_location_near`),
    not simply its latest-ever reading - AirTag reports are crowd-sourced and
    can arrive with real delay, so comparing a late-arriving report's
    position against the owner's *current* position would compare two
    different points in time and misclassify a coincidence as "away" (or vice
    versa).
    """
    if owner_location is None:
        return None
    time_delta = abs(new_report.timestamp - owner_location.recorded_at)
    if time_delta > dt.timedelta(minutes=cfg.owner_location_max_age_minutes):
        return None  # no owner reading close enough in time to trust the comparison

    raw_distance = haversine_distance(
        new_report.lat, new_report.lon, owner_location.lat, owner_location.lon
    )
    distance = _accuracy_adjusted_distance(raw_distance, new_report.accuracy, owner_location.horizontal_accuracy)
    return distance if distance > cfg.away_distance_threshold_meters else None


def owner_already_reunited(
    new_report: Report, current_owner_location: OwnerLocation | None, cfg: MovementConfig
) -> bool:
    """Whether the owner's *current* location - not time-matched to
    `new_report` the way `evaluate_away`'s comparison is - is already back
    near where `new_report` places the tag.

    AirTag reports arrive via Apple's crowd-sourced network and owner-device
    polls both carry real wall-clock delay, so by the time a "moved without
    you" alert is actually about to be sent, the owner may have already
    reunited with the tag even though the alert was correctly true at the
    report's own timestamp. Only meaningful to call after `evaluate_away`
    has already flagged `new_report` - this doesn't reconsider whether the
    tag moved, only whether notifying about it is still useful.
    """
    if current_owner_location is None:
        return False
    raw_distance = haversine_distance(
        new_report.lat, new_report.lon, current_owner_location.lat, current_owner_location.lon
    )
    distance = _accuracy_adjusted_distance(
        raw_distance, new_report.accuracy, current_owner_location.horizontal_accuracy
    )
    return distance <= cfg.away_distance_threshold_meters


def evaluate_device_away(
    device_location: OwnerLocation,
    primary_location: OwnerLocation | None,
    cfg: MovementConfig,
) -> float | None:
    """Device counterpart to evaluate_away() - the same "how far from the
    primary owner device" check, but for a non-primary owner device's own
    location instead of an AirTag report (see tracker._evaluate_device_away_alerts,
    CLAUDE.md's AirTag/device parity constraint). `primary_location` must be
    the primary device's reading closest in time to `device_location.recorded_at`
    (db.primary_owner_device_location_near), for the same reason evaluate_away()
    needs a time-matched reading rather than whatever's most recent.
    """
    if primary_location is None:
        return None
    time_delta = abs(device_location.recorded_at - primary_location.recorded_at)
    if time_delta > dt.timedelta(minutes=cfg.owner_location_max_age_minutes):
        return None

    raw_distance = haversine_distance(
        device_location.lat, device_location.lon, primary_location.lat, primary_location.lon
    )
    distance = _accuracy_adjusted_distance(
        raw_distance, device_location.horizontal_accuracy, primary_location.horizontal_accuracy
    )
    return distance if distance > cfg.away_distance_threshold_meters else None


def device_already_reunited(
    device_location: OwnerLocation,
    current_primary_location: OwnerLocation | None,
    cfg: MovementConfig,
) -> bool:
    """Device counterpart to owner_already_reunited() - whether the primary
    device's *current* location is already back near where `device_location`
    (the non-primary device's own last known position) puts it, so a "you
    left without X" push that's about to fire is already stale.
    """
    if current_primary_location is None:
        return False
    raw_distance = haversine_distance(
        device_location.lat, device_location.lon, current_primary_location.lat, current_primary_location.lon
    )
    distance = _accuracy_adjusted_distance(
        raw_distance, device_location.horizontal_accuracy, current_primary_location.horizontal_accuracy
    )
    return distance <= cfg.away_distance_threshold_meters
