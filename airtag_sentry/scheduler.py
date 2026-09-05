"""APScheduler wrapper: run tracker.poll_once() once immediately, then
re-schedule itself after every run based on the current
`polling_interval_minutes` setting (read from the DB, editable in the
dashboard) - so a change to that setting takes effect starting with the
next poll instead of requiring a restart.
"""

from __future__ import annotations

import datetime as dt
import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from airtag_sentry.config import Config
from airtag_sentry.db import get_conn, get_settings
from airtag_sentry.tracker import poll_once

logger = logging.getLogger(__name__)


def _run_poll(scheduler: BlockingScheduler, cfg: Config) -> None:
    try:
        poll_once(cfg)
    except Exception:
        logger.exception("Poll failed")
    finally:
        _schedule_next(scheduler, cfg)


def _schedule_next(scheduler: BlockingScheduler, cfg: Config) -> None:
    with get_conn(cfg.database_url) as conn:
        interval_minutes = get_settings(conn).polling_interval_minutes
    run_date = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=interval_minutes)
    scheduler.add_job(
        _run_poll,
        "date",
        run_date=run_date,
        args=[scheduler, cfg],
        id="poll_once",
        replace_existing=True,
    )
    logger.info("Next poll scheduled at %s (every %d minute(s)).", run_date.isoformat(), interval_minutes)


def run_forever(cfg: Config) -> None:
    scheduler = BlockingScheduler()
    _run_poll(scheduler, cfg)  # run once on startup so the dashboard has data right away
    scheduler.start()
