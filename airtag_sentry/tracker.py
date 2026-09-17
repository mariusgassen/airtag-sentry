"""Core poll: restore Apple session -> fetch location history -> dedupe insert ->
movement check -> notify -> publish to Home Assistant.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import logging
import threading

from findmy import FindMyAccessory, KeyPair

from airtag_sentry import keystore
from airtag_sentry.auth import is_connected, restore_account
from airtag_sentry.config import Config
from airtag_sentry.db import (
    Alert as DbAlert,
)
from airtag_sentry.db import (
    AirtagRecord,
    AppSettings,
    OwnerLocation,
    Report,
    count_reports,
    fetch_reports_before,
    get_airtag_key,
    get_conn,
    get_geocoded_point,
    get_settings,
    insert_reports,
    list_airtags,
    list_owner_devices,
    primary_owner_device_latest_location,
    primary_owner_device_location_near,
    record_alert,
    record_owner_device_location,
    round_coord,
    store_geocoded_point,
)
from airtag_sentry.geocode import format_location_line, reverse_geocode
from airtag_sentry.movement import (
    MovementConfig,
    evaluate_away,
    evaluate_movement,
    is_speed_outlier,
    owner_already_reunited,
)
from airtag_sentry.notifiers import build_notifiers, notify_all
from airtag_sentry.notifiers.homeassistant import HomeAssistantPublisher, build_ha_publisher
from airtag_sentry.owner_tracking import fetch_owner_device_locations

logger = logging.getLogger(__name__)

# Top 2 bits of FindMy.py's LocationReport.status byte - same encoding as the
# library's own scanner.BATTERY_LEVEL, which only OfflineFindingDevice (local
# BLE scans) exposes as a property; LocationReport only gives the raw byte.
_BATTERY_LEVELS = {0b00: "full", 0b01: "medium", 0b10: "low", 0b11: "very_low"}


def _battery_level(status: int) -> str:
    return _BATTERY_LEVELS[(status >> 6) & 0b11]


_ALERT_TITLES = {
    "distance_threshold": "Unerwartete Bewegung",
    "stillstand_movement": "Bewegung nach Stillstand",
    "moved_without_owner": "Bewegung ohne dich",
}

# Which AppSettings switch gates a notification for each alert reason (see
# Settings ⚙️ -> Benachrichtigungen). record_alert() below is never gated by
# these - an alert is always recorded (so Verlauf/alert history stays
# complete) whether or not it also sends a Telegram/push notification.
_NOTIFY_SETTINGS_FIELD = {
    "distance_threshold": "notify_on_distance_threshold",
    "stillstand_movement": "notify_on_stillstand_movement",
    "moved_without_owner": "notify_on_moved_without_owner",
}


def _should_notify(settings: AppSettings, reason: str) -> bool:
    return getattr(settings, _NOTIFY_SETTINGS_FIELD[reason])


def _load_key(cfg: Config, conn, airtag_id: str):
    stored = get_airtag_key(conn, airtag_id)
    if stored is None:
        raise RuntimeError(
            f"No key stored for airtag '{airtag_id}' - add one via the dashboard's "
            "Manage AirTags panel."
        )
    plaintext = keystore.decrypt(cfg.key_encryption_key, stored.encrypted_data)
    if stored.key_type == "accessory_json":
        return FindMyAccessory.from_json(json.loads(plaintext))
    return KeyPair.from_b64(plaintext)


def _geocode_new_points(conn, points: list[tuple[float, float]]) -> None:
    """Best-effort: geocodes any of `points` not already in geocoded_points,
    deduping by the same ~1m rounding the cache uses so a stay's several
    pings only trigger one real Nominatim call. Runs on the background
    scheduler thread, never blocking the web app - a failed lookup just
    leaves that coordinate ungeocoded until it's seen again."""
    seen: set[tuple[float, float]] = set()
    for lat, lon in points:
        key = round_coord(lat, lon)
        if key in seen:
            continue
        seen.add(key)
        if get_geocoded_point(conn, lat, lon) is not None:
            continue
        try:
            result = reverse_geocode(lat, lon)
        except Exception:
            logger.exception("Reverse geocoding failed for (%s, %s).", lat, lon)
            continue
        if result.address is not None or result.poi_name is not None:
            store_geocoded_point(conn, lat, lon, result.address, result.poi_name)


