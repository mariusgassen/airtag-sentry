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
    # Whether this AirTag is evaluated at all when it ends up far from the
    # primary owner device (as "left_behind" or "autonomous_movement" - see
    # CLAUDE.md) - defaults true, preserving the behavior from before this
    # was per-object (still gated by the account-wide notify_on_left_behind/
    # notify_on_autonomous_movement switches too). Mirrors OwnerDevice's own
    # away_alert_enabled, which defaults false instead - see its docstring
    # for why the defaults differ.
    away_alert_enabled: bool = True
    # User-controlled display order in ObjectsList.tsx (see set_airtags_order)
    # - lower sorts first. Mirrors OwnerDevice.sort_order; compare=False for
    # the same reason (presentation-only, not part of an AirTag's identity).
    sort_order: int = dataclasses.field(default=0, compare=False)


@dataclasses.dataclass(frozen=True)
class Report:
    id: int | None
    airtag_id: str
    timestamp: dt.datetime
    lat: float
    lon: float
    accuracy: float | None
    confidence: int | None
    # Decoded from FindMy.py's LocationReport.status top 2 bits (see
    # tracker._battery_level): "full" | "medium" | "low" | "very_low", or None
    # for older rows recorded before this column existed.
    battery_level: str | None = None
    # Set by tracker._poll_airtag (see movement.is_speed_outlier) when this
    # report's implied travel speed from the prior *kept* report is
    # physically implausible - a bad crowd-sourced Bluetooth relay, not real
    # movement. Still stored for completeness, but fetch_reports/
    # fetch_reports_before both exclude it: it never appears on the map
    # trail/stays and is never evaluated for a movement alert.
    is_outlier: bool = False


@dataclasses.dataclass(frozen=True)
class Alert:
    """Polymorphic: exactly one of (airtag_id, report_id) or (owner_device_id,
    owner_location_id) is set, matching the alerts table's alerts_source_xor
    CHECK - an AirTag's own movement/away alert, or a non-primary owner
    device's "left without you" alert (see tracker._evaluate_device_away_alerts).
    """

    reason: str
    distance_meters: float
    airtag_id: str | None = None
    report_id: int | None = None
    owner_device_id: str | None = None
    owner_location_id: int | None = None


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
    # Whether pyicloud's PyiCloudService is built with with_family=True, which
    # pulls Family Sharing members' devices into api.devices alongside the
    # account's own. Off by default (opt-in via the connect dialog's
    # checkbox) - this app only ever wants "my own" devices, see CLAUDE.md's
    # single-user constraint.
    include_family_devices: bool = False
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
    # set_owner_device_primary(). The primary device is the one *other*
    # objects (AirTags, and any other enabled device with away_alert_enabled)
    # get compared against for "moved without you"/away-correlation, and its
    # history is drawn as the map trail; the primary device is never itself
    # evaluated for an away alert - it defines where "you" are.
    is_primary: bool
    # User-chosen name/icon/color, mirroring AirtagRecord's - None means
    # "unset", i.e. fall back to `name` (the Apple-synced technical name) /
    # the derived glyph+color. `upsert_owner_devices` never touches these,
    # unlike `name` - see rename_owner_device/set_owner_device_appearance.
    display_name: str | None = None
    icon: str | None = None
    color: str | None = None
    # Whether this device raises a "you left without it" alert when it ends
    # up far from the primary device - mirrors AirtagRecord.away_alert_enabled,
    # but defaults false: unlike an AirTag (which already had this alert
    # unconditionally before it became per-object), a device never had any
    # away-alerting at all, and turning it on for every Mac/iPad/etc. in the
    # account the moment this shipped would be a surprise, not a fix. Ignored
    # for whichever device is currently primary (see is_primary above).
    away_alert_enabled: bool = False
    # Set to the poll's timestamp every time this device appears in a
    # *successful* live Apple device listing (upsert_owner_devices, called for
    # every device the account has - see owner_tracking.py). Comparing this
    # against OwnerAppleCredentials.last_sync_at (the same poll's timestamp)
    # tells whether this device was present in the most recent successful
    # sync, or has gone missing from the account (e.g. removed from iCloud) -
    # see GET /api/owner-devices' `on_account` field.
    last_seen_at: dt.datetime | None = None
    # User-controlled display order in ObjectsList.tsx/TimelinePage.tsx (see
    # set_owner_devices_order) - lower sorts first. A newly-discovered device
    # is appended after the current max (see upsert_owner_devices), never
    # inserted into the middle of an existing order. compare=False: it's
    # presentation-only, not part of a device's identity, so tests comparing
    # OwnerDevice instances for equality don't need to track it.
    sort_order: int = dataclasses.field(default=0, compare=False)


