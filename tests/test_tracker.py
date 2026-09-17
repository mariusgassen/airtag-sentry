import contextlib
import datetime as dt
import os
import types

import psycopg
import pytest

from airtag_sentry import tracker
from airtag_sentry.db import (
    AppSettings,
    GeocodedPoint,
    OwnerLocation,
    get_conn,
    get_geocoded_point,
    list_owner_devices,
    record_owner_device_location,
    set_owner_device_away_alert_enabled,
    set_owner_device_enabled,
    set_owner_device_primary,
    store_geocoded_point,
    upsert_owner_devices,
)
from airtag_sentry.geocode import GeocodeResult
from airtag_sentry.migrate import upgrade_to_head

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://airtag:airtag@localhost:5432/airtag_sentry_test"
)
os.environ.setdefault("TEST_DATABASE_URL", TEST_DATABASE_URL)


@pytest.fixture()
def conn():
    """Real Postgres connection, test_db.py-style: this module's geocoding
    tests exercise genuine DB round-tripping (geocoded_points) rather than
    just call wiring, so a mock connection wouldn't do."""
    try:
        with get_conn(TEST_DATABASE_URL) as connection:
            upgrade_to_head()
            with connection.cursor() as cur:
                cur.execute(
                    "TRUNCATE geocoded_points, owner_devices, owner_device_locations, alerts "
                    "RESTART IDENTITY CASCADE"
                )
            connection.commit()
            yield connection
    except psycopg.OperationalError:
        pytest.skip(f"Postgres not reachable at {TEST_DATABASE_URL}; start it to run this test.")


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
    monkeypatch.setattr(tracker, "_evaluate_device_away_alerts", lambda cfg, conn, notifiers, settings: None)

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
        movement_max_speed_kmh=200,
        history_cluster_radius_meters=50,
        color_palette="pastel",
        map_tile_provider="auto",
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


def test_poll_once_geocodes_newly_inserted_report_coordinates(monkeypatch, conn):
    # Uses the real conn fixture (test_db.py-style) since this is exercising
    # genuine DB round-tripping (geocoded_points), not just call wiring.
    from airtag_sentry import tracker as tracker_module

    monkeypatch.setattr(tracker_module, "get_conn", lambda _url: conn)
    monkeypatch.setattr(tracker_module, "is_connected", lambda _cfg: False)  # skip the AirTag session entirely
    monkeypatch.setattr(tracker_module, "fetch_owner_device_locations", lambda _cfg, _conn: [])
    monkeypatch.setattr(tracker_module, "build_notifiers", lambda _cfg, _conn: [])
    monkeypatch.setattr(tracker_module, "build_ha_publisher", lambda _cfg, _conn: None)

    geocode_calls = []

    def fake_reverse_geocode(lat, lon):
        geocode_calls.append((lat, lon))
        return GeocodeResult(address="12 Main St", poi_name="REWE")

    monkeypatch.setattr(tracker_module, "reverse_geocode", fake_reverse_geocode)

    tracker_module._geocode_new_points(conn, [(49.8728, 8.6512), (49.8728, 8.6512)])

    # Same rounded coordinate twice -> one real geocode call, cached after that.
    assert geocode_calls == [(49.8728, 8.6512)]
    assert get_geocoded_point(conn, 49.8728, 8.6512) == GeocodedPoint(
        lat_rounded=49.8728, lon_rounded=8.6512, address="12 Main St", poi_name="REWE"
    )


def test_geocode_new_points_skips_already_cached_coordinates(monkeypatch, conn):
    from airtag_sentry import tracker as tracker_module

    store_geocoded_point(conn, 49.8728, 8.6512, "Cached Address", "Cached POI")

    def fail_if_called(*_a, **_k):
        raise AssertionError("reverse_geocode should not be called for an already-cached coordinate")

    monkeypatch.setattr(tracker_module, "reverse_geocode", fail_if_called)

    tracker_module._geocode_new_points(conn, [(49.8728, 8.6512)])


# --- _evaluate_device_away_alerts ---
#
# Real Postgres (test_db.py-style): this exercises genuine DB round-tripping
# (owner_devices/owner_device_locations/alerts), not just call wiring.


def _setup_primary_and_device(conn, device_id="laptop", away_alert_enabled=True):
    seen_at = dt.datetime(2026, 1, 1, 7, 0, tzinfo=dt.timezone.utc)
    upsert_owner_devices(
        conn,
        [
            {"id": "primary", "name": "iPhone", "device_type": "iPhone"},
            {"id": device_id, "name": "MacBook", "device_type": "Mac"},
        ],
        seen_at=seen_at,
    )
    set_owner_device_enabled(conn, "primary", True)
    set_owner_device_primary(conn, "primary")
    set_owner_device_enabled(conn, device_id, True)
    set_owner_device_away_alert_enabled(conn, device_id, away_alert_enabled)


def _record(conn, device_id: str, recorded_at: dt.datetime, lat: float, lon: float) -> OwnerLocation:
    return record_owner_device_location(
        conn,
        OwnerLocation(id=None, device_id=device_id, recorded_at=recorded_at, lat=lat, lon=lon, horizontal_accuracy=5.0),
    )


