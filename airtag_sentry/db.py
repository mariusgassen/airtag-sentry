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
    icon: str | None = None
    color: str | None = None


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


@dataclasses.dataclass(frozen=True)
class OwnerAppleCredentials:
    apple_id: str
    encrypted_password: str
    # Bookkeeping for the background poller's live Apple calls (see
    # owner_tracking.fetch_owner_device_locations) - last_sync_at advances on
    # every *attempted* listing, success or failure; last_sync_error holds the
    # exception message from the most recent failure and is cleared on the
    # next success. Surfaced via GET /api/apple/owner/status so a lapsed
    # session or a transient Apple/network error is visible in the dashboard
    # instead of only ever being logged.
    last_sync_at: dt.datetime | None = None
    last_sync_error: str | None = None


@dataclasses.dataclass(frozen=True)
class TelegramCredentials:
    bot_token_encrypted: str
    chat_id: str
    bot_commands_enabled: bool
    # Anti-spoofing token handed to Telegram's setWebhook and compared against
    # the X-Telegram-Bot-Api-Secret-Token header on every inbound webhook
    # request - not user secret material, so unlike bot_token_encrypted this
    # isn't encrypted at rest. None while bot_commands_enabled is false.
    webhook_secret: str | None


@dataclasses.dataclass(frozen=True)
class OwnerDevice:
    id: str
    name: str
    device_type: str
    enabled: bool
    # Exactly one device (or none) is primary at a time - see
    # set_owner_device_primary(). The primary device is the one used for
    # "moved without you" away-correlation and its history is drawn as the
    # map trail; other enabled devices are tracked/listed but don't affect
    # either.
    is_primary: bool
    # User-chosen name/icon/color, mirroring AirtagRecord's - None means
    # "unset", i.e. fall back to `name` (the Apple-synced technical name) /
    # the derived glyph+color. `upsert_owner_devices` never touches these,
    # unlike `name` - see rename_owner_device/set_owner_device_appearance.
    display_name: str | None = None
    icon: str | None = None
    color: str | None = None
    # Set to the poll's timestamp every time this device appears in a
    # *successful* live Apple device listing (upsert_owner_devices, called for
    # every device the account has - see owner_tracking.py). Comparing this
    # against OwnerAppleCredentials.last_sync_at (the same poll's timestamp)
    # tells whether this device was present in the most recent successful
    # sync, or has gone missing from the account (e.g. removed from iCloud) -
    # see GET /api/owner-devices' `on_account` field.
    last_seen_at: dt.datetime | None = None


@dataclasses.dataclass(frozen=True)
class OwnerLocation:
    id: int | None
    device_id: str
    recorded_at: dt.datetime
    lat: float
    lon: float
    horizontal_accuracy: float | None


@dataclasses.dataclass(frozen=True)
class AppSettings:
    polling_interval_minutes: int
    movement_distance_threshold_meters: float
    movement_stillstand_hours: float
    movement_stillstand_movement_meters: float
    movement_alert_on_backfill: bool
    movement_away_distance_meters: float
    owner_location_max_age_minutes: float


@contextmanager
def get_conn(database_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(database_url) as conn:
        yield conn


def create_airtag(conn: psycopg.Connection, airtag_id: str, name: str) -> AirtagRecord:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO airtags (id, name) VALUES (%s, %s) RETURNING id, name, icon, color",
            (airtag_id, name),
        )
        row = cur.fetchone()
    conn.commit()
    return AirtagRecord(*row)


def list_airtags(conn: psycopg.Connection) -> list[AirtagRecord]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, icon, color FROM airtags ORDER BY created_at ASC")
        return [AirtagRecord(*row) for row in cur.fetchall()]


def rename_airtag(conn: psycopg.Connection, airtag_id: str, name: str) -> AirtagRecord | None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE airtags SET name = %s WHERE id = %s RETURNING id, name, icon, color",
            (name, airtag_id),
        )
        row = cur.fetchone()
    conn.commit()
    return AirtagRecord(*row) if row else None


def set_airtag_appearance(
    conn: psycopg.Connection, airtag_id: str, icon: str | None, color: str | None
) -> AirtagRecord | None:
    """Set (or, with both args None, reset to automatic) an AirTag's chosen
    icon/color. Both fields are always written together since the picker UI
    always submits both current values."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE airtags SET icon = %s, color = %s WHERE id = %s RETURNING id, name, icon, color",
            (icon, color, airtag_id),
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


def set_owner_apple_credentials(conn: psycopg.Connection, apple_id: str, encrypted_password: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO owner_apple_credentials
                (id, apple_id, encrypted_password, updated_at, last_sync_at, last_sync_error)
            VALUES (1, %s, %s, now(), NULL, NULL)
            ON CONFLICT (id) DO UPDATE
                SET apple_id = EXCLUDED.apple_id,
                    encrypted_password = EXCLUDED.encrypted_password,
                    updated_at = now(),
                    -- A fresh login shouldn't carry forward a previous
                    -- connection's stale sync error.
                    last_sync_at = NULL,
                    last_sync_error = NULL
            """,
            (apple_id, encrypted_password),
        )
    conn.commit()