@dataclasses.dataclass(frozen=True)
class OwnerLocation:
    id: int | None
    device_id: str
    recorded_at: dt.datetime
    lat: float
    lon: float
    horizontal_accuracy: float | None
    # From pyicloud's AppleDevice content dict (owner_tracking._snapshot_devices):
    # battery_level is a 0.0-1.0 fraction, battery_status a raw Apple string
    # ("Charging"/"NotCharging"/"Unplugged"). Both None for older rows or a
    # device that didn't report battery this poll.
    battery_level: float | None = None
    battery_status: str | None = None
    # Whether *this* poll's own Apple response actually included a battery
    # reading - false means battery_level/battery_status above were carried
    # forward from a previous row (or, with no previous reading either, are
    # just None) by record_owner_device_location's gap-fill. Lets a later
    # feature (e.g. a battery-over-time chart) distinguish a real reading
    # from a filled gap instead of seeing an unbroken line of values.
    battery_reported: bool = False


@dataclasses.dataclass(frozen=True)
class CartoCredentials:
    api_key_encrypted: str


@dataclasses.dataclass(frozen=True)
class MqttCredentials:
    host: str
    port: int
    username: str | None
    password_encrypted: str | None
    use_tls: bool


@dataclasses.dataclass(frozen=True)
class HaApiToken:
    # Hashed (sha256), not encrypted - unlike the Telegram bot token or MQTT
    # password, we never need the plaintext back, only to compare a presented
    # bearer token against it (see web/app.py's GET /api/ha/state).
    token_hash: str
    created_at: dt.datetime


@dataclasses.dataclass(frozen=True)
class NamedPlace:
    id: int
    name: str
    lat: float
    lon: float
    radius_meters: float


@dataclasses.dataclass(frozen=True)
class GeocodedPoint:
    lat_rounded: float
    lon_rounded: float
    address: str | None
    poi_name: str | None


@dataclasses.dataclass(frozen=True)
class AppSettings:
    polling_interval_minutes: int
    movement_distance_threshold_meters: float
    movement_stillstand_hours: float
    movement_stillstand_movement_meters: float
    movement_alert_on_backfill: bool
    movement_away_distance_meters: float
    owner_location_max_age_minutes: float
    # Implied speed (km/h) from the prior kept report above which a new
    # AirTag report is treated as a crowd-sourced relay outlier rather than
    # real movement - see movement.is_speed_outlier. Generous enough for
    # car/train travel, well below what a bad relay implies.
    movement_max_speed_kmh: float
    history_cluster_radius_meters: float
    color_palette: str
    # 'auto' (default): CARTO Voyager/Dark Matter tiles when an API key is
    # configured (see carto_settings/mapTiles.ts), else plain OSM. 'osm':
    # always plain OSM, even with a key configured - for anyone who'd rather
    # not use the CARTO style.
    map_tile_provider: str
    # Whether each alert reason (see tracker.py's _ALERT_TITLES) sends a
    # Telegram/push notification at all - independent of which notifier
    # channels are configured. An alert is always recorded (record_alert)
    # regardless of these, so Verlauf/alert history stays complete either
    # way; this only gates notify_all().
    notify_on_distance_threshold: bool
    notify_on_stillstand_movement: bool
    # Split from a single notify_on_moved_without_owner (see CLAUDE.md's
    # "you left it" vs "it left you" constraint) - left_behind is routine
    # (you moved away from a stationary object), autonomous_movement is the
    # actual signal this app exists to catch (the object moved on its own).
    # Independently toggleable so one can be silenced without the other.
    notify_on_left_behind: bool
    notify_on_autonomous_movement: bool


