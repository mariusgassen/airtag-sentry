"""CLI entrypoints: `python -m airtag_sentry {poll,run,serve}`.

Apple ID login (AirTag tracking and optional owner device tracking) is a
dashboard UI flow (Settings panel), not a CLI command - see
web/app.py's /api/apple/* routes, auth.py, and owner_tracking.py.
"""

from __future__ import annotations

import argparse
import logging

from airtag_sentry.config import load_config


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(prog="airtag_sentry")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("poll", help="Run a single poll immediately and exit.")
    sub.add_parser("run", help="Run the scheduler forever (polling interval set in the dashboard's Settings panel).")
    sub.add_parser("serve", help="Run the FastAPI dashboard.")

    args = parser.parse_args(argv)
    cfg = load_config()

    if args.command == "poll":
        from airtag_sentry.migrate import upgrade_to_head
        from airtag_sentry.tracker import poll_once

        upgrade_to_head()
        poll_once(cfg)
    elif args.command == "run":
        from airtag_sentry.migrate import upgrade_to_head
        from airtag_sentry.scheduler import run_forever

        upgrade_to_head()
        run_forever(cfg)
    elif args.command == "serve":
        import uvicorn

        from airtag_sentry.migrate import upgrade_to_head
        from airtag_sentry.web.app import create_app

        upgrade_to_head()
        uvicorn.run(
            create_app(cfg),
            host=cfg.web.host,
            port=cfg.web.port,
            proxy_headers=True,
            forwarded_allow_ips="*",
        )

    return 0
