import datetime as dt

from airtag_sentry.db import OwnerLocation, Report
from airtag_sentry.movement import MovementConfig, evaluate_away, evaluate_movement, haversine_distance

CFG = MovementConfig(
    distance_threshold_meters=100,
    stillstand_hours=24,
    stillstand_movement_meters=15,
    alert_on_backfill=False,
    away_distance_threshold_meters=150,
    owner_location_max_age_minutes=60,
)

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _report(hours_ago: float, lat: float, lon: float) -> Report:
    ts = NOW - dt.timedelta(hours=hours_ago)
    return Report(id=None, airtag_id="test", timestamp=ts, lat=lat, lon=lon, accuracy=5.0, confidence=2)


def _owner_location(minutes_ago: float, lat: float, lon: float) -> OwnerLocation:
    recorded_at = NOW - dt.timedelta(minutes=minutes_ago)
    return OwnerLocation(id=None, recorded_at=recorded_at, lat=lat, lon=lon, horizontal_accuracy=5.0)


def test_haversine_zero_distance():
    assert haversine_distance(52.5, 13.4, 52.5, 13.4) == 0.0


def test_haversine_known_distance():
    # Berlin (Brandenburg Gate) to Potsdam (Sanssouci), roughly 24 km apart.
    distance = haversine_distance(52.5163, 13.3777, 52.4029, 13.0402)
    assert 24_000 < distance < 28_000


def test_no_alert_when_stationary():
    prior = [_report(1, 52.5, 13.4)]
    new = _report(0, 52.50005, 13.40005)  # a few meters of GPS noise
    assert evaluate_movement(new, prior, CFG) is None


def test_no_alert_with_no_history():
    new = _report(0, 52.5, 13.4)
    assert evaluate_movement(new, [], CFG) is None


def test_distance_threshold_alert():
    prior = [_report(1, 52.5, 13.4)]
    new = _report(0, 52.51, 13.4)  # ~1.1 km away, well over the 100m threshold
    alert = evaluate_movement(new, prior, CFG)
    assert alert is not None
    assert alert.reason == "distance_threshold"
    assert alert.distance_meters > CFG.distance_threshold_meters


def test_stillstand_movement_alert_after_long_stillstand():
    # Stationary streak lasting well over stillstand_hours, then a small move
    # that's below the main threshold but above stillstand_movement_meters.
    prior = [
        _report(48, 52.5, 13.4),
        _report(30, 52.50001, 13.40001),
        _report(10, 52.50001, 13.40001),
    ]
    new = _report(0, 52.5003, 13.4003)  # ~25m move
    alert = evaluate_movement(new, prior, CFG)
    assert alert is not None
    assert alert.reason == "stillstand_movement"


def test_no_stillstand_alert_if_not_stationary_long_enough():
    prior = [
        _report(2, 52.5, 13.4),
        _report(1, 52.50001, 13.40001),
    ]
    new = _report(0, 52.5003, 13.4003)  # same ~25m move, but stillstand only ~2h
    assert evaluate_movement(new, prior, CFG) is None


def test_no_stillstand_alert_below_movement_epsilon():
    prior = [_report(48, 52.5, 13.4), _report(30, 52.5, 13.4)]
    new = _report(0, 52.500005, 13.400005)  # sub-epsilon GPS noise
    assert evaluate_movement(new, prior, CFG) is None


def test_evaluate_away_none_without_owner_location():
    new = _report(0, 52.5, 13.4)
    assert evaluate_away(new, None, NOW, CFG) is None


def test_evaluate_away_returns_distance_when_far_and_fresh():
    new = _report(0, 52.51, 13.4)  # ~1.1km from the owner location below
    owner = _owner_location(5, 52.5, 13.4)
    distance = evaluate_away(new, owner, NOW, CFG)
    assert distance is not None
    assert distance > CFG.away_distance_threshold_meters


def test_evaluate_away_none_when_near_owner():
    new = _report(0, 52.5, 13.4)
    owner = _owner_location(5, 52.50005, 13.40005)  # a few meters of GPS noise
    assert evaluate_away(new, owner, NOW, CFG) is None


def test_evaluate_away_none_when_owner_location_stale():
    new = _report(0, 52.51, 13.4)  # far from the owner location below
    owner = _owner_location(120, 52.5, 13.4)  # 120 min old, over the 60 min max age
    assert evaluate_away(new, owner, NOW, CFG) is None