@contextmanager
def get_conn(database_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(database_url) as conn:
        yield conn


_AIRTAG_COLUMNS = "id, name, icon, color, away_alert_enabled, sort_order"


def create_airtag(conn: psycopg.Connection, airtag_id: str, name: str) -> AirtagRecord:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO airtags (id, name, sort_order)
            VALUES (%s, %s, COALESCE((SELECT MAX(sort_order) FROM airtags), -1) + 1)
            RETURNING {_AIRTAG_COLUMNS}
            """,
            (airtag_id, name),
        )
        row = cur.fetchone()
    conn.commit()
    return AirtagRecord(*row)


def list_airtags(conn: psycopg.Connection) -> list[AirtagRecord]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_AIRTAG_COLUMNS} FROM airtags ORDER BY sort_order, created_at ASC")
        return [AirtagRecord(*row) for row in cur.fetchall()]


def rename_airtag(conn: psycopg.Connection, airtag_id: str, name: str) -> AirtagRecord | None:
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE airtags SET name = %s WHERE id = %s RETURNING {_AIRTAG_COLUMNS}",
            (name, airtag_id),
        )
        row = cur.fetchone()
    conn.commit()
    return AirtagRecord(*row) if row else None


def set_airtags_order(conn: psycopg.Connection, airtag_ids: list[str]) -> None:
    """Assigns sequential sort_order values (0, 1, 2, ...) to exactly the
    given ids, in the given order - see PUT /api/airtags/order. Mirrors
    set_owner_devices_order."""
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE airtags SET sort_order = %s WHERE id = %s",
            list(enumerate(airtag_ids)),
        )
    conn.commit()


def set_airtag_appearance(
    conn: psycopg.Connection, airtag_id: str, icon: str | None, color: str | None
) -> AirtagRecord | None:
    """Set (or, with both args None, reset to automatic) an AirTag's chosen
    icon/color. Both fields are always written together since the picker UI
    always submits both current values."""
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE airtags SET icon = %s, color = %s WHERE id = %s RETURNING {_AIRTAG_COLUMNS}",
            (icon, color, airtag_id),
        )
        row = cur.fetchone()
    conn.commit()
    return AirtagRecord(*row) if row else None


def set_airtag_away_alert_enabled(conn: psycopg.Connection, airtag_id: str, enabled: bool) -> AirtagRecord | None:
    """Mirrors set_owner_device_away_alert_enabled."""
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE airtags SET away_alert_enabled = %s WHERE id = %s RETURNING {_AIRTAG_COLUMNS}",
            (enabled, airtag_id),
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
                INSERT INTO location_reports
                    (airtag_id, timestamp, lat, lon, accuracy, confidence, battery_level, is_outlier)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (airtag_id, "timestamp") DO NOTHING
                RETURNING id, airtag_id, timestamp, lat, lon, accuracy, confidence, battery_level, is_outlier
                """,
                (
                    report.airtag_id,
                    report.timestamp,
                    report.lat,
                    report.lon,
                    report.accuracy,
                    report.confidence,
                    report.battery_level,
                    report.is_outlier,
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


_REPORT_COLUMNS = 'id, airtag_id, "timestamp", lat, lon, accuracy, confidence, battery_level, is_outlier'


def fetch_reports(conn: psycopg.Connection, airtag_id: str, limit: int | None = None) -> list[Report]:
    """Never returns is_outlier reports - see Report.is_outlier. Callers that
    need the raw, unfiltered history (currently none) would need a separate
    query."""
    query = (
        f"SELECT {_REPORT_COLUMNS} FROM location_reports "
        'WHERE airtag_id = %s AND NOT is_outlier ORDER BY "timestamp" ASC'
    )
    params: tuple = (airtag_id,)
    if limit is not None:
        query = (
            f"SELECT {_REPORT_COLUMNS} FROM ("
            f"SELECT {_REPORT_COLUMNS} FROM location_reports "
            'WHERE airtag_id = %s AND NOT is_outlier ORDER BY "timestamp" DESC LIMIT %s'
            ") sub ORDER BY \"timestamp\" ASC"
        )
        params = (airtag_id, limit)
    with conn.cursor() as cur:
        cur.execute(query, params)
        return [Report(*row) for row in cur.fetchall()]


def fetch_reports_before(
    conn: psycopg.Connection, airtag_id: str, timestamp: dt.datetime
) -> list[Report]:
    """Never returns is_outlier reports, so movement detection always
    compares against the last physically-plausible position - see
    Report.is_outlier."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_REPORT_COLUMNS} FROM location_reports "
            'WHERE airtag_id = %s AND "timestamp" < %s AND NOT is_outlier ORDER BY "timestamp" ASC',
            (airtag_id, timestamp),
        )
        return [Report(*row) for row in cur.fetchall()]


def record_alert(conn: psycopg.Connection, alert: Alert) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO alerts (airtag_id, reason, distance_meters, report_id, owner_device_id, owner_location_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                alert.airtag_id,
                alert.reason,
                alert.distance_meters,
                alert.report_id,
                alert.owner_device_id,
                alert.owner_location_id,
            ),
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


def set_owner_apple_credentials(
    conn: psycopg.Connection, apple_id: str, encrypted_password: str, include_family_devices: bool = False
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO owner_apple_credentials
                (id, apple_id, encrypted_password, include_family_devices, updated_at, last_sync_at, last_sync_error)
            VALUES (1, %s, %s, %s, now(), NULL, NULL)
            ON CONFLICT (id) DO UPDATE
                SET apple_id = EXCLUDED.apple_id,
                    encrypted_password = EXCLUDED.encrypted_password,
                    include_family_devices = EXCLUDED.include_family_devices,
                    updated_at = now(),
                    -- A fresh login shouldn't carry forward a previous
                    -- connection's stale sync error.
                    last_sync_at = NULL,
                    last_sync_error = NULL
            """,
            (apple_id, encrypted_password, include_family_devices),
        )
    conn.commit()


def set_owner_include_family_devices(conn: psycopg.Connection, include_family_devices: bool) -> bool:
    """Flips the Family Sharing filter on an already-connected account, without
    touching the stored password - unlike set_owner_apple_credentials (a full
    login upsert), this only ever runs against an existing row. Returns False
    (no-op) if owner tracking isn't connected."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE owner_apple_credentials SET include_family_devices = %s, updated_at = now() WHERE id = 1",
            (include_family_devices,),
        )
        updated = cur.rowcount > 0
    conn.commit()
    return updated


def get_owner_apple_credentials(conn: psycopg.Connection) -> OwnerAppleCredentials | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT apple_id, encrypted_password, include_family_devices, last_sync_at, last_sync_error "
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


def set_carto_credentials(conn: psycopg.Connection, api_key_encrypted: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO carto_settings (id, api_key_encrypted, updated_at)
            VALUES (1, %s, now())
            ON CONFLICT (id) DO UPDATE
                SET api_key_encrypted = EXCLUDED.api_key_encrypted,
                    updated_at = now()
            """,
            (api_key_encrypted,),
        )
    conn.commit()


