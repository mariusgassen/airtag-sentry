import datetime as dt
import os

import psycopg
import pytest

from airtag_sentry.db import (
    AppSettings,
    OwnerDevice,
    OwnerLocation,
    Report,
    StoredKey,
    create_airtag,
    delete_airtag,
    delete_airtag_key,
    delete_owner_apple_credentials,
    delete_telegram_credentials,
    fetch_owner_device_location_history,
    get_airtag_key,
    get_conn,
    get_owner_apple_credentials,
    get_settings,
    get_telegram_credentials,
    insert_reports,
    latest_owner_device_locations,
    latest_primary_owner_device_location,
    list_airtags,
    list_keyed_airtag_ids,
    list_owner_devices,
    record_owner_device_location,
    rename_airtag,
    rename_owner_device,
    set_airtag_appearance,
    set_airtag_key,
    set_owner_apple_credentials,
    set_owner_apple_sync_status,
    set_owner_device_appearance,
    set_owner_device_enabled,
    set_owner_device_primary,
    set_owner_include_family_devices,
    set_telegram_bot_commands,
    set_telegram_credentials,
    update_settings,
    upsert_owner_devices,
)
from airtag_sentry.migrate import upgrade_to_head

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://airtag:airtag@localhost:5432/airtag_sentry_test"
)
os.environ.setdefault("TEST_DATABASE_URL", TEST_DATABASE_URL)


@pytest.fixture()
def conn():
    try:
        with get_conn(TEST_DATABASE_URL) as connection:
            upgrade_to_head()
            with connection.cursor() as cur:
                cur.execute(
                    "TRUNCATE airtags, location_reports, alerts, push_subscriptions, airtag_keys, "
                    "owner_devices, owner_device_locations, owner_apple_credentials, telegram_settings "
                    "RESTART IDENTITY CASCADE"
                )
                # settings is a singleton row (id pinned to 1), not per-test data -
                # reset it to defaults in place rather than truncating it away.
                cur.execute(
                    """
                    UPDATE settings SET
                        polling_interval_minutes = 15,
                        movement_distance_threshold_meters = 100,
                        movement_stillstand_hours = 24,
                        movement_stillstand_movement_meters = 15,
                        movement_alert_on_backfill = false,
                        movement_away_distance_meters = 150,
                        owner_location_max_age_minutes = 60
                    WHERE id = 1
                    """
                )
            connection.commit()
            # Most tests below reference these two ids as if they already exist
            # (airtag_id is now a real FK to airtags.id).
            create_airtag(connection, "bike", "Fahrrad")
            create_airtag(connection, "backpack", "Rucksack")
            yield connection
    except psycopg.OperationalError:
        pytest.skip(f"Postgres not reachable at {TEST_DATABASE_URL}; start it to run this test.")


def _report(iso: str, lat: float, lon: float, airtag_id: str = "bike") -> Report:
    return Report(
        id=None,
        airtag_id=airtag_id,
        timestamp=dt.datetime.fromisoformat(iso).replace(tzinfo=dt.timezone.utc),
        lat=lat,
        lon=lon,
        accuracy=5.0,
        confidence=2,
    )