def _fail_fetch(cfg, conn):
    raise AssertionError("must not do a live Apple fetch - all test readings are already fresh enough")


def _fake_cfg() -> types.SimpleNamespace:
    return types.SimpleNamespace(display_timezone=dt.timezone.utc)


def test_evaluate_device_away_alerts_noop_without_primary_device(monkeypatch, conn):
    from airtag_sentry import tracker as tracker_module

    upsert_owner_devices(
        conn, [{"id": "laptop", "name": "MacBook", "device_type": "Mac"}], seen_at=dt.datetime.now(dt.timezone.utc)
    )
    set_owner_device_enabled(conn, "laptop", True)
    set_owner_device_away_alert_enabled(conn, "laptop", True)
    monkeypatch.setattr(tracker_module, "fetch_owner_device_locations", _fail_fetch)
    notified = []
    monkeypatch.setattr(tracker_module, "notify_all", lambda notifiers, title, message: notified.append((title, message)))

    tracker_module._evaluate_device_away_alerts(object(), conn, [], _settings())

    assert notified == []
    assert list_owner_devices(conn)  # sanity: the device still exists, just no primary


def test_evaluate_device_away_alerts_skips_device_not_opted_in(monkeypatch, conn):
    from airtag_sentry import tracker as tracker_module

    _setup_primary_and_device(conn, away_alert_enabled=False)
    monkeypatch.setattr(tracker_module, "fetch_owner_device_locations", _fail_fetch)
    notified = []
    monkeypatch.setattr(tracker_module, "notify_all", lambda notifiers, title, message: notified.append((title, message)))

    now = dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.timezone.utc)
    _record(conn, "primary", now, 52.5, 13.4)
    _record(conn, "laptop", now, 52.6, 13.5)  # far away, but not opted in

    tracker_module._evaluate_device_away_alerts(object(), conn, [], _settings())

    assert notified == []


def test_evaluate_device_away_alerts_skips_primary_device_itself(monkeypatch, conn):
    from airtag_sentry import tracker as tracker_module

    _setup_primary_and_device(conn)
    set_owner_device_away_alert_enabled(conn, "primary", True)  # shouldn't matter - primary is never evaluated
    monkeypatch.setattr(tracker_module, "fetch_owner_device_locations", _fail_fetch)
    notified = []
    monkeypatch.setattr(tracker_module, "notify_all", lambda notifiers, title, message: notified.append((title, message)))

    now = dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.timezone.utc)
    _record(conn, "primary", now, 52.5, 13.4)

    tracker_module._evaluate_device_away_alerts(object(), conn, [], _settings())

    assert notified == []


def test_evaluate_device_away_alerts_skips_first_ever_reading_by_default(monkeypatch, conn):
    """Mirrors AirTags' own movement_alert_on_backfill guard - a device's very
    first-ever recorded location shouldn't immediately alert just because
    away_alert_enabled was switched on while it happened to be elsewhere."""
    from airtag_sentry import tracker as tracker_module

    _setup_primary_and_device(conn)
    monkeypatch.setattr(tracker_module, "fetch_owner_device_locations", _fail_fetch)
    notified = []
    monkeypatch.setattr(tracker_module, "notify_all", lambda notifiers, title, message: notified.append((title, message)))

    now = dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.timezone.utc)
    _record(conn, "primary", now, 52.5, 13.4)
    _record(conn, "laptop", now, 52.6, 13.5)  # first-ever reading, already far away

    tracker_module._evaluate_device_away_alerts(object(), conn, [], _settings(movement_alert_on_backfill=False))

    assert notified == []


def test_evaluate_device_away_alerts_still_records_when_notify_setting_off(monkeypatch, conn):
    """notify_on_moved_without_owner only gates the push, same as _poll_airtag -
    the alert itself is still recorded either way."""
    from airtag_sentry import tracker as tracker_module

    _setup_primary_and_device(conn)
    monkeypatch.setattr(tracker_module, "fetch_owner_device_locations", _fail_fetch)
    notified = []
    monkeypatch.setattr(tracker_module, "notify_all", lambda notifiers, title, message: notified.append((title, message)))

    t0 = dt.datetime(2026, 1, 1, 8, 0, tzinfo=dt.timezone.utc)
    t1 = dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.timezone.utc)
    _record(conn, "primary", t0, 52.5, 13.4)
    _record(conn, "laptop", t0, 52.5, 13.4)
    _record(conn, "primary", t1, 52.5, 13.4)
    _record(conn, "laptop", t1, 52.51, 13.4)

    tracker_module._evaluate_device_away_alerts(
        object(), conn, [], _settings(notify_on_moved_without_owner=False)
    )

    assert notified == []
    with conn.cursor() as cur:
        cur.execute("SELECT reason, owner_device_id FROM alerts")
        assert cur.fetchall() == [("moved_without_owner", "laptop")]