def get_carto_credentials(conn: psycopg.Connection) -> CartoCredentials | None:
    with conn.cursor() as cur:
        cur.execute("SELECT api_key_encrypted FROM carto_settings WHERE id = 1")
        row = cur.fetchone()
        return CartoCredentials(*row) if row else None


def delete_carto_credentials(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM carto_settings WHERE id = 1")
    conn.commit()


def set_mqtt_credentials(
    conn: psycopg.Connection,
    host: str,
    port: int,
    username: str | None,
    password_encrypted: str | None,
    use_tls: bool,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mqtt_settings (id, host, port, username, password_encrypted, use_tls, updated_at)
            VALUES (1, %s, %s, %s, %s, %s, now())
            ON CONFLICT (id) DO UPDATE
                SET host = EXCLUDED.host,
                    port = EXCLUDED.port,
                    username = EXCLUDED.username,
                    password_encrypted = EXCLUDED.password_encrypted,
                    use_tls = EXCLUDED.use_tls,
                    updated_at = now()
            """,
            (host, port, username, password_encrypted, use_tls),
        )
    conn.commit()


def get_mqtt_credentials(conn: psycopg.Connection) -> MqttCredentials | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT host, port, username, password_encrypted, use_tls FROM mqtt_settings WHERE id = 1"
        )
        row = cur.fetchone()
        return MqttCredentials(*row) if row else None


def delete_mqtt_credentials(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM mqtt_settings WHERE id = 1")
    conn.commit()


def set_ha_api_token_hash(conn: psycopg.Connection, token_hash: str) -> None:
    """Replaces any existing token (single-row table) - generating a new one
    invalidates the old one immediately."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ha_api_tokens (id, token_hash, created_at)
            VALUES (1, %s, now())
            ON CONFLICT (id) DO UPDATE SET token_hash = EXCLUDED.token_hash, created_at = now()
            """,
            (token_hash,),
        )
    conn.commit()


def get_ha_api_token(conn: psycopg.Connection) -> HaApiToken | None:
    with conn.cursor() as cur:
        cur.execute("SELECT token_hash, created_at FROM ha_api_tokens WHERE id = 1")
        row = cur.fetchone()
        return HaApiToken(*row) if row else None


def delete_ha_api_token(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ha_api_tokens WHERE id = 1")
    conn.commit()


_SETTINGS_COLUMNS = (
    "polling_interval_minutes",
    "movement_distance_threshold_meters",
    "movement_stillstand_hours",
    "movement_stillstand_movement_meters",
    "movement_alert_on_backfill",
    "movement_away_distance_meters",
    "owner_location_max_age_minutes",
    "movement_max_speed_kmh",
    "history_cluster_radius_meters",
    "color_palette",
    "map_tile_provider",
    "notify_on_distance_threshold",
    "notify_on_stillstand_movement",
    "notify_on_left_behind",
    "notify_on_autonomous_movement",
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
                movement_max_speed_kmh = %s,
                history_cluster_radius_meters = %s,
                color_palette = %s,
                map_tile_provider = %s,
                notify_on_distance_threshold = %s,
                notify_on_stillstand_movement = %s,
                notify_on_left_behind = %s,
                notify_on_autonomous_movement = %s,
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
                settings.movement_max_speed_kmh,
                settings.history_cluster_radius_meters,
                settings.color_palette,
                settings.map_tile_provider,
                settings.notify_on_distance_threshold,
                settings.notify_on_stillstand_movement,
                settings.notify_on_left_behind,
                settings.notify_on_autonomous_movement,
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
            INSERT INTO owner_devices (id, name, device_type, last_seen_at, sort_order)
            VALUES (
                %(id)s, %(name)s, %(device_type)s, %(seen_at)s,
                COALESCE((SELECT MAX(sort_order) FROM owner_devices), -1) + 1
            )
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, device_type = EXCLUDED.device_type,
                last_seen_at = EXCLUDED.last_seen_at
            """,
            rows,
        )
    conn.commit()


_OWNER_DEVICE_COLUMNS = (
    "id, name, device_type, enabled, is_primary, display_name, icon, color, "
    "away_alert_enabled, last_seen_at, sort_order"
)


def list_owner_devices(conn: psycopg.Connection) -> list[OwnerDevice]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_OWNER_DEVICE_COLUMNS} FROM owner_devices ORDER BY sort_order, name")
        return [OwnerDevice(*row) for row in cur.fetchall()]


