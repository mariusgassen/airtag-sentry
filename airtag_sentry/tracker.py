"""Core poll: restore Apple session -> fetch location history -> dedupe insert ->
movement check -> notify.
"""

from __future__ import annotations

import logging

from findmy import FindMyAccessory, KeyPair

from airtag_sentry.auth import restore_account
from airtag_sentry.config import Config
from airtag_sentry.db import (
    Alert as DbAlert,
)
from airtag_sentry.db import (
    Report,
    count_reports,
    fetch_reports_before,
    get_conn,
    init_schema,
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


def _load_key(cfg: Config):
    if cfg.airtag.accessory_json_path:
        return FindMyAccessory.from_json(cfg.airtag.accessory_json_path)
    return KeyPair.from_b64(cfg.airtag.private_key_b64)


def poll_once(cfg: Config) -> None:
    account = restore_account(cfg)
    key = _load_key(cfg)

    location_reports = account.fetch_location_history(key)
    account.to_json(cfg.apple.store_path)  # tokens can rotate on any call

    if not location_reports:
        logger.info("No location reports returned this poll.")
        return

    reports = [
        Report(
            id=None,
            timestamp=lr.timestamp,
            lat=lr.latitude,
            lon=lr.longitude,
            accuracy=lr.horizontal_accuracy,
            confidence=lr.confidence,
        )
        for lr in location_reports
    ]

    with get_conn(cfg.database_url) as conn:
        init_schema(conn)
        was_empty = count_reports(conn) == 0
        newly_inserted = insert_reports(conn, reports)

        if not newly_inserted:
            logger.info("No new reports (all %d already known).", len(reports))
            return

        logger.info("Inserted %d new report(s).", len(newly_inserted))

        if was_empty and not cfg.movement.alert_on_backfill:
            logger.info(
                "First-ever poll: skipping alerts for the %d backfilled report(s).",
                len(newly_inserted),
            )
            return

        notifiers = build_notifiers(cfg)
        for report in newly_inserted:
            prior_reports = fetch_reports_before(conn, report.timestamp)
            alert = evaluate_movement(report, prior_reports, cfg.movement)
            if alert is None:
                continue

            record_alert(
                conn,
                DbAlert(reason=alert.reason, distance_meters=alert.distance_meters, report_id=report.id),
            )
            message = (
                f"{cfg.airtag.name} hat sich um {alert.distance_meters:.0f} m bewegt "
                f"(Report {report.timestamp.isoformat()})."
            )
            notify_all(notifiers, _ALERT_TITLES[alert.reason], message)