def get_owner_apple_credentials(conn: psycopg.Connection) -> OwnerAppleCredentials | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT apple_id, encrypted_password, last_sync_at, last_sync_error "
            "FROM owner_apple_credentials WHERE id = 1"
        )
        row = cur.fetchone()
        return OwnerAppleCredentials(*row) if row else None


def set_owner_apple_sync_status(conn: psycopg.Connection, synced_at: dt.datetime, error: str | None) -> None:
    """Records the outcome of one live Apple device-listing attempt (success or
    failure) - see OwnerAppleCredentials.last_sync_at/last_sync_error. A no-op if
    owner tracking was disconnected in the meantime (no credentials row left to
    update)."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE owner_apple_credentials SET last_sync_at = %s, last_sync_error = %s WHERE id = 1",
            (synced_at, error),
        )
    conn.commit()


def delete_owner_apple_credentials(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM owner_apple_credentials WHERE id = 1")
    conn.commit()


def set_telegram_credentials(conn: psycopg.Connection, bot_token_encrypted: str, chat_id: str) -> None:
    # Reconnecting (e.g. a new bot token) invalidates any webhook already
    # registered against the old token, so drop bot-commands state too - the
    # dashboard's enable flow re-registers it against the new credentials.
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO telegram_settings
                (id, bot_token_encrypted, chat_id, bot_commands_enabled, webhook_secret, updated_at)
            VALUES (1, %s, %s, false, NULL, now())
            ON CONFLICT (id) DO UPDATE
                SET bot_token_encrypted = EXCLUDED.bot_token_encrypted,
                    chat_id = EXCLUDED.chat_id,
                    bot_commands_enabled = false,
                    webhook_secret = NULL,
                    updated_at = now()
            """,
            (bot_token_encrypted, chat_id),
        )
    conn.commit()


def get_telegram_credentials(conn: psycopg.Connection) -> TelegramCredentials | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT bot_token_encrypted, chat_id, bot_commands_enabled, webhook_secret "
            "FROM telegram_settings WHERE id = 1"
        )
        row = cur.fetchone()
        return TelegramCredentials(*row) if row else None


def delete_telegram_credentials(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM telegram_settings WHERE id = 1")
    conn.commit()


def set_telegram_bot_commands(conn: psycopg.Connection, enabled: bool, webhook_secret: str | None) -> None:
    """Enable/disable the inbound bot-commands webhook. Only meaningful once
    Telegram credentials already exist (the row must be present)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE telegram_settings
                SET bot_commands_enabled = %s, webhook_secret = %s, updated_at = now()
                WHERE id = 1
            """,
            (enabled, webhook_secret),
        )
    conn.commit()


_SETTINGS_COLUMNS = (
    "polling_interval_minutes",
    "movement_distance_threshold_meters",
    "movement_stillstand_hours",
    "movement_stillstand_movement_meters",
    "movement_alert_on_backfill",
    "movement_away_distance_meters",
    "owner_location_max_age_minutes",
)


def get_settings(conn: psycopg.Connection) -> AppSettings:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(_SETTINGS_COLUMNS)} FROM settings WHERE id = 1")
        row = cur.fetchone()
        return AppSettings(*row)


def update_settings(conn: psycopg.Connection, settings: AppSettings) -> AppSettings:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE settings SET
                polling_interval_minutes = %s,
                movement_distance_threshold_meters = %s,
                movement_stillstand_hours = %s,
                movement_stillstand_movement_meters = %s,
                movement_alert_on_backfill = %s,
                movement_away_distance_meters = %s,
                owner_location_max_age_minutes = %s,
                updated_at = now()
            WHERE id = 1
            """,
            (
                settings.polling_interval_minutes,
                settings.movement_distance_threshold_meters,
                settings.movement_stillstand_hours,
                settings.movement_stillstand_movement_meters,
                settings.movement_alert_on_backfill,
                settings.movement_away_distance_meters,
                settings.owner_location_max_age_minutes,
            ),
        )
    conn.commit()
    return settings


def upsert_owner_devices(conn: psycopg.Connection, devices: list[dict], seen_at: dt.datetime) -> None:
    """Records/refreshes device identity (name, type) as seen in a live Apple
    listing, and stamps `last_seen_at` with `seen_at` (the calling poll's own
    timestamp, not a fresh `now()` per row) so every device from the same
    listing gets the exact same value - that's what lets GET /api/owner-devices
    tell "seen in the most recent successful sync" apart from "missing from it"
    with a plain equality check against OwnerAppleCredentials.last_sync_at,
    rather than a fuzzy age comparison. Leaves `enabled` untouched - discovering
    a device never opts it into tracking on its own."""
    if not devices:
        return
    rows = [{**device, "seen_at": seen_at} for device in devices]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO owner_devices (id, name, device_type, last_seen_at)
            VALUES (%(id)s, %(name)s, %(device_type)s, %(seen_at)s)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, device_type = EXCLUDED.device_type,
                last_seen_at = EXCLUDED.last_seen_at
            """,
            rows,
        )
    conn.commit()


