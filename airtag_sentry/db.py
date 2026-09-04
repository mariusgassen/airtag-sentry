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
    "timestamp" TIMESTAMPTZ NOT NULL UNIQUE,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    accuracy DOUBLE PRECISION,
    confidence SMALLINT,
    source TEXT NOT NULL DEFAULT 'findmy',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_location_reports_timestamp ON location_reports ("timestamp");

CREATE TABLE IF NOT EXISTS alerts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
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
"""


@dataclasses.dataclass(frozen=True)
class Report:
    id: int | None
    timestamp: dt.datetime
    lat: float
    lon: float
    accuracy: float | None
    confidence: int | None


@dataclasses.dataclass(frozen=True)
class Alert:
    reason: str
    distance_meters: float
    report_id: int


@dataclasses.dataclass(frozen=True)
class PushSubscription:
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
                INSERT INTO location_reports (timestamp, lat, lon, accuracy, confidence)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT ("timestamp") DO NOTHING
                RETURNING id, timestamp, lat, lon, accuracy, confidence
                """,
                (report.timestamp, report.lat, report.lon, report.accuracy, report.confidence),
            )
            row = cur.fetchone()
            if row is not None:
                inserted.append(Report(*row))
    conn.commit()
    return inserted


def count_reports(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM location_reports")
        (count,) = cur.fetchone()
        return count


def fetch_reports(conn: psycopg.Connection, limit: int | None = None) -> list[Report]:
    query = 'SELECT id, "timestamp", lat, lon, accuracy, confidence FROM location_reports ORDER BY "timestamp" ASC'
    params: tuple = ()
    if limit is not None:
        query = (
            'SELECT id, "timestamp", lat, lon, accuracy, confidence FROM ('
            'SELECT id, "timestamp", lat, lon, accuracy, confidence FROM location_reports '
            'ORDER BY "timestamp" DESC LIMIT %s'
            ") sub ORDER BY \"timestamp\" ASC"
        )
        params = (limit,)
    with conn.cursor() as cur:
        cur.execute(query, params)
        return [Report(*row) for row in cur.fetchall()]


def fetch_reports_before(conn: psycopg.Connection, timestamp: dt.datetime) -> list[Report]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT id, "timestamp", lat, lon, accuracy, confidence FROM location_reports '
            'WHERE "timestamp" < %s ORDER BY "timestamp" ASC',
            (timestamp,),
        )
        return [Report(*row) for row in cur.fetchall()]


def record_alert(conn: psycopg.Connection, alert: Alert) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO alerts (reason, distance_meters, report_id) VALUES (%s, %s, %s)",
            (alert.reason, alert.distance_meters, alert.report_id),
        )
    conn.commit()


def latest_alert(conn: psycopg.Connection) -> tuple[str, dt.datetime] | None:
    with conn.cursor() as cur:
        cur.execute('SELECT reason, "timestamp" FROM alerts ORDER BY "timestamp" DESC LIMIT 1')
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
