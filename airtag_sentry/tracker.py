"""Core poll: restore Apple session -> fetch location history -> dedupe insert ->
movement check -> notify.
"""

from __future__ import annotations

import datetime as dt
import json
import logging

from findmy import FindMyAccessory, KeyPair

from airtag_sentry import keystore
from airtag_sentry.auth import restore_account
from airtag_sentry.config import Config
from airtag_sentry.db import (
    Alert as DbAlert,
)
from airtag_sentry.db import (
    AirtagRecord,
    AppSettings,
    Report,
    count_reports,
    fetch_reports_before,
    get_airtag_key,
    get_conn,
    get_settings,
    insert_reports,
    latest_owner_location,
    list_airtags,
    record_alert,
    record_owner_location,
)
from airtag_sentry.movement import MovementConfig, evaluate_away, evaluate_movement
from airtag_sentry.notifiers import build_notifiers, notify_all
from airtag_sentry.owner_tracking import fetch_owner_location

logger = logging.getLogger(__name__)

_ALERT_TITLES = {
    "distance_threshold": "AirTagSentry: unerwartete Bewegung",
    "stillstand_movement": "AirTagSentry: Bewegung nach Stillstand",
    "moved_without_owner": "AirTagSentry: Bewegung ohne dich",
}


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


def _update_owner_location(cfg: Config, conn) -> None:
    """Best-effort refresh of the owner's device location. Never allowed to break
    AirTag polling - a failure here just means this poll's away-correlation falls
    back to whatever was recorded last time (or skips it, if nothing ever was).
    fetch_owner_location() itself returns None immediately if owner tracking was
    never connected via the dashboard, so no separate "is it configured" check
    is needed here."""
    try:
        location = fetch_owner_location(cfg, conn)
    except Exception:
        logger.exception("Failed to fetch owner device location this poll.")
        return
    if location is None:
        logger.info("No owner device location available this poll.")
        return
    record_owner_location(conn, location)


def poll_once(cfg: Config) -> None:
    account = restore_account(cfg)

    with get_conn(cfg.database_url) as conn:
        settings = get_settings(conn)
        notifiers = build_notifiers(cfg)
        _update_owner_location(cfg, conn)
        for airtag in list_airtags(conn):
            try:
                _poll_airtag(cfg, account, airtag, conn, notifiers, settings)
            except Exception:
                logger.exception("Poll failed for airtag '%s' (%s)", airtag.id, airtag.name)
            finally:
                account.to_json(cfg.apple.store_path)  # tokens can rotate on any call


def _poll_airtag(
    cfg: Config, account, airtag: AirtagRecord, conn, notifiers, settings: AppSettings
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
        )
        for lr in location_reports
    ]

    was_empty = count_reports(conn, airtag.id) == 0
    newly_inserted = insert_reports(conn, reports)

    if not newly_inserted:
        logger.info("[%s] No new reports (all %d already known).", airtag.id, len(reports))
        return

    logger.info("[%s] Inserted %d new report(s).", airtag.id, len(newly_inserted))

    if was_empty and not settings.movement_alert_on_backfill:
        logger.info(
            "[%s] First-ever poll: skipping alerts for the %d backfilled report(s).",
            airtag.id,
            len(newly_inserted),
        )
        return

    movement_cfg = MovementConfig(
        distance_threshold_meters=settings.movement_distance_threshold_meters,
        stillstand_hours=settings.movement_stillstand_hours,
        stillstand_movement_meters=settings.movement_stillstand_movement_meters,
        alert_on_backfill=settings.movement_alert_on_backfill,
        away_distance_threshold_meters=settings.movement_away_distance_meters,
        owner_location_max_age_minutes=settings.owner_location_max_age_minutes,
    )
    for report in newly_inserted:
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
        message = (
            f"{airtag.name} hat sich um {alert.distance_meters:.0f} m bewegt "
            f"(Report {report.timestamp.isoformat()})."
        )
        notify_all(notifiers, _ALERT_TITLES[alert.reason], message)

        away_distance = evaluate_away(
            report, latest_owner_location(conn), dt.datetime.now(dt.timezone.utc), movement_cfg
        )
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
            away_message = (
                f"{airtag.name} hat sich {away_distance:.0f} m von dir entfernt bewegt "
                f"(Report {report.timestamp.isoformat()})."
            )
            notify_all(notifiers, _ALERT_TITLES["moved_without_owner"], away_message)
