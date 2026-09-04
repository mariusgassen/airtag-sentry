import datetime as dt
import os

import psycopg
import pytest

from airtag_sentry.db import Report, get_conn, init_schema, insert_reports

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://airtag:airtag@localhost:5432/airtag_sentry_test"
)


@pytest.fixture()
def conn():
    try:
        with get_conn(TEST_DATABASE_URL) as connection:
            init_schema(connection)
            with connection.cursor() as cur:
                cur.execute("TRUNCATE location_reports, alerts, push_subscriptions RESTART IDENTITY CASCADE")
            connection.commit()
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
    assert {"location_reports", "alerts", "push_subscriptions"} <= tables


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
