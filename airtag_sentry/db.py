"""Postgres access: schema management and CRUD for reports, alerts, push subscriptions.

Plain psycopg (v3) with parameterized SQL - the schema is small enough that an ORM
would add indirection without buying anything. One connection per call is enough at
this traffic level (a poll every 15 minutes); no pool needed.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from contextlib import contextmanager
from typing import Iterator

import psycopg

SCHEMA = """
CREATE TABLE IF NOT EXISTS location_reports (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    airtag_id TEXT NOT NULL,
    "timestamp" TIMESTAMPTZ NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    accuracy DOUBLE PRECISION,
    confidence SMALLINT,
    source TEXT NOT NULL DEFAULT 'findmy',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT location_reports_airtag_timestamp_key UNIQUE (airtag_id, "timestamp")
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    airtag_id TEXT NOT NULL,
    "timestamp" TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason TEXT NOT NULL,
    distance_meters DOUBLE PRECISION NOT NULL,
    report_id BIGINT NOT NULL REFERENCES location_reports(id)
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Migration for pre-multi-airtag deployments: backfill existing rows under a
-- 'default' airtag_id and replace the old single-column uniqueness with a
-- composite one, so different airtags may share a timestamp. Must run before
-- the airtag_id-referencing indexes below, since a legacy table won't have
-- that column until these ALTERs apply.
ALTER TABLE location_reports ADD COLUMN IF NOT EXISTS airtag_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE location_reports ALTER COLUMN airtag_id DROP DEFAULT;
ALTER TABLE location_reports DROP CONSTRAINT IF EXISTS location_reports_timestamp_key;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'location_reports_airtag_timestamp_key'
    ) THEN
        ALTER TABLE location_reports
            ADD CONSTRAINT location_reports_airtag_timestamp_key UNIQUE (airtag_id, "timestamp");
    END IF;
END $$;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS airtag_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE alerts ALTER COLUMN airtag_id DROP DEFAULT;

CREATE INDEX IF NOT EXISTS idx_location_reports_timestamp ON location_reports ("timestamp");
CREATE INDEX IF NOT EXISTS idx_location_reports_airtag_timestamp ON location_reports (airtag_id, "timestamp");
CREATE INDEX IF NOT EXISTS idx_alerts_airtag_timestamp ON alerts (airtag_id, "timestamp");
"""


@dataclasses.dataclass(frozen=True)
class Report:
    id: int | None
    airtag_id: str
    timestamp: dt.datetime
    lat: float
    lon: float
    accuracy: float | None
    confidence: int | None


@dataclasses.dataclass(frozen=True)
class Alert:
    airtag_id: str
    reason: str
    distance_meters: float
    report_id: int


@dataclasses.dataclass(frozen=True)
class PushSubscription:
    # Deliberately not scoped to an airtag_id: a subscribed browser gets alerts
    # for every configured AirTag.
    endpoint: str
    p256dh: str
    auth: str


@contextmanager
def get_conn(database_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(database_url) as conn:
        yield conn


def init_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()


def insert_reports(conn: psycopg.Connection, reports: list[Report]) -> list[Report]:
    """Insert reports, skipping ones whose timestamp already exists.

    Returns only the reports that were actually newly inserted, sorted ascending -
    this is what movement detection and alerting should look at.
    """
    inserted: list[Report] = []
    with conn.cursor() as cur:
        for report in sorted(reports, key=lambda r: r.timestamp):
            cur.execute(
                """
                INSERT INTO location_reports (airtag_id, timestamp, lat, lon, accuracy, confidence)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (airtag_id, "timestamp") DO NOTHING
                RETURNING id, airtag_id, timestamp, lat, lon, accuracy, confidence
                """,
                (
                    report.airtag_id,
                    report.timestamp,
                    report.lat,
                    report.lon,
                    report.accuracy,
                    report.confidence,
                ),
            )
            row = cur.fetchone()
            if row is not None:
                inserted.append(Report(*row))
    conn.commit()
    return inserted


def count_reports(conn: psycopg.Connection, airtag_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM location_reports WHERE airtag_id = %s", (airtag_id,))
        (count,) = cur.fetchone()
        return count


def fetch_reports(conn: psycopg.Connection, airtag_id: str, limit: int | None = None) -> list[Report]:
    query = (
        'SELECT id, airtag_id, "timestamp", lat, lon, accuracy, confidence FROM location_reports '
        'WHERE airtag_id = %s ORDER BY "timestamp" ASC'
    )
    params: tuple = (airtag_id,)
    if limit is not None:
        query = (
            'SELECT id, airtag_id, "timestamp", lat, lon, accuracy, confidence FROM ('
            'SELECT id, airtag_id, "timestamp", lat, lon, accuracy, confidence FROM location_reports '
            'WHERE airtag_id = %s ORDER BY "timestamp" DESC LIMIT %s'
            ") sub ORDER BY \"timestamp\" ASC"
        )
        params = (airtag_id, limit)
    with conn.cursor() as cur:
        cur.execute(query, params)
        return [Report(*row) for row in cur.fetchall()]


def fetch_reports_before(
    conn: psycopg.Connection, airtag_id: str, timestamp: dt.datetime
) -> list[Report]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT id, airtag_id, "timestamp", lat, lon, accuracy, confidence FROM location_reports '
            'WHERE airtag_id = %s AND "timestamp" < %s ORDER BY "timestamp" ASC',
            (airtag_id, timestamp),
        )
        return [Report(*row) for row in cur.fetchall()]


def record_alert(conn: psycopg.Connection, alert: Alert) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO alerts (airtag_id, reason, distance_meters, report_id) VALUES (%s, %s, %s, %s)",
            (alert.airtag_id, alert.reason, alert.distance_meters, alert.report_id),
        )
    conn.commit()


def latest_alert(conn: psycopg.Connection, airtag_id: str) -> tuple[str, dt.datetime] | None:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT reason, "timestamp" FROM alerts WHERE airtag_id = %s ORDER BY "timestamp" DESC LIMIT 1',
            (airtag_id,),
        )
        row = cur.fetchone()
        return tuple(row) if row else None


def add_push_subscription(conn: psycopg.Connection, sub: PushSubscription) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO push_subscriptions (endpoint, p256dh, auth)
            VALUES (%s, %s, %s)
            ON CONFLICT (endpoint) DO UPDATE SET p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth
            """,
            (sub.endpoint, sub.p256dh, sub.auth),
        )
    conn.commit()


def remove_push_subscription(conn: psycopg.Connection, endpoint: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (endpoint,))
    conn.commit()


def list_push_subscriptions(conn: psycopg.Connection) -> list[PushSubscription]:
    with conn.cursor() as cur:
        cur.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions")
        return [PushSubscription(*row) for row in cur.fetchall()]