_OWNER_DEVICE_COLUMNS = "id, name, device_type, enabled, is_primary, display_name, icon, color, last_seen_at"


def list_owner_devices(conn: psycopg.Connection) -> list[OwnerDevice]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_OWNER_DEVICE_COLUMNS} FROM owner_devices ORDER BY name")
        return [OwnerDevice(*row) for row in cur.fetchall()]


def set_owner_device_enabled(conn: psycopg.Connection, device_id: str, enabled: bool) -> OwnerDevice | None:
    with conn.cursor() as cur:
        cur.execute(
            # Disabling a device that's currently primary clears is_primary too -
            # a disabled device never gets a fresh location, so leaving it primary
            # would silently stop away-correlation without any visible signal why.
            f"UPDATE owner_devices SET enabled = %s, is_primary = is_primary AND %s WHERE id = %s "
            f"RETURNING {_OWNER_DEVICE_COLUMNS}",
            (enabled, enabled, device_id),
        )
        row = cur.fetchone()
    conn.commit()
    return OwnerDevice(*row) if row else None


def set_owner_device_primary(conn: psycopg.Connection, device_id: str | None) -> OwnerDevice | None:
    """Marks `device_id` as the one device used for away-correlation and the map
    trail, clearing any previous primary first (at most one at a time). Also
    force-enables it, since a disabled device never gets a fresh location.
    `device_id=None` just clears the current primary, returning None."""
    with conn.cursor() as cur:
        cur.execute("UPDATE owner_devices SET is_primary = false WHERE is_primary")
        if device_id is None:
            conn.commit()
            return None
        cur.execute(
            f"UPDATE owner_devices SET is_primary = true, enabled = true WHERE id = %s "
            f"RETURNING {_OWNER_DEVICE_COLUMNS}",
            (device_id,),
        )
        row = cur.fetchone()
    conn.commit()
    return OwnerDevice(*row) if row else None


def rename_owner_device(conn: psycopg.Connection, device_id: str, display_name: str | None) -> OwnerDevice | None:
    """Sets (or, with display_name=None, clears back to the Apple-synced technical
    `name`) a device's user-chosen display name. Never touches `name` itself -
    that's upsert_owner_devices' column, refreshed from Apple on every live listing."""
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE owner_devices SET display_name = %s WHERE id = %s RETURNING {_OWNER_DEVICE_COLUMNS}",
            (display_name, device_id),
        )
        row = cur.fetchone()
    conn.commit()
    return OwnerDevice(*row) if row else None


def set_owner_device_appearance(
    conn: psycopg.Connection, device_id: str, icon: str | None, color: str | None
) -> OwnerDevice | None:
    """Set (or, with both args None, reset to automatic) a device's chosen
    icon/color - mirrors set_airtag_appearance."""
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE owner_devices SET icon = %s, color = %s WHERE id = %s RETURNING {_OWNER_DEVICE_COLUMNS}",
            (icon, color, device_id),
        )
        row = cur.fetchone()
    conn.commit()
    return OwnerDevice(*row) if row else None


def record_owner_device_location(conn: psycopg.Connection, location: OwnerLocation) -> OwnerLocation:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO owner_device_locations (device_id, recorded_at, lat, lon, horizontal_accuracy)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, device_id, recorded_at, lat, lon, horizontal_accuracy
            """,
            (
                location.device_id,
                location.recorded_at,
                location.lat,
                location.lon,
                location.horizontal_accuracy,
            ),
        )
        row = cur.fetchone()
    conn.commit()
    return OwnerLocation(*row)


def latest_owner_device_locations(conn: psycopg.Connection) -> list[OwnerLocation]:
    """The latest reading for each *enabled* device - one row per device."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (odl.device_id)
                odl.id, odl.device_id, odl.recorded_at, odl.lat, odl.lon, odl.horizontal_accuracy
            FROM owner_device_locations odl
            JOIN owner_devices od ON od.id = odl.device_id
            WHERE od.enabled
            ORDER BY odl.device_id, odl.recorded_at DESC
            """
        )
        return [OwnerLocation(*row) for row in cur.fetchall()]


def latest_primary_owner_device_location(conn: psycopg.Connection) -> OwnerLocation | None:
    """The primary device's latest reading, used for away-correlation and the
    map trail - None if no device is marked primary or it has no location yet."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT odl.id, odl.device_id, odl.recorded_at, odl.lat, odl.lon, odl.horizontal_accuracy
            FROM owner_device_locations odl
            JOIN owner_devices od ON od.id = odl.device_id
            WHERE od.is_primary
            ORDER BY odl.recorded_at DESC LIMIT 1
            """
        )
        row = cur.fetchone()
        return OwnerLocation(*row) if row else None


def fetch_owner_device_location_history(
    conn: psycopg.Connection, device_id: str, limit: int = 200
) -> list[OwnerLocation]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, device_id, recorded_at, lat, lon, horizontal_accuracy "
            "FROM owner_device_locations WHERE device_id = %s "
            "ORDER BY recorded_at DESC LIMIT %s",
            (device_id, limit),
        )
        return [OwnerLocation(*row) for row in cur.fetchall()]
