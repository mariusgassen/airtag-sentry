"""FastAPI dashboard: read-only reports/status API, push subscription endpoints,
and the static PWA (Leaflet map + timeline + manifest/service worker).

Routes are plain `def` (not `async def`) so Starlette runs the sync psycopg calls
in its threadpool automatically - no async DB driver needed at this scale.
"""

from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from findmy import FindMyAccessory, KeyPair
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from airtag_sentry import keystore
from airtag_sentry.config import Config, load_config
from airtag_sentry.db import (
    PushSubscription,
    StoredKey,
    add_push_subscription,
    create_airtag,
    delete_airtag,
    delete_airtag_key,
    fetch_reports,
    get_conn,
    latest_alert,
    list_airtags,
    list_keyed_airtag_ids,
    remove_push_subscription,
    rename_airtag,
    set_airtag_key,
)

STATIC_DIR = Path(__file__).parent / "static"

_PUBLIC_PATHS = {"/login", "/auth/callback", "/logout"}

_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"


class AuthMiddleware(BaseHTTPMiddleware):
    """Requires a logged-in session for every route except the login/callback/logout ones.

    Must wrap StaticFiles too, since a mounted sub-app bypasses FastAPI's
    Depends() entirely - middleware is the only thing that sees both.
    """

    def __init__(self, app, cfg: Config):
        super().__init__(app)
        self._cfg = cfg

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)
        if request.session.get("user") != self._cfg.auth.allowed_login:
            if request.url.path.startswith("/api/"):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
            return RedirectResponse(url="/login", status_code=302)
        return await call_next(request)


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionIn(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


class UnsubscribeIn(BaseModel):
    endpoint: str


class AirtagKeyIn(BaseModel):
    private_key_b64: str | None = None
    accessory_json: dict[str, Any] | None = None


class AirtagIn(BaseModel):
    name: str


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "airtag"


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or load_config()
    app = FastAPI(title="AirTagSentry")

    def _resolve_airtag_id(conn, airtag_id: str | None) -> str:
        airtags = list_airtags(conn)
        if not airtags:
            raise HTTPException(
                status_code=404, detail="No AirTags configured yet - add one via the dashboard."
            )
        if airtag_id is None:
            return airtags[0].id
        if airtag_id not in {a.id for a in airtags}:
            raise HTTPException(status_code=404, detail=f"Unknown airtag_id '{airtag_id}'")
        return airtag_id

    def _airtag_name(conn, airtag_id: str) -> str:
        return next(a.name for a in list_airtags(conn) if a.id == airtag_id)

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        state = secrets.token_urlsafe(24)
        request.session["oauth_state"] = state
        authorize_url = (
            f"{_GITHUB_AUTHORIZE_URL}?client_id={cfg.auth.github_client_id}"
            f"&scope=read:user&state={state}"
        )
        return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>AirTagSentry - Login</title></head>
<body style="font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
<a href="{authorize_url}" style="background:#238636;color:white;padding:0.75rem 1.25rem;
border-radius:6px;text-decoration:none;font-size:1.1rem;">Mit GitHub anmelden</a>
</body></html>"""

    @app.get("/auth/callback")
    def auth_callback(request: Request, code: str | None = None, state: str | None = None):
        expected_state = request.session.pop("oauth_state", None)
        if not code or not state or state != expected_state:
            raise HTTPException(status_code=403, detail="Invalid OAuth state")

        token_res = requests.post(
            _GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": cfg.auth.github_client_id,
                "client_secret": cfg.auth.github_client_secret,
                "code": code,
            },
            timeout=10,
        )
        token_res.raise_for_status()
        access_token = token_res.json().get("access_token")
        if not access_token:
            raise HTTPException(status_code=403, detail="GitHub OAuth exchange failed")

        user_res = requests.get(
            _GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        user_res.raise_for_status()
        login = user_res.json().get("login")
        if login != cfg.auth.allowed_login:
            raise HTTPException(status_code=403, detail="This GitHub account is not authorized")

        request.session["user"] = login
        return RedirectResponse(url="/", status_code=302)

    @app.get("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse(url="/login", status_code=302)

    @app.get("/api/airtags")
    def get_airtags():
        with get_conn(cfg.database_url) as conn:
            airtags = list_airtags(conn)
            keyed_ids = list_keyed_airtag_ids(conn)
        return [{"id": a.id, "name": a.name, "has_key": a.id in keyed_ids} for a in airtags]

    @app.post("/api/airtags")
    def create_airtag_route(body: AirtagIn):
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name must not be empty.")
        base_slug = _slugify(name)
        with get_conn(cfg.database_url) as conn:
            existing_ids = {a.id for a in list_airtags(conn)}
            slug = base_slug
            suffix = 2
            while slug in existing_ids:
                slug = f"{base_slug}-{suffix}"
                suffix += 1
            record = create_airtag(conn, slug, name)
        return {"id": record.id, "name": record.name, "has_key": False}

    @app.patch("/api/airtags/{airtag_id}")
    def rename_airtag_route(airtag_id: str, body: AirtagIn):
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name must not be empty.")
        with get_conn(cfg.database_url) as conn:
            _resolve_airtag_id(conn, airtag_id)
            record = rename_airtag(conn, airtag_id, name)
        return {"id": record.id, "name": record.name}

    @app.delete("/api/airtags/{airtag_id}")
    def delete_airtag_route(airtag_id: str):
        with get_conn(cfg.database_url) as conn:
            _resolve_airtag_id(conn, airtag_id)
            delete_airtag(conn, airtag_id)
        return {"ok": True}

    @app.post("/api/airtags/{airtag_id}/key")
    def set_airtag_key_route(airtag_id: str, body: AirtagKeyIn):
        if bool(body.private_key_b64) == bool(body.accessory_json):
            raise HTTPException(
                status_code=400,
                detail="Provide exactly one of private_key_b64 or accessory_json.",
            )

        if body.accessory_json is not None:
            key_type = "accessory_json"
            plaintext = json.dumps(body.accessory_json)
            try:
                FindMyAccessory.from_json(body.accessory_json)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid accessory_json: {exc}") from exc
        else:
            key_type = "private_key_b64"
            plaintext = body.private_key_b64
            try:
                KeyPair.from_b64(plaintext)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid private_key_b64: {exc}") from exc

        encrypted = keystore.encrypt(cfg.key_encryption_key, plaintext)
        with get_conn(cfg.database_url) as conn:
            _resolve_airtag_id(conn, airtag_id)
            set_airtag_key(
                conn, StoredKey(airtag_id=airtag_id, key_type=key_type, encrypted_data=encrypted)
            )
        return {"ok": True}

    @app.delete("/api/airtags/{airtag_id}/key")
    def delete_airtag_key_route(airtag_id: str):
        with get_conn(cfg.database_url) as conn:
            _resolve_airtag_id(conn, airtag_id)
            delete_airtag_key(conn, airtag_id)
        return {"ok": True}

    @app.get("/api/reports")
    def get_reports(airtag_id: str | None = None, limit: int | None = None):
        with get_conn(cfg.database_url) as conn:
            resolved = _resolve_airtag_id(conn, airtag_id)
            reports = fetch_reports(conn, resolved, limit=limit)
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
    def get_status(airtag_id: str | None = None):
        with get_conn(cfg.database_url) as conn:
            resolved = _resolve_airtag_id(conn, airtag_id)
            reports = fetch_reports(conn, resolved, limit=1)
            alert = latest_alert(conn, resolved)
            airtag_name = _airtag_name(conn, resolved)
        return {
            "airtag_id": resolved,
            "airtag_name": airtag_name,
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
            add_push_subscription(
                conn,
                PushSubscription(endpoint=sub.endpoint, p256dh=sub.keys.p256dh, auth=sub.keys.auth),
            )
        return {"ok": True}

    @app.post("/api/push/unsubscribe")
    def unsubscribe(body: UnsubscribeIn):
        with get_conn(cfg.database_url) as conn:
            remove_push_subscription(conn, body.endpoint)
        return {"ok": True}

    # Mounted last so the /api/* routes above always take precedence.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    # Middleware order matters: Starlette wraps the most-recently-added middleware
    # outermost, so SessionMiddleware (added second) runs before AuthMiddleware and
    # populates request.session first.
    app.add_middleware(AuthMiddleware, cfg=cfg)
    app.add_middleware(SessionMiddleware, secret_key=cfg.auth.session_secret_key, https_only=True)

    return app
