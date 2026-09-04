"""FastAPI dashboard: read-only reports/status API, push subscription endpoints,
and the static PWA (Leaflet map + timeline + manifest/service worker).

Routes are plain `def` (not `async def`) so Starlette runs the sync psycopg calls
in its threadpool automatically - no async DB driver needed at this scale.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from airtag_sentry.config import Config, load_config
from airtag_sentry.db import (
    PushSubscription,
    add_push_subscription,
    fetch_reports,
    get_conn,
    init_schema,
    latest_alert,
    remove_push_subscription,
)

STATIC_DIR = Path(__file__).parent / "static"


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionIn(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


class UnsubscribeIn(BaseModel):
    endpoint: str


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or load_config()
    app = FastAPI(title="AirTagSentry")

    @app.get("/api/reports")
    def get_reports(limit: int | None = None):
        with get_conn(cfg.database_url) as conn:
            init_schema(conn)
            reports = fetch_reports(conn, limit=limit)
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat(),
                "lat": r.lat,
                "lon": r.lon,
                "accuracy": r.accuracy,
                "confidence": r.confidence,
            }
            for r in reports
        ]

    @app.get("/api/status")
    def get_status():
        with get_conn(cfg.database_url) as conn:
            init_schema(conn)
            reports = fetch_reports(conn, limit=1)
            alert = latest_alert(conn)
        return {
            "airtag_name": cfg.airtag.name,
            "last_report": (
                {
                    "timestamp": reports[0].timestamp.isoformat(),
                    "lat": reports[0].lat,
                    "lon": reports[0].lon,
                }
                if reports
                else None
            ),
            "last_alert": ({"reason": alert[0], "timestamp": alert[1].isoformat()} if alert else None),
            "poll_interval_minutes": cfg.polling.interval_minutes,
        }

    @app.get("/api/push/vapid-public-key")
    def get_vapid_public_key():
        if not cfg.notifications.webpush:
            raise HTTPException(status_code=404, detail="Web push is not configured")
        return {"publicKey": cfg.notifications.webpush.public_key}

    @app.post("/api/push/subscribe")
    def subscribe(sub: SubscriptionIn):
        with get_conn(cfg.database_url) as conn:
            init_schema(conn)
            add_push_subscription(
                conn,
                PushSubscription(endpoint=sub.endpoint, p256dh=sub.keys.p256dh, auth=sub.keys.auth),
            )
        return {"ok": True}

    @app.post("/api/push/unsubscribe")
    def unsubscribe(body: UnsubscribeIn):
        with get_conn(cfg.database_url) as conn:
            init_schema(conn)
            remove_push_subscription(conn, body.endpoint)
        return {"ok": True}

    # Mounted last so the /api/* routes above always take precedence.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
