"""Core poll: restore Apple session -> fetch location history -> dedupe insert ->
movement check -> notify.
"""

from __future__ import annotations

import json
import logging

from findmy import FindMyAccessory, KeyPair

from airtag_sentry import keystore
from airtag_sentry.auth import restore_account
from airtag_sentry.config import AirtagConfig, Config
from airtag_sentry.db import (
    Alert as DbAlert,
)
from airtag_sentry.db import (
    Report,
    count_reports,
    fetch_reports_before,
    get_airtag_key,
    get_conn,
    run_migrations,
    insert_reports,
    record_alert,
)
from airtag_sentry.movement import evaluate_movement
from airtag_sentry.notifiers import build_notifiers, notify_all

logger = logging.getLogger(__name__)

_ALERT_TITLES = {
    "distance_threshold": "AirTagSentry: unerwartete Bewegung",
    "stillstand_movement": "AirTagSentry: Bewegung nach Stillstand",
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


def poll_once(cfg: Config) -> None:
    account = restore_account(cfg)

    with get_conn(cfg.database_url) as conn:
        run_migrations(conn)
        notifiers = build_notifiers(cfg)
        for airtag in cfg.airtags:
            try:
                _poll_airtag(cfg, account, airtag, conn, notifiers)
            except Exception:
                logger.exception("Poll failed for airtag '%s' (%s)", airtag.id, airtag.name)
            finally:
                account.to_json(cfg.apple.store_path)  # tokens can rotate on any call


def _poll_airtag(cfg: Config, account, airtag: AirtagConfig, conn, notifiers) -> None:
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

    if was_empty and not cfg.movement.alert_on_backfill:
        logger.info(
            "[%s] First-ever poll: skipping alerts for the %d backfilled report(s).",
            airtag.id,
            len(newly_inserted),
        )
        return

    for report in newly_inserted:
        prior_reports = fetch_reports_before(conn, airtag.id, report.timestamp)
        alert = evaluate_movement(report, prior_reports, cfg.movement)
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