def set_owner_devices_order(conn: psycopg.Connection, device_ids: list[str]) -> None:
    """Assigns sequential sort_order values (0, 1, 2, ...) to exactly the
    given ids, in the given order - see PUT /api/owner-devices/order. Devices
    not included (e.g. disabled ones ObjectsList never shows) keep whatever
    sort_order they already had."""
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE owner_devices SET sort_order = %s WHERE id = %s",
            list(enumerate(device_ids)),
        )
    conn.commit()


def delete_owner_device(conn: psycopg.Connection, device_id: str) -> None:
    """Forgets a device outright (cascades to its owner_device_locations, if any
    - see the table's ON DELETE CASCADE). Only meant for a device that was never
    enabled: see owner_tracking.fetch_owner_device_locations, which is the only
    caller - a device merely observed once (e.g. a family member's, while
    Family Sharing was on) and never opted into tracking has no history or
    customization worth keeping once Apple stops listing it, unlike an enabled
    device (which is disabled instead, to preserve its history/on_account
    badge)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM owner_devices WHERE id = %s", (device_id,))
    conn.commit()


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


def set_owner_device_away_alert_enabled(conn: psycopg.Connection, device_id: str, enabled: bool) -> OwnerDevice | None:
    """Mirrors set_airtag_away_alert_enabled. Meaningless (and not evaluated,
    see tracker._evaluate_device_away_alerts) for whichever device is
    currently primary, but harmless to set - it just has no effect until/
    unless that device stops being primary."""
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE owner_devices SET away_alert_enabled = %s WHERE id = %s RETURNING {_OWNER_DEVICE_COLUMNS}",
            (enabled, device_id),
        )
        row = cur.fetchone()
    conn.commit()
    return OwnerDevice(*row) if row else None


def record_owner_device_location(conn: psycopg.Connection, location: OwnerLocation) -> OwnerLocation:
    """battery_level is None whenever this particular snapshot didn't carry a
    real reading (see owner_tracking._snapshot_devices - either the device
    never reports battery at all, or Apple's batteryStatus came back
    "Unknown" for this round). A device's battery doesn't reset to "unknown"
    just because one poll's fix didn't include a fresh reading, so carry the
    most recent known battery_level/battery_status forward onto this new
    location instead of blanking out the dashboard's battery display until
    the next successful reading - battery_reported records whether *this*
    row's value is a fresh reading or an inherited one, so the raw history
    isn't lost to the display-friendly carry-forward (see OwnerLocation)."""
    battery_reported = location.battery_level is not None
    battery_level = location.battery_level
    battery_status = location.battery_status
    if battery_level is None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT battery_level, battery_status FROM owner_device_locations "
                "WHERE device_id = %s ORDER BY recorded_at DESC LIMIT 1",
                (location.device_id,),
            )
            prev = cur.fetchone()
        if prev is not None:
            battery_level, battery_status = prev

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO owner_device_locations
                (device_id, recorded_at, lat, lon, horizontal_accuracy, battery_level, battery_status, battery_reported)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, device_id, recorded_at, lat, lon, horizontal_accuracy, battery_level, battery_status, battery_reported
            """,
            (
                location.device_id,
                location.recorded_at,
                location.lat,
                location.lon,
                location.horizontal_accuracy,
                battery_level,
                battery_status,
                battery_reported,
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
                odl.id, odl.device_id, odl.recorded_at, odl.lat, odl.lon, odl.horizontal_accuracy,
                odl.battery_level, odl.battery_status, odl.battery_reported
            FROM owner_device_locations odl
            JOIN owner_devices od ON od.id = odl.device_id
            WHERE od.enabled
            ORDER BY odl.device_id, odl.recorded_at DESC
            """
        )
        return [OwnerLocation(*row) for row in cur.fetchall()]


