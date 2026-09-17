import datetime as dt

from airtag_sentry.db import OwnerLocation, Report
from airtag_sentry.movement import (
    MovementConfig,
    evaluate_away,
    evaluate_movement,
    haversine_distance,
    implied_speed_kmh,
    is_speed_outlier,
    owner_already_reunited,
)

CFG = MovementConfig(
    distance_threshold_meters=100,
    stillstand_hours=24,
    stillstand_movement_meters=15,
    alert_on_backfill=False,
    away_distance_threshold_meters=150,
    owner_location_max_age_minutes=60,
    max_speed_kmh=200,
)

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _report(hours_ago: float, lat: float, lon: float, accuracy: float | None = 5.0) -> Report:
    ts = NOW - dt.timedelta(hours=hours_ago)
    return Report(id=None, airtag_id="test", timestamp=ts, lat=lat, lon=lon, accuracy=accuracy, confidence=2)


def _owner_location(
    minutes_ago: float,
    lat: float,
    lon: float,
    device_id: str = "device-1",
    horizontal_accuracy: float | None = 5.0,
    relative_to: dt.datetime = NOW,
) -> OwnerLocation:
    recorded_at = relative_to - dt.timedelta(minutes=minutes_ago)
    return OwnerLocation(
        id=None,
        device_id=device_id,
        recorded_at=recorded_at,
        lat=lat,
        lon=lon,
        horizontal_accuracy=horizontal_accuracy,
    )


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
    assert evaluate_away(new, None, CFG) is None


def test_evaluate_away_returns_distance_when_far_and_close_in_time():
    new = _report(0, 52.51, 13.4)  # ~1.1km from the owner location below
    owner = _owner_location(5, 52.5, 13.4)
    distance = evaluate_away(new, owner, CFG)
    assert distance is not None
    assert distance > CFG.away_distance_threshold_meters


def test_evaluate_away_none_when_near_owner():
    new = _report(0, 52.5, 13.4)
    owner = _owner_location(5, 52.50005, 13.40005)  # a few meters of GPS noise
    assert evaluate_away(new, owner, CFG) is None


def test_evaluate_away_none_when_owner_location_far_in_time_from_report():
    new = _report(0, 52.51, 13.4)  # far from the owner location below
    owner = _owner_location(120, 52.5, 13.4)  # 120 min from the report, over the 60 min max age
    assert evaluate_away(new, owner, CFG) is None


def test_evaluate_away_uses_owner_reading_near_the_reports_own_timestamp():
    """Regression test: a delayed, crowd-sourced report timestamped hours in
    the past must be compared against the owner's location from around that
    same time, not whatever the owner's latest reading is by the time the
    report is processed - otherwise a report that only just arrived looks
    "far from the owner" purely because the owner has since moved on."""
    report_time = NOW - dt.timedelta(hours=4, minutes=30)
    new = Report(id=None, airtag_id="test", timestamp=report_time, lat=52.5, lon=13.4, accuracy=5.0, confidence=2)
    # Owner was right there when the report happened...
    owner_then = _owner_location(5, 52.5, 13.4, relative_to=report_time)
    assert evaluate_away(new, owner_then, CFG) is None
    # ...even though by "now" (when the report is actually processed) the
    # owner has moved far away - that later reading must not be used here.
    owner_now = _owner_location(5, 52.6, 13.6, relative_to=NOW)
    assert haversine_distance(52.5, 13.4, 52.6, 13.6) > CFG.away_distance_threshold_meters
    assert evaluate_away(new, owner_now, CFG) is None  # too far in time from report_time to be used


def test_evaluate_away_discounts_combined_accuracy_radius():
    # ~100m raw distance, entirely absorbed by the two points' noise margins.
    new = _report(0, 52.5, 13.4, accuracy=100.0)
    owner = _owner_location(5, 52.5009, 13.4, horizontal_accuracy=100.0)  # ~100m raw
    assert evaluate_away(new, owner, CFG) is None


def test_distance_threshold_alert_suppressed_by_low_accuracy_spike():
    """A single noisy/low-accuracy fix (e.g. a crowd-sourced relay far from
    the real position) must not read as real movement once its own reported
    uncertainty could explain the apparent jump."""
    prior = [_report(1, 52.5, 13.4, accuracy=5.0)]
    new = _report(0, 52.501, 13.4, accuracy=2000.0)  # ~111m raw move, but a 2km error radius
    assert evaluate_movement(new, prior, CFG) is None


def test_distance_threshold_alert_still_fires_for_real_move_despite_accuracy():
    prior = [_report(1, 52.5, 13.4, accuracy=5.0)]
    new = _report(0, 52.51, 13.4, accuracy=50.0)  # ~1.1km move, well beyond any plausible noise
    alert = evaluate_movement(new, prior, CFG)
    assert alert is not None
    assert alert.reason == "distance_threshold"


def test_owner_already_reunited_false_without_current_owner_location():
    new = _report(0, 52.5, 13.4)
    assert owner_already_reunited(new, None, CFG) is False


def test_owner_already_reunited_true_when_current_owner_location_is_near():
    new = _report(0, 52.5, 13.4)
    current = _owner_location(0, 52.50005, 13.40005)  # a few meters away, now
    assert owner_already_reunited(new, current, CFG) is True


def test_owner_already_reunited_false_when_current_owner_location_still_far():
    new = _report(0, 52.5, 13.4)
    current = _owner_location(0, 52.51, 13.4)  # still ~1.1km away, now
    assert owner_already_reunited(new, current, CFG) is False


def test_implied_speed_kmh_known_case():
    # ~24-28km apart (Berlin-Potsdam, see test_haversine_known_distance), 1h apart.
    t1 = NOW
    t2 = NOW + dt.timedelta(hours=1)
    speed = implied_speed_kmh(52.5163, 13.3777, t1, 52.4029, 13.0402, t2)
    assert 24 < speed < 28


def test_implied_speed_kmh_infinite_for_same_instant():
    assert implied_speed_kmh(52.5, 13.4, NOW, 52.6, 13.5, NOW) == float("inf")


def test_is_speed_outlier_false_without_a_baseline_report():
    new = _report(0, 52.5, 13.4)
    assert is_speed_outlier(new, None, CFG) is False


def test_is_speed_outlier_false_for_plausible_travel():
    # ~1.1km in 5 minutes is fast but not impossible (car in traffic).
    prior = _report(5 / 60, 52.5, 13.4)
    new = _report(0, 52.51, 13.4)
    assert is_speed_outlier(new, prior, CFG) is False


def test_is_speed_outlier_true_for_implausible_jump():
    # ~24-28km in under a minute - no AirTag moves at that speed.
    prior = _report(1 / 60, 52.5163, 13.3777)
    new = _report(0, 52.4029, 13.0402)
    assert is_speed_outlier(new, prior, CFG) is True