def _update_owner_devices(cfg: Config, conn, ha_publisher: HomeAssistantPublisher | None) -> None:
    """Best-effort refresh of every enabled owner device's location. Never allowed
    to break AirTag polling - a failure here just means this poll's away-correlation
    falls back to whatever was recorded last time (or skips it, if nothing ever was).
    fetch_owner_device_locations() itself returns [] immediately if owner tracking
    was never connected via the dashboard, so no separate "is it configured" check
    is needed here."""
    try:
        locations = fetch_owner_device_locations(cfg, conn)
    except Exception:
        logger.exception("Failed to fetch owner device locations this poll.")
        return
    if not locations:
        logger.info("No owner device locations available this poll.")
        return
    devices_by_id = {d.id: d for d in list_owner_devices(conn)} if ha_publisher is not None else {}
    for location in locations:
        record_owner_device_location(conn, location)
        if ha_publisher is not None:
            device = devices_by_id.get(location.device_id)
            name = (device.display_name or device.name) if device else location.device_id
            try:
                ha_publisher.publish_owner_device(
                    location.device_id,
                    name,
                    location.lat,
                    location.lon,
                    location.horizontal_accuracy,
                    location.battery_level,
                )
            except Exception:
                logger.exception("Failed to publish owner device '%s' to Home Assistant.", location.device_id)
    _geocode_new_points(conn, [(loc.lat, loc.lon) for loc in locations])


def _owner_location_for_away_check(
    cfg: Config, conn, near_timestamp: dt.datetime, max_age_minutes: float
) -> OwnerLocation | None:
    """The primary owner device's reading closest to `near_timestamp`, doing one
    on-demand live Apple fetch first if what's already recorded is missing or
    too old to trust - rather than silently accepting stale data and letting
    evaluate_away() abstain. _update_owner_devices() already refreshes this
    once per poll cycle, but that snapshot can still be older than
    `max_age_minutes` by the time a particular AirTag's movement alert is
    being evaluated (Apple round trips take real wall-clock time); this only
    runs when a movement alert actually fired, so it's a rare extra Apple
    call, not one per report."""
    location = primary_owner_device_location_near(conn, near_timestamp)
    if location is not None and abs(near_timestamp - location.recorded_at) <= dt.timedelta(minutes=max_age_minutes):
        return location

    try:
        fresh_locations = fetch_owner_device_locations(cfg, conn)
    except Exception:
        logger.exception("On-demand owner-location refresh failed during away-correlation.")
        return location  # fall back to whatever was already recorded, stale or not
    for fresh_location in fresh_locations:
        record_owner_device_location(conn, fresh_location)
    return primary_owner_device_location_near(conn, near_timestamp)


# Guards against two poll_once() calls racing each other - the scheduled
# background poll (scheduler.py) and a dashboard-triggered manual "refresh
# now" (web/app.py's /api/poll-now) run on different threads with no other
# coordination between them, and overlapping runs could interleave writes to
# the same Apple session file (account.to_json) or double-fire alerts.
_poll_lock = threading.Lock()


def poll_once(cfg: Config) -> bool:
    """Owner-device tracking and AirTag tracking are two independent Apple
    sessions (see owner_tracking.py's module docstring) - connecting only one
    of them must not stop the other from polling. _update_owner_devices() runs
    unconditionally; the AirTag session is only restored/polled if one has
    actually been connected via the dashboard.

    Returns False (and does nothing else) if another poll is already running -
    the caller can treat that the same as a completed poll, since the
    in-progress one will have produced equally fresh data by the time it's
    done."""
    if not _poll_lock.acquire(blocking=False):
        logger.info("Skipping poll - one is already in progress.")
        return False
    try:
        with get_conn(cfg.database_url) as conn:
            settings = get_settings(conn)
            notifiers = build_notifiers(cfg, conn)
            ha_publisher = build_ha_publisher(cfg, conn)
            try:
                _update_owner_devices(cfg, conn, ha_publisher)

                if not is_connected(cfg):
                    logger.info("AirTag tracking not connected - skipping AirTag poll this cycle.")
                    return True

                account = restore_account(cfg)
                for airtag in list_airtags(conn):
                    try:
                        _poll_airtag(cfg, account, airtag, conn, notifiers, settings, ha_publisher)
                    except Exception:
                        logger.exception("Poll failed for airtag '%s' (%s)", airtag.id, airtag.name)
                    finally:
                        account.to_json(cfg.apple.store_path)  # tokens can rotate on any call
            finally:
                if ha_publisher is not None:
                    ha_publisher.close()
    finally:
        _poll_lock.release()
    return True