def primary_owner_device_location_near(conn: psycopg.Connection, timestamp: dt.datetime) -> OwnerLocation | None:
    """The primary device's reading closest in time to `timestamp`, used for
    away-correlation - None if no device is marked primary or it has no
    location yet.

    Nearest-in-time rather than "most recent ever": AirTag reports are
    crowd-sourced (FindMy.py) and can arrive with real delay, so the owner
    reading that matters is the one from around when the report's own
    timestamp says the tag was there - not whatever the owner's latest
    location happens to be by the time the report is processed.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT odl.id, odl.device_id, odl.recorded_at, odl.lat, odl.lon, odl.horizontal_accuracy,
                odl.battery_level, odl.battery_status, odl.battery_reported
            FROM owner_device_locations odl
            JOIN owner_devices od ON od.id = odl.device_id
            WHERE od.is_primary
            ORDER BY ABS(EXTRACT(EPOCH FROM (odl.recorded_at - %s))) ASC LIMIT 1
            """,
            (timestamp,),
        )
        row = cur.fetchone()
        return OwnerLocation(*row) if row else None


def primary_owner_device_latest_location(conn: psycopg.Connection) -> OwnerLocation | None:
    """The primary device's single most recent reading - unlike
    `primary_owner_device_location_near`, this ignores any target timestamp
    and always returns the freshest one on record. Used to check whether the
    owner has already reunited with a tag by the time a "moved without you"
    alert is about to be sent, even though the alert's own away-correlation
    correctly used the reading closest to the triggering report's timestamp.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT odl.id, odl.device_id, odl.recorded_at, odl.lat, odl.lon, odl.horizontal_accuracy,
                odl.battery_level, odl.battery_status, odl.battery_reported
            FROM owner_device_locations odl
            JOIN owner_devices od ON od.id = odl.device_id
            WHERE od.is_primary
            ORDER BY odl.recorded_at DESC LIMIT 1
            """
        )
        row = cur.fetchone()
        return OwnerLocation(*row) if row else None


