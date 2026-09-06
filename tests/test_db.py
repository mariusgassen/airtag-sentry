import datetime as dt
import os

import psycopg
import pytest

from airtag_sentry.db import (
    AppSettings,
    OwnerLocation,
    Report,
    StoredKey,
    create_airtag,
    delete_airtag,
    delete_airtag_key,
    delete_owner_apple_credentials,
    get_airtag_key,
    get_conn,
    get_owner_apple_credentials,
    get_settings,
    insert_reports,
    latest_owner_location,
    list_airtags,
    list_keyed_airtag_ids,
    record_owner_location,
    rename_airtag,
    set_airtag_key,
    set_owner_apple_credentials,
    update_settings,
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
                    "owner_locations, owner_apple_credentials RESTART IDENTITY CASCADE"
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
        "owner_locations",
        "owner_apple_credentials",
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


def test_owner_location_record_and_latest_round_trip(conn):
    assert latest_owner_location(conn) is None

    first = record_owner_location(
        conn,
        OwnerLocation(
            id=None,
            recorded_at=dt.datetime(2026, 1, 1, 10, 0, tzinfo=dt.timezone.utc),
            lat=52.5,
            lon=13.4,
            horizontal_accuracy=10.0,
        ),
    )
    assert first.id is not None
    assert latest_owner_location(conn) == first

    # A later reading becomes the new "latest" one.
    second = record_owner_location(
        conn,
        OwnerLocation(
            id=None,
            recorded_at=dt.datetime(2026, 1, 1, 10, 15, tzinfo=dt.timezone.utc),
            lat=52.51,
            lon=13.41,
            horizontal_accuracy=8.0,
        ),
    )
    assert latest_owner_location(conn) == second


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


def test_settings_table_stays_single_row(conn):
    with conn.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute("INSERT INTO settings (id) VALUES (2)")
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM settings")
        (count,) = cur.fetchone()
    assert count == 1
