"""APScheduler wrapper: run tracker.poll_once() once immediately, then
re-schedule itself after every run based on the current
`polling_interval_minutes` setting (read from the DB, editable in the
dashboard) - so a change to that setting takes effect starting with the
next poll instead of requiring a restart.

Runs as a `BackgroundScheduler` (its own worker thread), started from the
FastAPI app's lifespan hook (see web/app.py) rather than as a separate
blocking process - the poller and the dashboard are one deployable process,
talking to each other only through Postgres.
"""

from __future__ import annotations

import datetime as dt
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from airtag_sentry.config import Config
from airtag_sentry.db import get_conn, get_settings
from airtag_sentry.tracker import poll_once

logger = logging.getLogger(__name__)


def _run_poll(scheduler: BackgroundScheduler, cfg: Config) -> None:
    try:
        poll_once(cfg)
    except Exception:
        logger.exception("Poll failed")
    finally:
        _schedule_next(scheduler, cfg)


def _schedule_next(scheduler: BackgroundScheduler, cfg: Config) -> None:
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


def start_scheduler(cfg: Config) -> BackgroundScheduler:
    """Start the poll loop on its own thread and return immediately.

    The first poll is scheduled for "now" rather than run inline, so this
    doesn't block the FastAPI startup that calls it (and thus `/health`)
    on an Apple round-trip - it runs on the scheduler's own thread instead.
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(_run_poll, args=[scheduler, cfg], id="poll_once")
    scheduler.start()
    return scheduler