def _poll_airtag(
    cfg: Config,
    account,
    airtag: AirtagRecord,
    conn,
    notifiers,
    settings: AppSettings,
    ha_publisher: HomeAssistantPublisher | None,
) -> None:
    key = _load_key(cfg, conn, airtag.id)
    location_reports = account.fetch_location_history(key)

    if not location_reports:
        logger.info("[%s] No location reports returned this poll.", airtag.id)
        return

    reports = [
        Report(
            id=None,
            airtag_id=airtag.id,
            timestamp=lr.timestamp,
            lat=lr.latitude,
            lon=lr.longitude,
            accuracy=lr.horizontal_accuracy,
            confidence=lr.confidence,
            battery_level=_battery_level(lr.status),
        )
        for lr in location_reports
    ]
    reports.sort(key=lambda r: r.timestamp)

    movement_cfg = MovementConfig(
        distance_threshold_meters=settings.movement_distance_threshold_meters,
        stillstand_hours=settings.movement_stillstand_hours,
        stillstand_movement_meters=settings.movement_stillstand_movement_meters,
        alert_on_backfill=settings.movement_alert_on_backfill,
        away_distance_threshold_meters=settings.movement_away_distance_meters,
        owner_location_max_age_minutes=settings.owner_location_max_age_minutes,
        max_speed_kmh=settings.movement_max_speed_kmh,
    )

    # Flag reports whose implied speed from the last physically-plausible
    # (kept) report is impossible for an AirTag - a bad crowd-sourced
    # Bluetooth relay, not real movement (see movement.is_speed_outlier).
    # Done before insert, against a baseline that starts from what's already
    # in the DB, so a flagged report can never anchor the next comparison.
    baseline_reports = fetch_reports_before(conn, airtag.id, reports[0].timestamp)
    baseline = baseline_reports[-1] if baseline_reports else None
    flagged_reports = []
    for report in reports:
        outlier = is_speed_outlier(report, baseline, movement_cfg)
        flagged_reports.append(dataclasses.replace(report, is_outlier=outlier))
        if not outlier:
            baseline = report
    reports = flagged_reports

    was_empty = count_reports(conn, airtag.id) == 0
    newly_inserted = insert_reports(conn, reports)

    if not newly_inserted:
        logger.info("[%s] No new reports (all %d already known).", airtag.id, len(reports))
        return

    logger.info("[%s] Inserted %d new report(s).", airtag.id, len(newly_inserted))

    if ha_publisher is not None:
        kept = [r for r in reports if not r.is_outlier]
        latest = max(kept, key=lambda r: r.timestamp) if kept else None
        if latest is not None:
            try:
                ha_publisher.publish_airtag(
                    airtag.id, airtag.name, latest.lat, latest.lon, latest.accuracy, latest.battery_level
                )
            except Exception:
                logger.exception("Failed to publish airtag '%s' to Home Assistant.", airtag.id)

    if was_empty and not settings.movement_alert_on_backfill:
        logger.info(
            "[%s] First-ever poll: skipping alerts for the %d backfilled report(s).",
            airtag.id,
            len(newly_inserted),
        )
    else:
        for report in newly_inserted:
            if report.is_outlier:
                logger.info(
                    "[%s] Report at %s flagged as a speed outlier - skipping alert evaluation.",
                    airtag.id,
                    report.timestamp,
                )
                continue

            prior_reports = fetch_reports_before(conn, airtag.id, report.timestamp)
            alert = evaluate_movement(report, prior_reports, movement_cfg)
            if alert is None:
                continue

            record_alert(
                conn,
                DbAlert(
                    airtag_id=airtag.id,
                    reason=alert.reason,
                    distance_meters=alert.distance_meters,
                    report_id=report.id,
                ),
            )
            address = reverse_geocode(report.lat, report.lon).address
            if _should_notify(settings, alert.reason):
                message = (
                    f"{airtag.name} hat sich um {alert.distance_meters:.0f} m bewegt.\n"
                    f"{format_location_line(report.lat, report.lon, report.timestamp, address, cfg.display_timezone)}"
                )
                notify_all(notifiers, _ALERT_TITLES[alert.reason], message)

            owner_location = _owner_location_for_away_check(
                cfg, conn, report.timestamp, movement_cfg.owner_location_max_age_minutes
            )
            away_distance = evaluate_away(report, owner_location, movement_cfg)
            if away_distance is not None:
                record_alert(
                    conn,
                    DbAlert(
                        airtag_id=airtag.id,
                        reason="moved_without_owner",
                        distance_meters=away_distance,
                        report_id=report.id,
                    ),
                )
                if _should_notify(settings, "moved_without_owner") and not owner_already_reunited(
                    report, primary_owner_device_latest_location(conn), movement_cfg
                ):
                    away_message = (
                        f"{airtag.name} hat sich {away_distance:.0f} m von dir entfernt bewegt.\n"
                        f"{format_location_line(report.lat, report.lon, report.timestamp, address, cfg.display_timezone)}"
                    )
                    notify_all(notifiers, _ALERT_TITLES["moved_without_owner"], away_message)

    _geocode_new_points(conn, [(r.lat, r.lon) for r in newly_inserted if not r.is_outlier])