def test_schema_creates_tables(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        tables = {row[0] for row in cur.fetchall()}
    assert {
        "airtags",
        "location_reports",
        "alerts",
        "push_subscriptions",
        "airtag_keys",
        "settings",
        "owner_devices",
        "owner_device_locations",
        "owner_apple_credentials",
        "telegram_settings",
        "alembic_version",
    } <= tables


def test_migrations_idempotent(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM alembic_version")
        (count_before,) = cur.fetchone()
    assert count_before == 1

    # Re-running must not error and must not change anything.
    upgrade_to_head()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM alembic_version")
        (count_after,) = cur.fetchone()
    assert count_after == 1


def test_create_list_rename_delete_airtag(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM airtags")  # start from a clean slate for this test
    conn.commit()

    assert list_airtags(conn) == []

    created = create_airtag(conn, "trolley", "Einkaufswagen")
    assert created.id == "trolley"
    assert created.name == "Einkaufswagen"
    assert [a.id for a in list_airtags(conn)] == ["trolley"]

    renamed = rename_airtag(conn, "trolley", "Trolley 2")
    assert renamed.name == "Trolley 2"
    assert list_airtags(conn)[0].name == "Trolley 2"

    delete_airtag(conn, "trolley")
    assert list_airtags(conn) == []


def test_set_airtag_appearance_round_trip(conn):
    assert next(a for a in list_airtags(conn) if a.id == "bike").icon is None

    updated = set_airtag_appearance(conn, "bike", "bike", "#0a84ff")
    assert updated.icon == "bike"
    assert updated.color == "#0a84ff"
    stored = next(a for a in list_airtags(conn) if a.id == "bike")
    assert stored.icon == "bike"
    assert stored.color == "#0a84ff"

    reset = set_airtag_appearance(conn, "bike", None, None)
    assert reset.icon is None
    assert reset.color is None


def test_delete_airtag_cascades_to_reports_alerts_and_key(conn):
    insert_reports(conn, [_report("2026-01-01T10:00:00", 52.5, 13.4, airtag_id="bike")])
    set_airtag_key(conn, StoredKey(airtag_id="bike", key_type="private_key_b64", encrypted_data="tok"))

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM location_reports WHERE airtag_id = 'bike'")
        assert cur.fetchone()[0] == 1

    delete_airtag(conn, "bike")

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM location_reports WHERE airtag_id = 'bike'")
        assert cur.fetchone()[0] == 0
    assert get_airtag_key(conn, "bike") is None
    assert "bike" not in {a.id for a in list_airtags(conn)}


def test_insert_reports_returns_only_new_rows(conn):
    first_batch = [_report("2026-01-01T10:00:00", 52.5, 13.4), _report("2026-01-01T10:15:00", 52.5001, 13.4001)]
    inserted = insert_reports(conn, first_batch)
    assert len(inserted) == 2

    # Re-inserting the same timestamps (as a real 7-day-window poll would) must
    # not duplicate rows or come back as "newly inserted".
    second_batch = first_batch + [_report("2026-01-01T10:30:00", 52.5002, 13.4002)]
    inserted_again = insert_reports(conn, second_batch)
    assert len(inserted_again) == 1
    assert inserted_again[0].timestamp.isoformat() == "2026-01-01T10:30:00+00:00"

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM location_reports")
        (count,) = cur.fetchone()
    assert count == 3


def test_insert_reports_allows_same_timestamp_for_different_airtag(conn):
    ts = "2026-01-01T10:00:00"
    inserted_a = insert_reports(conn, [_report(ts, 52.5, 13.4, airtag_id="bike")])
    inserted_b = insert_reports(conn, [_report(ts, 48.1, 11.6, airtag_id="backpack")])
    assert len(inserted_a) == 1
    assert len(inserted_b) == 1

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM location_reports")
        (count,) = cur.fetchone()
    assert count == 2


def test_airtag_key_set_get_delete_round_trip(conn):
    assert get_airtag_key(conn, "bike") is None
    assert list_keyed_airtag_ids(conn) == set()

    set_airtag_key(conn, StoredKey(airtag_id="bike", key_type="private_key_b64", encrypted_data="tok1"))
    stored = get_airtag_key(conn, "bike")
    assert stored == StoredKey(airtag_id="bike", key_type="private_key_b64", encrypted_data="tok1")
    assert list_keyed_airtag_ids(conn) == {"bike"}

    # Setting again for the same id replaces rather than duplicating.
    set_airtag_key(conn, StoredKey(airtag_id="bike", key_type="accessory_json", encrypted_data="tok2"))
    stored = get_airtag_key(conn, "bike")
    assert stored == StoredKey(airtag_id="bike", key_type="accessory_json", encrypted_data="tok2")

    delete_airtag_key(conn, "bike")
    assert get_airtag_key(conn, "bike") is None
    assert list_keyed_airtag_ids(conn) == set()


def test_get_settings_returns_seeded_defaults(conn):
    settings = get_settings(conn)
    assert settings == AppSettings(
        polling_interval_minutes=15,
        movement_distance_threshold_meters=100,
        movement_stillstand_hours=24,
        movement_stillstand_movement_meters=15,
        movement_alert_on_backfill=False,
        movement_away_distance_meters=150,
        owner_location_max_age_minutes=60,
    )


def test_update_settings_round_trips(conn):
    updated = update_settings(
        conn,
        AppSettings(
            polling_interval_minutes=30,
            movement_distance_threshold_meters=200,
            movement_stillstand_hours=12,
            movement_stillstand_movement_meters=5,
            movement_alert_on_backfill=True,
            movement_away_distance_meters=250,
            owner_location_max_age_minutes=30,
        ),
    )
    assert updated.polling_interval_minutes == 30
    assert updated.movement_away_distance_meters == 250
    assert get_settings(conn) == updated


_SEEN_AT = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)


def _owner_location(device_id: str, iso: str, lat: float, lon: float, accuracy: float = 10.0) -> OwnerLocation:
    return OwnerLocation(
        id=None,
        device_id=device_id,
        recorded_at=dt.datetime.fromisoformat(iso).replace(tzinfo=dt.timezone.utc),
        lat=lat,
        lon=lon,
        horizontal_accuracy=accuracy,
    )


def test_upsert_and_list_owner_devices_preserves_enabled_on_reupsert(conn):
    assert list_owner_devices(conn) == []

    upsert_owner_devices(conn, [{"id": "mac-1", "name": "MacBook Air", "device_type": "Mac"}], seen_at=_SEEN_AT)
    assert list_owner_devices(conn) == [
        OwnerDevice(
            id="mac-1", name="MacBook Air", device_type="Mac", enabled=False, is_primary=False, last_seen_at=_SEEN_AT
        )
    ]

    enabled = set_owner_device_enabled(conn, "mac-1", True)
    assert enabled == OwnerDevice(
        id="mac-1", name="MacBook Air", device_type="Mac", enabled=True, is_primary=False, last_seen_at=_SEEN_AT
    )

    # Re-discovering the same device (e.g. after a rename in Find My) must not
    # reset `enabled` - only identity fields (including last_seen_at) are
    # refreshed.
    later = _SEEN_AT + dt.timedelta(minutes=15)
    upsert_owner_devices(conn, [{"id": "mac-1", "name": "Marius' MacBook", "device_type": "Mac"}], seen_at=later)
    assert list_owner_devices(conn) == [
        OwnerDevice(
            id="mac-1", name="Marius' MacBook", device_type="Mac", enabled=True, is_primary=False, last_seen_at=later
        )
    ]


def test_reupsert_does_not_clobber_display_name_or_appearance(conn):
    """upsert_owner_devices refreshes `name`/`device_type` from a live Apple
    listing on every call - it must never touch display_name/icon/color, or a
    user's rename/appearance choice would get silently reset on the next
    dashboard load."""
    upsert_owner_devices(conn, [{"id": "mac-1", "name": "MacBook Air", "device_type": "Mac"}], seen_at=_SEEN_AT)
    rename_owner_device(conn, "mac-1", "Mein Mac")
    set_owner_device_appearance(conn, "mac-1", "laptop", "#ff0000")

    # A live Apple refresh renames the *technical* name only.
    upsert_owner_devices(
        conn, [{"id": "mac-1", "name": "Marius' MacBook Air", "device_type": "Mac"}], seen_at=_SEEN_AT
    )

    [device] = list_owner_devices(conn)
    assert device.name == "Marius' MacBook Air"
    assert device.display_name == "Mein Mac"
    assert device.icon == "laptop"
    assert device.color == "#ff0000"


def test_rename_owner_device_sets_and_clears_display_name(conn):
    upsert_owner_devices(conn, [{"id": "mac-1", "name": "MacBook Air", "device_type": "Mac"}], seen_at=_SEEN_AT)

    renamed = rename_owner_device(conn, "mac-1", "Mein Mac")
    assert renamed.display_name == "Mein Mac"
    assert renamed.name == "MacBook Air"

    reset = rename_owner_device(conn, "mac-1", None)
    assert reset.display_name is None


def test_rename_owner_device_returns_none_for_unknown_id(conn):
    assert rename_owner_device(conn, "unknown", "Mein Mac") is None


def test_set_owner_device_appearance_sets_and_resets_icon_and_color(conn):
    upsert_owner_devices(conn, [{"id": "mac-1", "name": "MacBook Air", "device_type": "Mac"}], seen_at=_SEEN_AT)

    styled = set_owner_device_appearance(conn, "mac-1", "laptop", "#ff0000")
    assert styled.icon == "laptop"
    assert styled.color == "#ff0000"

    reset = set_owner_device_appearance(conn, "mac-1", None, None)
    assert reset.icon is None
    assert reset.color is None


def test_set_owner_device_appearance_returns_none_for_unknown_id(conn):
    assert set_owner_device_appearance(conn, "unknown", "laptop", "#ff0000") is None


def test_set_owner_device_enabled_returns_none_for_unknown_id(conn):
    assert set_owner_device_enabled(conn, "unknown", True) is None


def test_set_owner_device_primary_is_exclusive_and_force_enables(conn):
    upsert_owner_devices(
        conn,
        [
            {"id": "mac-1", "name": "MacBook Air", "device_type": "Mac"},
            {"id": "iphone-1", "name": "iPhone", "device_type": "iPhone"},
        ],
        seen_at=_SEEN_AT,
    )

    mac = set_owner_device_primary(conn, "mac-1")
    assert mac.is_primary is True
    assert mac.enabled is True  # force-enabled, since a disabled device never gets a location

    # Picking a new primary clears the previous one - never more than one.
    iphone = set_owner_device_primary(conn, "iphone-1")
    assert iphone.is_primary is True
    [mac_after] = [d for d in list_owner_devices(conn) if d.id == "mac-1"]
    assert mac_after.is_primary is False

    assert set_owner_device_primary(conn, None) is None
    assert all(not d.is_primary for d in list_owner_devices(conn))


def test_set_owner_device_primary_returns_none_for_unknown_id(conn):
    assert set_owner_device_primary(conn, "unknown") is None


def test_disabling_the_primary_device_clears_primary(conn):
    upsert_owner_devices(conn, [{"id": "mac-1", "name": "MacBook Air", "device_type": "Mac"}], seen_at=_SEEN_AT)
    set_owner_device_primary(conn, "mac-1")

    disabled = set_owner_device_enabled(conn, "mac-1", False)
    assert disabled.enabled is False
    assert disabled.is_primary is False


def test_latest_owner_device_locations_only_includes_enabled_devices(conn):
    upsert_owner_devices(
        conn,
        [
            {"id": "mac-1", "name": "MacBook Air", "device_type": "Mac"},
            {"id": "iphone-1", "name": "iPhone", "device_type": "iPhone"},
        ],
        seen_at=_SEEN_AT,
    )
    set_owner_device_enabled(conn, "mac-1", True)
    # iphone-1 stays disabled - it should never show up below, even with a
    # recorded location.

    record_owner_device_location(conn, _owner_location("mac-1", "2026-01-01T10:00", 52.5, 13.4))
    record_owner_device_location(conn, _owner_location("iphone-1", "2026-01-01T10:00", 52.6, 13.5))

    assert [loc.device_id for loc in latest_owner_device_locations(conn)] == ["mac-1"]

    # A later reading for the enabled device becomes the new "latest" one.
    second = record_owner_device_location(conn, _owner_location("mac-1", "2026-01-01T10:15", 52.51, 13.41, 8.0))
    assert latest_owner_device_locations(conn) == [second]


def test_latest_primary_owner_device_location_ignores_non_primary_devices(conn):
    upsert_owner_devices(
        conn,
        [
            {"id": "mac-1", "name": "MacBook Air", "device_type": "Mac"},
            {"id": "iphone-1", "name": "iPhone", "device_type": "iPhone"},
        ],
        seen_at=_SEEN_AT,
    )
    set_owner_device_enabled(conn, "mac-1", True)
    set_owner_device_enabled(conn, "iphone-1", True)
    assert latest_primary_owner_device_location(conn) is None

    record_owner_device_location(conn, _owner_location("mac-1", "2026-01-01T10:00", 52.5, 13.4))
    # Not primary - must never be picked, even though it's enabled and has a location.
    assert latest_primary_owner_device_location(conn) is None

    set_owner_device_primary(conn, "iphone-1")
    record_owner_device_location(conn, _owner_location("mac-1", "2026-01-01T10:15", 52.51, 13.41))
    assert latest_primary_owner_device_location(conn) is None  # mac-1 still isn't primary

    primary_loc = record_owner_device_location(conn, _owner_location("iphone-1", "2026-01-01T10:20", 52.6, 13.5))
    assert latest_primary_owner_device_location(conn) == primary_loc


def test_fetch_owner_device_location_history_returns_newest_first_and_respects_limit(conn):
    upsert_owner_devices(conn, [{"id": "mac-1", "name": "MacBook Air", "device_type": "Mac"}], seen_at=_SEEN_AT)
    assert fetch_owner_device_location_history(conn, "mac-1") == []

    first = record_owner_device_location(conn, _owner_location("mac-1", "2026-01-01T10:00", 52.5, 13.4))
    second = record_owner_device_location(conn, _owner_location("mac-1", "2026-01-01T10:15", 52.51, 13.41, 8.0))

    assert fetch_owner_device_location_history(conn, "mac-1") == [second, first]
    assert fetch_owner_device_location_history(conn, "mac-1", limit=1) == [second]


def test_owner_apple_credentials_set_get_delete_round_trip(conn):
    assert get_owner_apple_credentials(conn) is None

    set_owner_apple_credentials(conn, "owner@example.com", "enc1")
    stored = get_owner_apple_credentials(conn)
    assert stored.apple_id == "owner@example.com"
    assert stored.encrypted_password == "enc1"

    # Setting again replaces rather than duplicating (single-row table).
    set_owner_apple_credentials(conn, "owner@example.com", "enc2")
    stored = get_owner_apple_credentials(conn)
    assert stored.encrypted_password == "enc2"

    delete_owner_apple_credentials(conn)
    assert get_owner_apple_credentials(conn) is None


def test_owner_apple_sync_status_records_and_clears_error(conn):
    set_owner_apple_credentials(conn, "owner@example.com", "enc1")
    assert get_owner_apple_credentials(conn).last_sync_at is None
    assert get_owner_apple_credentials(conn).last_sync_error is None

    set_owner_apple_sync_status(conn, _SEEN_AT, "Invalid email/password combination.")
    stored = get_owner_apple_credentials(conn)
    assert stored.last_sync_at == _SEEN_AT
    assert stored.last_sync_error == "Invalid email/password combination."

    # The next successful sync clears the error but still advances last_sync_at.
    later = _SEEN_AT + dt.timedelta(minutes=15)
    set_owner_apple_sync_status(conn, later, None)
    stored = get_owner_apple_credentials(conn)
    assert stored.last_sync_at == later
    assert stored.last_sync_error is None


def test_reconnecting_owner_apple_account_clears_a_stale_sync_error(conn):
    """A fresh login shouldn't carry forward a previous connection's error -
    otherwise reconnecting after fixing a bad password would still show the
    old failure until the next poll happens to succeed."""
    set_owner_apple_credentials(conn, "owner@example.com", "enc1")
    set_owner_apple_sync_status(conn, _SEEN_AT, "Invalid email/password combination.")

    set_owner_apple_credentials(conn, "owner@example.com", "enc2")
    stored = get_owner_apple_credentials(conn)
    assert stored.last_sync_at is None
    assert stored.last_sync_error is None


def test_set_owner_include_family_devices_updates_existing_account_without_password(conn):
    """The Family Sharing filter must be flippable after connecting, without a
    re-login: unlike set_owner_apple_credentials (a full login upsert), this
    should update just the flag on the existing row."""
    set_owner_apple_credentials(conn, "owner@example.com", "enc1", include_family_devices=False)

    assert set_owner_include_family_devices(conn, True) is True
    stored = get_owner_apple_credentials(conn)
    assert stored.include_family_devices is True
    assert stored.encrypted_password == "enc1"

    assert set_owner_include_family_devices(conn, False) is True
    assert get_owner_apple_credentials(conn).include_family_devices is False


def test_set_owner_include_family_devices_is_a_noop_when_not_connected(conn):
    assert get_owner_apple_credentials(conn) is None
    assert set_owner_include_family_devices(conn, True) is False
    assert get_owner_apple_credentials(conn) is None


def test_telegram_credentials_set_get_delete_round_trip(conn):
    assert get_telegram_credentials(conn) is None

    set_telegram_credentials(conn, "enc-token-1", "12345")
    stored = get_telegram_credentials(conn)
    assert stored.bot_token_encrypted == "enc-token-1"
    assert stored.chat_id == "12345"
    assert stored.bot_commands_enabled is False
    assert stored.webhook_secret is None

    # Setting again replaces rather than duplicating (single-row table).
    set_telegram_credentials(conn, "enc-token-2", "67890")
    stored = get_telegram_credentials(conn)
    assert stored.bot_token_encrypted == "enc-token-2"
    assert stored.chat_id == "67890"

    delete_telegram_credentials(conn)
    assert get_telegram_credentials(conn) is None


def test_telegram_bot_commands_set_round_trip(conn):
    set_telegram_credentials(conn, "enc-token", "12345")

    set_telegram_bot_commands(conn, True, "webhook-secret-1")
    stored = get_telegram_credentials(conn)
    assert stored.bot_commands_enabled is True
    assert stored.webhook_secret == "webhook-secret-1"

    set_telegram_bot_commands(conn, False, None)
    stored = get_telegram_credentials(conn)
    assert stored.bot_commands_enabled is False
    assert stored.webhook_secret is None

    # Reconnecting (a new bot token) resets bot-commands state - any webhook
    # registered against the old token is no longer valid.
    set_telegram_bot_commands(conn, True, "webhook-secret-2")
    set_telegram_credentials(conn, "enc-token-new", "12345")
    stored = get_telegram_credentials(conn)
    assert stored.bot_commands_enabled is False
    assert stored.webhook_secret is None


def test_settings_table_stays_single_row(conn):
    with conn.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute("INSERT INTO settings (id) VALUES (2)")
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM settings")
        (count,) = cur.fetchone()
    assert count == 1
