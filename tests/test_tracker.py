import contextlib
import datetime as dt
import types

import pytest

from airtag_sentry import tracker
from airtag_sentry.db import AppSettings, OwnerLocation


@pytest.mark.parametrize(
    "status, expected",
    [
        (0b00_000000, "full"),
        (0b01_000000, "medium"),
        (0b10_000000, "low"),
        (0b11_000000, "very_low"),
        (0b11_101010, "very_low"),  # lower bits (device type etc.) don't affect the reading
    ],
)
def test_battery_level_decodes_top_two_bits_of_status_byte(status, expected):
    """FindMy.py's LocationReport.status is the raw status byte; battery is its
    top 2 bits, per the library's own scanner.BATTERY_LEVEL encoding (only
    exposed there as a property, not on LocationReport - see tracker.py)."""
    assert tracker._battery_level(status) == expected


def test_poll_once_still_updates_owner_devices_when_airtag_session_missing(monkeypatch):
    """Regression test: owner-device tracking and AirTag tracking are two
    independent Apple sessions (see owner_tracking.py's module docstring),
    but poll_once used to call restore_account() unconditionally as its very
    first line - so a user who connected only owner tracking (not AirTags)
    got a FileNotFoundError on every poll and owner-device locations were
    never recorded, contradicting the "entirely optional/independent"
    contract."""

    @contextlib.contextmanager
    def fake_get_conn(database_url):
        yield object()

    monkeypatch.setattr(tracker, "get_conn", fake_get_conn)
    monkeypatch.setattr(tracker, "get_settings", lambda conn: object())
    monkeypatch.setattr(tracker, "build_notifiers", lambda cfg, conn: [])
    monkeypatch.setattr(tracker, "build_ha_publisher", lambda cfg, conn: None)
    monkeypatch.setattr(tracker, "is_connected", lambda cfg: False)

    def fail_restore_account(cfg):
        raise AssertionError("restore_account() must not be called when no AirTag session exists")

    monkeypatch.setattr(tracker, "restore_account", fail_restore_account)

    def fail_list_airtags(conn):
        raise AssertionError("list_airtags() must not be called when no AirTag session exists")

    monkeypatch.setattr(tracker, "list_airtags", fail_list_airtags)

    calls = []
    monkeypatch.setattr(
        tracker, "_update_owner_devices", lambda cfg, conn, ha_publisher: calls.append((cfg, conn))
    )

    cfg = types.SimpleNamespace(database_url="unused")
    assert tracker.poll_once(cfg) is True

    assert len(calls) == 1
    assert calls[0][0] is cfg


def _settings(**overrides) -> AppSettings:
    defaults = dict(
        polling_interval_minutes=15,
        movement_distance_threshold_meters=100,
        movement_stillstand_hours=24,
        movement_stillstand_movement_meters=15,
        movement_alert_on_backfill=False,
        movement_away_distance_meters=150,
        owner_location_max_age_minutes=60,
        history_cluster_radius_meters=50,
        color_palette="pastel",
        notify_on_distance_threshold=True,
        notify_on_stillstand_movement=True,
        notify_on_moved_without_owner=True,
    )
    defaults.update(overrides)
    return AppSettings(**defaults)


@pytest.mark.parametrize(
    "reason, field",
    [
        ("distance_threshold", "notify_on_distance_threshold"),
        ("stillstand_movement", "notify_on_stillstand_movement"),
        ("moved_without_owner", "notify_on_moved_without_owner"),
    ],
)
def test_should_notify_reads_the_matching_settings_field(reason, field):
    assert tracker._should_notify(_settings(**{field: True}), reason) is True
    assert tracker._should_notify(_settings(**{field: False}), reason) is False


def _owner_location(recorded_at: dt.datetime) -> OwnerLocation:
    return OwnerLocation(
        id=1, device_id="d1", recorded_at=recorded_at, lat=52.5, lon=13.4, horizontal_accuracy=5.0
    )


def test_owner_location_for_away_check_skips_live_fetch_when_reading_is_fresh(monkeypatch):
    now = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
    fresh = _owner_location(now - dt.timedelta(minutes=5))
    monkeypatch.setattr(tracker, "primary_owner_device_location_near", lambda conn, ts: fresh)

    def fail_fetch(cfg, conn):
        raise AssertionError("must not do a live Apple fetch when the cached reading is fresh enough")

    monkeypatch.setattr(tracker, "fetch_owner_device_locations", fail_fetch)

    result = tracker._owner_location_for_away_check(cfg=object(), conn=object(), near_timestamp=now, max_age_minutes=60)

    assert result is fresh


def test_owner_location_for_away_check_does_a_live_fetch_when_reading_is_stale(monkeypatch):
    now = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
    stale = _owner_location(now - dt.timedelta(hours=2))
    refreshed = _owner_location(now - dt.timedelta(minutes=1))

    lookups = [stale, refreshed]
    monkeypatch.setattr(tracker, "primary_owner_device_location_near", lambda conn, ts: lookups.pop(0))
    monkeypatch.setattr(tracker, "fetch_owner_device_locations", lambda cfg, conn: [refreshed])
    recorded = []
    monkeypatch.setattr(tracker, "record_owner_device_location", lambda conn, loc: recorded.append(loc))

    result = tracker._owner_location_for_away_check(cfg=object(), conn=object(), near_timestamp=now, max_age_minutes=60)

    assert recorded == [refreshed]
    assert result is refreshed


def test_owner_location_for_away_check_falls_back_to_stale_reading_on_fetch_failure(monkeypatch):
    now = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
    stale = _owner_location(now - dt.timedelta(hours=2))
    monkeypatch.setattr(tracker, "primary_owner_device_location_near", lambda conn, ts: stale)

    def fail_fetch(cfg, conn):
        raise RuntimeError("Apple session expired")

    monkeypatch.setattr(tracker, "fetch_owner_device_locations", fail_fetch)

    result = tracker._owner_location_for_away_check(cfg=object(), conn=object(), near_timestamp=now, max_age_minutes=60)

    assert result is stale


def test_poll_once_skips_and_returns_false_when_already_running(monkeypatch):
    """A manual "refresh now" (web/app.py's /api/poll-now) and the scheduled
    background poll (scheduler.py) call poll_once() from different threads
    with no other coordination - an overlapping run must no-op rather than
    interleave writes to the same Apple session file or double-fire alerts."""

    def fail_get_conn(database_url):
        raise AssertionError("poll_once() must not do any work while the lock is held")

    monkeypatch.setattr(tracker, "get_conn", fail_get_conn)

    cfg = types.SimpleNamespace(database_url="unused")
    tracker._poll_lock.acquire()
    try:
        assert tracker.poll_once(cfg) is False
    finally:
        tracker._poll_lock.release()