def fetch_owner_device_location_history(
    conn: psycopg.Connection, device_id: str, limit: int | None = 200
) -> list[OwnerLocation]:
    query = (
        "SELECT id, device_id, recorded_at, lat, lon, horizontal_accuracy, battery_level, battery_status, "
        "battery_reported "
        "FROM owner_device_locations WHERE device_id = %s "
        "ORDER BY recorded_at DESC"
    )
    params: tuple = (device_id,)
    if limit is not None:
        query += " LIMIT %s"
        params = (device_id, limit)
    with conn.cursor() as cur:
        cur.execute(query, params)
        return [OwnerLocation(*row) for row in cur.fetchall()]


def list_named_places(conn: psycopg.Connection) -> list[NamedPlace]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, lat, lon, radius_meters FROM named_places ORDER BY name")
        return [NamedPlace(*row) for row in cur.fetchall()]


def create_named_place(
    conn: psycopg.Connection, name: str, lat: float, lon: float, radius_meters: float
) -> NamedPlace:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO named_places (name, lat, lon, radius_meters) VALUES (%s, %s, %s, %s) "
            "RETURNING id, name, lat, lon, radius_meters",
            (name, lat, lon, radius_meters),
        )
        row = cur.fetchone()
    conn.commit()
    return NamedPlace(*row)


def update_named_place(
    conn: psycopg.Connection, place_id: int, name: str, lat: float, lon: float, radius_meters: float
) -> NamedPlace | None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE named_places SET name = %s, lat = %s, lon = %s, radius_meters = %s WHERE id = %s "
            "RETURNING id, name, lat, lon, radius_meters",
            (name, lat, lon, radius_meters, place_id),
        )
        row = cur.fetchone()
    conn.commit()
    return NamedPlace(*row) if row else None


def delete_named_place(conn: psycopg.Connection, place_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM named_places WHERE id = %s", (place_id,))
    conn.commit()


def round_coord(lat: float, lon: float) -> tuple[float, float]:
    """~1m precision - shared by geocoded_points and place_label_corrections
    so a correction overrides exactly the lookup the geocode cache uses."""
    return (round(lat, 5), round(lon, 5))


def get_geocoded_point(conn: psycopg.Connection, lat: float, lon: float) -> GeocodedPoint | None:
    lat_r, lon_r = round_coord(lat, lon)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT lat_rounded, lon_rounded, address, poi_name FROM geocoded_points "
            "WHERE lat_rounded = %s AND lon_rounded = %s",
            (lat_r, lon_r),
        )
        row = cur.fetchone()
        return GeocodedPoint(*row) if row else None


def store_geocoded_point(
    conn: psycopg.Connection, lat: float, lon: float, address: str | None, poi_name: str | None
) -> GeocodedPoint:
    lat_r, lon_r = round_coord(lat, lon)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO geocoded_points (lat_rounded, lon_rounded, address, poi_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (lat_rounded, lon_rounded) DO UPDATE SET
                address = EXCLUDED.address, poi_name = EXCLUDED.poi_name, fetched_at = now()
            RETURNING lat_rounded, lon_rounded, address, poi_name
            """,
            (lat_r, lon_r, address, poi_name),
        )
        row = cur.fetchone()
    conn.commit()
    return GeocodedPoint(*row)


def get_place_label_correction(conn: psycopg.Connection, lat: float, lon: float) -> str | None:
    lat_r, lon_r = round_coord(lat, lon)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT corrected_name FROM place_label_corrections WHERE lat_rounded = %s AND lon_rounded = %s",
            (lat_r, lon_r),
        )
        row = cur.fetchone()
        return row[0] if row else None


def set_place_label_correction(conn: psycopg.Connection, lat: float, lon: float, corrected_name: str) -> None:
    lat_r, lon_r = round_coord(lat, lon)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO place_label_corrections (lat_rounded, lon_rounded, corrected_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (lat_rounded, lon_rounded) DO UPDATE SET corrected_name = EXCLUDED.corrected_name
            """,
            (lat_r, lon_r, corrected_name),
        )
    conn.commit()


def delete_place_label_correction(conn: psycopg.Connection, lat: float, lon: float) -> None:
    lat_r, lon_r = round_coord(lat, lon)
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM place_label_corrections WHERE lat_rounded = %s AND lon_rounded = %s", (lat_r, lon_r)
        )
    conn.commit()
