"""APScheduler wrapper: run tracker.poll_once() once immediately, then every
polling.interval_minutes.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from airtag_sentry.config import Config
from airtag_sentry.tracker import poll_once

logger = logging.getLogger(__name__)


def _run_poll(cfg: Config) -> None:
    try:
        poll_once(cfg)
    except Exception:
        logger.exception("Poll failed")


def run_forever(cfg: Config) -> None:
    scheduler = BlockingScheduler()
    scheduler.add_job(
        _run_poll,
        "interval",
        minutes=cfg.polling.interval_minutes,
        args=[cfg],
        id="poll_once",
    )
    logger.info("Starting scheduler: polling every %d minute(s).", cfg.polling.interval_minutes)
    _run_poll(cfg)  # run once on startup so the dashboard has data right away
    scheduler.start()
