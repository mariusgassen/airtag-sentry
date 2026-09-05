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


@dataclasses.dataclass(frozen=True)
class AirtagRecord:
    id: str
    name: str


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
class StoredKey:
    airtag_id: str
    key_type: str  # "accessory_json" | "private_key_b64"
    encrypted_data: str


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


def create_airtag(conn: psycopg.Connection, airtag_id: str, name: str) -> AirtagRecord:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO airtags (id, name) VALUES (%s, %s) RETURNING id, name",
            (airtag_id, name),
        )
        row = cur.fetchone()
    conn.commit()
    return AirtagRecord(*row)


def list_airtags(conn: psycopg.Connection) -> list[AirtagRecord]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM airtags ORDER BY created_at ASC")
        return [AirtagRecord(*row) for row in cur.fetchall()]


def rename_airtag(conn: psycopg.Connection, airtag_id: str, name: str) -> AirtagRecord | None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE airtags SET name = %s WHERE id = %s RETURNING id, name",
            (name, airtag_id),
        )
        row = cur.fetchone()
    conn.commit()
    return AirtagRecord(*row) if row else None


def delete_airtag(conn: psycopg.Connection, airtag_id: str) -> None:
    # Cascades to location_reports/alerts/airtag_keys via their FK constraints.
    with conn.cursor() as cur:
        cur.execute("DELETE FROM airtags WHERE id = %s", (airtag_id,))
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


def set_airtag_key(conn: psycopg.Connection, key: StoredKey) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO airtag_keys (airtag_id, key_type, encrypted_data, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (airtag_id) DO UPDATE
                SET key_type = EXCLUDED.key_type,
                    encrypted_data = EXCLUDED.encrypted_data,
                    updated_at = now()
            """,
            (key.airtag_id, key.key_type, key.encrypted_data),
        )
    conn.commit()


def get_airtag_key(conn: psycopg.Connection, airtag_id: str) -> StoredKey | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT airtag_id, key_type, encrypted_data FROM airtag_keys WHERE airtag_id = %s",
            (airtag_id,),
        )
        row = cur.fetchone()
        return StoredKey(*row) if row else None


def delete_airtag_key(conn: psycopg.Connection, airtag_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM airtag_keys WHERE airtag_id = %s", (airtag_id,))
    conn.commit()


def list_keyed_airtag_ids(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT airtag_id FROM airtag_keys")
        return {row[0] for row in cur.fetchall()}