def test_evaluate_device_away_alerts_fires_on_new_away_transition(monkeypatch, conn):
    from airtag_sentry import tracker as tracker_module

    _setup_primary_and_device(conn)
    monkeypatch.setattr(tracker_module, "fetch_owner_device_locations", _fail_fetch)
    monkeypatch.setattr(tracker_module, "reverse_geocode", lambda lat, lon: GeocodeResult(address=None, poi_name=None))
    notified = []
    monkeypatch.setattr(tracker_module, "notify_all", lambda notifiers, title, message: notified.append((title, message)))

    t0 = dt.datetime(2026, 1, 1, 8, 0, tzinfo=dt.timezone.utc)
    t1 = dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.timezone.utc)
    _record(conn, "primary", t0, 52.5, 13.4)
    _record(conn, "laptop", t0, 52.5, 13.4)  # together
    _record(conn, "primary", t1, 52.5, 13.4)  # primary stays
    _record(conn, "laptop", t1, 52.51, 13.4)  # laptop now ~1.1km away

    tracker_module._evaluate_device_away_alerts(_fake_cfg(), conn, [], _settings())

    assert len(notified) == 1
    title, message = notified[0]
    assert title == "Bewegung ohne dich"
    assert "MacBook" in message

    with conn.cursor() as cur:
        cur.execute("SELECT reason, owner_device_id FROM alerts")
        assert cur.fetchall() == [("moved_without_owner", "laptop")]


def test_evaluate_device_away_alerts_does_not_repeat_while_still_away(monkeypatch, conn):
    """owner_device_locations gets a fresh row every poll regardless of
    movement (unlike deduped AirTag reports) - re-evaluating the same
    still-away device every poll must not re-notify each time."""
    from airtag_sentry import tracker as tracker_module

    _setup_primary_and_device(conn)
    monkeypatch.setattr(tracker_module, "fetch_owner_device_locations", _fail_fetch)
    monkeypatch.setattr(tracker_module, "reverse_geocode", lambda lat, lon: GeocodeResult(address=None, poi_name=None))
    notified = []
    monkeypatch.setattr(tracker_module, "notify_all", lambda notifiers, title, message: notified.append((title, message)))

    t0 = dt.datetime(2026, 1, 1, 8, 0, tzinfo=dt.timezone.utc)
    t1 = dt.datetime(2026, 1, 1, 8, 30, tzinfo=dt.timezone.utc)
    t2 = dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.timezone.utc)
    _record(conn, "primary", t0, 52.5, 13.4)
    _record(conn, "laptop", t0, 52.5, 13.4)
    _record(conn, "primary", t1, 52.5, 13.4)
    _record(conn, "laptop", t1, 52.51, 13.4)  # away starts here

    tracker_module._evaluate_device_away_alerts(_fake_cfg(), conn, [], _settings())
    assert len(notified) == 1

    _record(conn, "primary", t2, 52.5, 13.4)
    _record(conn, "laptop", t2, 52.51, 13.4)  # still away, unchanged

    tracker_module._evaluate_device_away_alerts(_fake_cfg(), conn, [], _settings())
    assert len(notified) == 1  # no repeat


def test_evaluate_device_away_alerts_suppresses_notification_when_already_reunited(monkeypatch, conn):
    """Device counterpart of owner_already_reunited's regression case (PR
    #119): the historical away-check is correct at the time it happened, but
    if the primary device's freshest known location shows you're already
    back with the object by the time the push is about to send, skip it -
    the alert row is still recorded either way."""
    from airtag_sentry import tracker as tracker_module

    _setup_primary_and_device(conn)
    monkeypatch.setattr(tracker_module, "fetch_owner_device_locations", _fail_fetch)
    monkeypatch.setattr(tracker_module, "reverse_geocode", lambda lat, lon: GeocodeResult(address=None, poi_name=None))
    notified = []
    monkeypatch.setattr(tracker_module, "notify_all", lambda notifiers, title, message: notified.append((title, message)))

    t_home = dt.datetime(2026, 1, 1, 8, 0, tzinfo=dt.timezone.utc)
    t_office = dt.datetime(2026, 1, 1, 8, 15, tzinfo=dt.timezone.utc)
    t_laptop_reading = dt.datetime(2026, 1, 1, 8, 30, tzinfo=dt.timezone.utc)
    t_home_again = dt.datetime(2026, 1, 1, 8, 50, tzinfo=dt.timezone.utc)

    _record(conn, "primary", t_home, 52.5, 13.4)
    _record(conn, "laptop", t_home, 52.5, 13.4)  # together at home
    _record(conn, "primary", t_office, 52.51, 13.4)  # primary leaves for the office without the laptop
    _record(conn, "laptop", t_laptop_reading, 52.5, 13.4)  # laptop itself never moves - still home
    _record(conn, "primary", t_home_again, 52.5, 13.4)  # primary is already back home by the time we evaluate

    tracker_module._evaluate_device_away_alerts(object(), conn, [], _settings())

    assert notified == []  # already reunited - push suppressed
    with conn.cursor() as cur:
        cur.execute("SELECT reason, owner_device_id FROM alerts")
        assert cur.fetchall() == [("moved_without_owner", "laptop")]  # but still recorded
