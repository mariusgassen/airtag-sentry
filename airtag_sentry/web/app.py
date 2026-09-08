"""FastAPI dashboard: read-only reports/status API, push subscription endpoints,
and the static PWA (Leaflet map + timeline + manifest/service worker).

Also owns the background poller (see scheduler.py): it's started from this
app's lifespan hook and runs on its own thread for the life of the process,
so the dashboard and the poller are one deployable unit that only talk to
each other through Postgres, never directly.

Routes are plain `def` (not `async def`) so Starlette runs the sync psycopg calls
in its threadpool automatically - no async DB driver needed at this scale.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import requests
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from findmy import FindMyAccessory, KeyPair
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from airtag_sentry import auth, keystore, owner_tracking, telegram_bot
from airtag_sentry.geocode import reverse_geocode
from airtag_sentry.config import Config, load_config
from airtag_sentry.db import (
    AppSettings,
    PushSubscription,
    StoredKey,
    add_push_subscription,
    create_airtag,
    delete_airtag,
    delete_airtag_key,
    delete_telegram_credentials,
    fetch_owner_device_location_history,
    fetch_reports,
    get_conn,
    get_owner_apple_credentials,
    get_settings,
    get_telegram_credentials,
    latest_alert,
    latest_owner_device_locations,
    list_airtags,
    list_keyed_airtag_ids,
    list_owner_devices as db_list_owner_devices,
    remove_push_subscription,
    rename_airtag,
    set_airtag_appearance,
    set_airtag_key,
    set_telegram_bot_commands,
    set_telegram_credentials,
    update_settings,
)
from airtag_sentry.scheduler import start_scheduler

STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger(__name__)

# Must stay in sync with frontend/src/deviceIcons.tsx's icon registry keys -
# the picker only ever offers these, but the server still validates rather
# than trusting the client.
AIRTAG_ICON_CHOICES = {
    "bike",
    "backpack",
    "car",
    "keys",
    "wallet",
    "suitcase",
    "laptop",
    "camera",
    "pet",
    "headphones",
    "book",
    "box",
    "iphone",
    "airpods",
}
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class _CacheControlledStaticFiles(StaticFiles):
    """Serves the Vite build with cache headers that make a new deploy visible right away.

    Vite fingerprints every file under /assets/ with a content hash, so those
    are safe to cache forever - a new deploy simply ships differently-named
    files, never a changed one. Everything else (index.html and the SPA
    fallback that serves it, sw.js, manifest.webmanifest, registerSW.js,
    icons) is unhashed and *does* change in place on a new deploy, so it must
    never be served from a stale cache: index.html is what points the browser
    at the current asset filenames, and vite's `emptyOutDir` deletes the old
    ones on every build, so a cached old index.html means 404s on its
    <script>/<link> tags until a hard refresh.
    """

    def file_response(self, full_path, stat_result, scope, status_code: int = 200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        is_fingerprinted = Path(full_path).parent.name == "assets"
        response.headers["cache-control"] = (
            "public, max-age=31536000, immutable" if is_fingerprinted else "no-cache"
        )
        return response


_PUBLIC_PATHS = {
    "/login",
    "/auth/login",
    "/auth/callback",
    "/logout",
    "/manifest.webmanifest",
    "/registerSW.js",
    "/sw.js",
    "/favicon.ico",
    "/health",
    "/api/telegram/webhook",
}


def _is_public(path: str) -> bool:
    """Whether `path` may be served without a session.

    PWA install/update machinery (the browser's "Add to Home Screen" checks,
    background service-worker update fetches) requests the manifest, icons
    and service worker script outside the page's own authenticated fetch
    context. Gating those behind login redirected them to the login page's
    HTML instead of the actual asset - the browser then either shows a
    broken/missing app icon or, for sw.js, discards the "update" since it's
    not valid JS. Browsers and bookmark tools also request /favicon.ico
    directly, independent of the page's own <link rel="icon">, so it needs
    the same exemption. None of these are sensitive; only the app's data and
    the app shell itself need a session.

    `/health` is the same story for a different caller: Coolify's Docker
    healthcheck probes it directly, with no session cookie to send.

    `/api/telegram/webhook` is the same again for Telegram's own servers -
    it authenticates itself via the X-Telegram-Bot-Api-Secret-Token header
    (see telegram_webhook()) instead of a session.
    """
    return path in _PUBLIC_PATHS or path.startswith("/icons/")


class AuthMiddleware(BaseHTTPMiddleware):
    """Requires a logged-in session for every route except the login/callback/logout ones.

    Must wrap StaticFiles too, since a mounted sub-app bypasses FastAPI's
    Depends() entirely - middleware is the only thing that sees both.
    """

    def __init__(self, app, cfg: Config):
        super().__init__(app)
        self._cfg = cfg

    async def dispatch(self, request: Request, call_next):
        if _is_public(request.url.path):
            return await call_next(request)
        if request.session.get("user") != self._cfg.auth.oidc_allowed_username:
            if request.url.path.startswith("/api/"):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
            # The PWA service worker precaches the app shell ("/", "/assets/*")
            # in the background, independent of whatever page is open, and
            # redirecting those fetches to /login used to re-run the login
            # route as if the user had clicked it, regenerating the OAuth
            # state - back when /login itself minted one on every hit.
            # /login is now a static informational page; only an explicit
            # click on its button hits /auth/login and mints a state, so a
            # background wake-up landing here can no longer touch an
            # in-flight login no matter how it's dispatched. Still: browsers
            # only ever send Sec-Fetch-Mode: navigate for an actual top-level
            # navigation (never from fetch()/a service worker), so reject
            # anything else outright instead of touching /login.
            #
            # A previous version also required Sec-Fetch-User: ?1 here to
            # filter out iOS's background PWA wake-ups (a genuine top-level
            # navigation with no user present, still Sec-Fetch-Mode:
            # navigate). That header is never sent for a plain page reload
            # either, though, so it also silently 401'd real users reloading
            # the dashboard instead of sending them to /login.
            sec_fetch_mode = request.headers.get("sec-fetch-mode")
            if sec_fetch_mode is not None and sec_fetch_mode != "navigate":
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


class AirtagAppearanceIn(BaseModel):
    icon: str | None = None
    color: str | None = None


class SettingsIn(BaseModel):
    polling_interval_minutes: int = Field(gt=0)
    movement_distance_threshold_meters: float = Field(gt=0)
    movement_stillstand_hours: float = Field(gt=0)
    movement_stillstand_movement_meters: float = Field(gt=0)
    movement_alert_on_backfill: bool
    movement_away_distance_meters: float = Field(gt=0)
    owner_location_max_age_minutes: float = Field(gt=0)


class AppleLoginIn(BaseModel):
    email: str
    password: str


class AppleTwoFactorSelectIn(BaseModel):
    method_index: int


class AppleTwoFactorCodeIn(BaseModel):
    code: str


class AppleSessionImportIn(BaseModel):
    session_json: dict


class OwnerLoginIn(BaseModel):
    apple_id: str
    password: str
    # Mirrors the connect dialog's "shared with me" checkbox - see
    # owner_tracking.start_owner_login. Off by default: pyicloud's
    # PyiCloudService otherwise defaults to with_family=True, pulling Family
    # Sharing members' devices into api.devices alongside the account's own.
    include_family: bool = False


class OwnerDeviceEnabledIn(BaseModel):
    # device_id travels in the body, not the URL path: Apple's own device ids
    # (see owner_tracking.py) are opaque base64-ish blobs that can contain a
    # literal "/" - as a path segment that gets mangled by ASGI/proxy layers
    # decoding "%2F" back into a delimiter before routing ever sees it,
    # splitting one {device_id} segment into two and breaking route matching
    # (surfacing as a 405, not a 404, when the split path happens to collide
    # with another route's method set). A JSON body field never has this
    # problem since nothing about it is delimited on "/".
    device_id: str
    enabled: bool


class OwnerDevicePrimaryIn(BaseModel):
    device_id: str


class OwnerDeviceRenameIn(BaseModel):
    # device_id travels in the body, not the URL path - see OwnerDeviceEnabledIn.
    device_id: str
    display_name: str | None = None


class OwnerDeviceAppearanceIn(BaseModel):
    device_id: str
    icon: str | None = None
    color: str | None = None


class TelegramCredentialsIn(BaseModel):
    bot_token: str
    chat_id: str


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "airtag"


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = start_scheduler(cfg)
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="AirTagSentry", lifespan=lifespan)

    # Discovers Authentik's endpoints (authorize/token/userinfo/jwks) from its
    # OIDC well-known document instead of hardcoding them, since Authentik's
    # exact URLs depend on how its application/provider slugs were set up.
    # Exposed on app.state so tests can seed a fake server_metadata dict and
    # stub out the token/userinfo HTTP calls without needing a real IdP.
    oauth = OAuth()
    oauth.register(
        name="authentik",
        server_metadata_url=f"{cfg.auth.oidc_issuer.rstrip('/')}/.well-known/openid-configuration",
        client_id=cfg.auth.oidc_client_id,
        client_secret=cfg.auth.oidc_client_secret,
        client_kwargs={"scope": "openid profile", "code_challenge_method": "S256"},
    )
    app.state.oauth = oauth

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

    @app.get("/health")
    def health():
        """Liveness/readiness probe for Coolify's (or `docker compose`'s) container
        healthcheck. Actually round-trips to Postgres rather than returning a bare
        200, so a DB outage - the one dependency that would otherwise make every
        page silently fail - shows up as "unhealthy" instead of "running"."""
        try:
            with get_conn(cfg.database_url) as conn:
                conn.execute("SELECT 1")
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc
        return {"status": "ok"}

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        html = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#000000">
<link rel="icon" href="/favicon.ico" sizes="any">
<title>AirTagSentry - Anmelden</title>
<style>
  :root {
    color-scheme: dark;
    --bg: #000000;
    --card: rgba(28, 28, 30, 0.72);
    --card-border: rgba(255, 255, 255, 0.08);
    --accent: #0a84ff;
    --accent-2: #5e5ce6;
    --text: #ffffff;
    --text-secondary: #8e8e93;
  }
  @media (prefers-color-scheme: light) {
    :root:not([data-theme="dark"]) {
      color-scheme: light;
      --bg: #f2f2f7;
      --card: rgba(255, 255, 255, 0.72);
      --card-border: rgba(0, 0, 0, 0.06);
      --accent: #007aff;
      --accent-2: #5856d6;
      --text: #000000;
      --text-secondary: #8e8e93;
    }
  }
  :root[data-theme="light"] {
    color-scheme: light;
    --bg: #f2f2f7;
    --card: rgba(255, 255, 255, 0.72);
    --card-border: rgba(0, 0, 0, 0.06);
    --accent: #007aff;
    --accent-2: #5856d6;
    --text: #000000;
    --text-secondary: #8e8e93;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }
  .backdrop {
    position: fixed;
    inset: -20%;
    z-index: 0;
    background:
      radial-gradient(circle at 20% 20%, color-mix(in srgb, var(--accent) 35%, transparent), transparent 55%),
      radial-gradient(circle at 80% 75%, color-mix(in srgb, var(--accent-2) 30%, transparent), transparent 55%);
    filter: blur(60px);
  }
  .card {
    position: relative;
    z-index: 1;
    width: min(340px, calc(100vw - 3rem));
    padding: 2.25rem 1.75rem 1.75rem;
    border-radius: 28px;
    background: var(--card);
    border: 1px solid var(--card-border);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
  }
  .glyph {
    width: 64px;
    height: 64px;
    margin-bottom: 1rem;
    color: var(--accent);
  }
  h1 {
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    margin: 0 0 0.4rem;
  }
  p.tagline {
    font-size: 0.9rem;
    color: var(--text-secondary);
    margin: 0 0 1.75rem;
  }
  .btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    width: 100%;
    background: var(--accent);
    color: white;
    padding: 0.85rem 1.25rem;
    border-radius: 14px;
    text-decoration: none;
    font-size: 1rem;
    font-weight: 600;
    transition: transform 0.15s ease, opacity 0.15s ease;
  }
  .btn:active {
    transform: scale(0.97);
    opacity: 0.85;
  }
  .btn svg { width: 20px; height: 20px; flex-shrink: 0; }
</style>
<script>
  try {
    var t = localStorage.getItem('airtagsentry.theme')
    if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t
  } catch (e) {}
</script>
</head>
<body>
<div class="backdrop"></div>
<div class="card">
  <svg class="glyph" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="12" cy="12" r="10" fill="currentColor" fill-opacity="0.15"/>
    <circle cx="12" cy="12" r="6.5" stroke="currentColor" stroke-width="1.6"/>
    <circle cx="12" cy="12" r="2" fill="currentColor"/>
  </svg>
  <h1>AirTagSentry</h1>
  <p class="tagline">Standort-Historie und Bewegungs-Alarm für deine AirTags.</p>
  <a class="btn" href="/auth/login">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <rect x="3" y="11" width="18" height="10" rx="2"/>
      <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
    Mit Authentik anmelden
  </a>
</div>
</body>
</html>"""
        # No per-render state to protect against caching anymore (that now
        # lives in /auth/login), but this stays unhashed/dynamic like the
        # app shell itself, so treat it the same way.
        return HTMLResponse(
            content=html,
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    @app.get("/auth/login")
    async def auth_login(request: Request):
        redirect_uri = str(request.url_for("auth_callback"))
        return await oauth.authentik.authorize_redirect(request, redirect_uri)

    @app.get("/auth/callback")
    async def auth_callback(request: Request):
        try:
            token = await oauth.authentik.authorize_access_token(request)
        except OAuthError as exc:
            logger.warning(
                "oidc callback rejected: %s referer=%s ua=%s",
                exc,
                request.headers.get("referer"),
                request.headers.get("user-agent"),
            )
            raise HTTPException(status_code=403, detail="Invalid OIDC state") from exc

        userinfo = await oauth.authentik.userinfo(token=token)
        username = userinfo.get("preferred_username")
        if not username or username != cfg.auth.oidc_allowed_username:
            raise HTTPException(status_code=403, detail="This account is not authorized")

        request.session["user"] = username
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
        return [
            {"id": a.id, "name": a.name, "has_key": a.id in keyed_ids, "icon": a.icon, "color": a.color}
            for a in airtags
        ]

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
        return {"id": record.id, "name": record.name, "has_key": False, "icon": record.icon, "color": record.color}

    @app.patch("/api/airtags/{airtag_id}")
    def rename_airtag_route(airtag_id: str, body: AirtagIn):
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name must not be empty.")
        with get_conn(cfg.database_url) as conn:
            _resolve_airtag_id(conn, airtag_id)
            record = rename_airtag(conn, airtag_id, name)
        return {"id": record.id, "name": record.name}

    @app.patch("/api/airtags/{airtag_id}/appearance")
    def set_airtag_appearance_route(airtag_id: str, body: AirtagAppearanceIn):
        if body.icon is not None and body.icon not in AIRTAG_ICON_CHOICES:
            raise HTTPException(status_code=400, detail=f"Unknown icon '{body.icon}'.")
        if body.color is not None and not _COLOR_RE.match(body.color):
            raise HTTPException(status_code=400, detail="color must be a '#rrggbb' hex string.")
        with get_conn(cfg.database_url) as conn:
            _resolve_airtag_id(conn, airtag_id)
            record = set_airtag_appearance(conn, airtag_id, body.icon, body.color)
        return {"id": record.id, "icon": record.icon, "color": record.color}

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

    @app.get("/api/geocode")
    def geocode_route(lat: float, lon: float):
        return {"address": reverse_geocode(lat, lon)}

    @app.get("/api/status")
    def get_status(airtag_id: str | None = None):
        with get_conn(cfg.database_url) as conn:
            resolved = _resolve_airtag_id(conn, airtag_id)
            reports = fetch_reports(conn, resolved, limit=1)
            alert = latest_alert(conn, resolved)
            airtag_name = _airtag_name(conn, resolved)
            poll_interval_minutes = get_settings(conn).polling_interval_minutes
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
            "poll_interval_minutes": poll_interval_minutes,
        }

    @app.get("/api/settings")
    def get_settings_route():
        with get_conn(cfg.database_url) as conn:
            settings = get_settings(conn)
        return dataclasses.asdict(settings)

    @app.put("/api/settings")
    def update_settings_route(body: SettingsIn):
        with get_conn(cfg.database_url) as conn:
            settings = update_settings(conn, AppSettings(**body.model_dump()))
        return dataclasses.asdict(settings)

    @app.get("/api/owner-devices")
    def get_owner_devices():
        """Persisted list of the owner's Apple devices (Macs, iPhones, iPads,
        Watches - see owner_tracking.py), each with whether it's enabled for
        tracking. Identity is refreshed by the background poller on every poll
        cycle (owner_tracking.fetch_owner_device_locations), not by this route -
        it used to do a *live* Apple call on every request instead, so a lapsed
        pyicloud session, a transient network error, or Apple-side rate limiting
        would blank the dashboard's whole device list (see tasks/todo.md).
        Reading straight from Postgres means this route can't fail because of
        Apple at all, and we only ever needed the persisted history anyway.
        Empty if owner tracking isn't configured or the poller hasn't run yet.

        Each device also gets `on_account`: whether it was present in the most
        recent *successful* live sync (device.last_seen_at == credentials.
        last_sync_at, the exact same poll's timestamp) - false means Apple
        stopped listing it (e.g. removed from iCloud/Find My), distinct from
        it simply being disabled or never having reported a location.
        Unknown (reported as true) before any sync has ever run."""
        with get_conn(cfg.database_url) as conn:
            devices = db_list_owner_devices(conn)
            creds = get_owner_apple_credentials(conn)
        last_sync_at = creds.last_sync_at if creds else None
        return [
            {
                **dataclasses.asdict(d),
                "on_account": last_sync_at is None or d.last_seen_at == last_sync_at,
            }
            for d in devices
        ]

    @app.put("/api/owner-devices")
    def set_owner_device_enabled_route(body: OwnerDeviceEnabledIn):
        # device_id is a body field, not a path segment - see OwnerDeviceEnabledIn.
        with get_conn(cfg.database_url) as conn:
            device = owner_tracking.set_device_enabled(conn, body.device_id, body.enabled)
        if device is None:
            raise HTTPException(status_code=404, detail=f"Unknown device_id '{body.device_id}'")
        return dataclasses.asdict(device)

    @app.put("/api/owner-devices/primary")
    def set_owner_device_primary_route(body: OwnerDevicePrimaryIn):
        """Marks `body.device_id` as the one device used for "moved without you"
        away-correlation and the map's location trail - also enables it, since a
        disabled device never gets a fresh location. Clears any previous primary."""
        with get_conn(cfg.database_url) as conn:
            device = owner_tracking.set_device_primary(conn, body.device_id)
        if device is None:
            raise HTTPException(status_code=404, detail=f"Unknown device_id '{body.device_id}'")
        return dataclasses.asdict(device)

    @app.delete("/api/owner-devices/primary")
    def clear_owner_device_primary_route():
        with get_conn(cfg.database_url) as conn:
            owner_tracking.set_device_primary(conn, None)
        return {"ok": True}

    @app.patch("/api/owner-devices/rename")
    def rename_owner_device_route(body: OwnerDeviceRenameIn):
        """Sets the device's display name shown throughout the dashboard/bot -
        `None`/empty resets to the Apple-synced technical name (`device.name`).
        Mirrors PATCH /api/airtags/{id}."""
        display_name = body.display_name.strip() if body.display_name else None
        with get_conn(cfg.database_url) as conn:
            device = owner_tracking.rename_device(conn, body.device_id, display_name)
        if device is None:
            raise HTTPException(status_code=404, detail=f"Unknown device_id '{body.device_id}'")
        return dataclasses.asdict(device)

    @app.patch("/api/owner-devices/appearance")
    def set_owner_device_appearance_route(body: OwnerDeviceAppearanceIn):
        """Mirrors PATCH /api/airtags/{id}/appearance."""
        if body.icon is not None and body.icon not in AIRTAG_ICON_CHOICES:
            raise HTTPException(status_code=400, detail=f"Unknown icon '{body.icon}'.")
        if body.color is not None and not _COLOR_RE.match(body.color):
            raise HTTPException(status_code=400, detail="color must be a '#rrggbb' hex string.")
        with get_conn(cfg.database_url) as conn:
            device = owner_tracking.set_device_appearance(conn, body.device_id, body.icon, body.color)
        if device is None:
            raise HTTPException(status_code=404, detail=f"Unknown device_id '{body.device_id}'")
        return dataclasses.asdict(device)

    @app.get("/api/owner-device-locations")
    def get_owner_device_locations():
        """Latest known location of every *enabled* owner device, used to correlate
        AirTag movement against and to show on the map - one entry per enabled
        device with a recorded fix, empty if none."""
        with get_conn(cfg.database_url) as conn:
            locations = latest_owner_device_locations(conn)
            devices = {d.id: d for d in db_list_owner_devices(conn)}
        results = []
        for loc in locations:
            device = devices.get(loc.device_id)
            results.append(
                {
                    "device_id": loc.device_id,
                    "name": (device.display_name or device.name) if device else loc.device_id,
                    "icon": device.icon if device else None,
                    "color": device.color if device else None,
                    "recorded_at": loc.recorded_at.isoformat(),
                    "lat": loc.lat,
                    "lon": loc.lon,
                    "horizontal_accuracy": loc.horizontal_accuracy,
                }
            )
        return results

    @app.get("/api/owner-devices/history")
    def get_owner_device_history(device_id: str, limit: int = 200):
        """History of one owner device's location, newest first. device_id is a
        query param, not a path segment - see OwnerDeviceEnabledIn for why."""
        with get_conn(cfg.database_url) as conn:
            locations = fetch_owner_device_location_history(conn, device_id, limit=limit)
        return [
            {
                "recorded_at": loc.recorded_at.isoformat(),
                "lat": loc.lat,
                "lon": loc.lon,
                "horizontal_accuracy": loc.horizontal_accuracy,
            }
            for loc in locations
        ]

    @app.get("/api/apple/status")
    def apple_status():
        """Whether the AirTag-tracking Apple session (see auth.py) is connected."""
        return {"connected": auth.is_connected(cfg)}

    @app.post("/api/apple/login")
    def apple_login(body: AppleLoginIn):
        try:
            result = auth.start_login(cfg, body.email, body.password)
        except Exception as exc:
            logger.exception("Apple login failed.")
            raise HTTPException(status_code=400, detail=f"Login failed: {exc}") from exc
        return dataclasses.asdict(result)

    @app.post("/api/apple/2fa/select")
    def apple_2fa_select(body: AppleTwoFactorSelectIn):
        try:
            auth.request_2fa_code(body.method_index)
        except Exception as exc:
            logger.exception("Apple 2FA method selection failed.")
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/apple/2fa/submit")
    def apple_2fa_submit(body: AppleTwoFactorCodeIn):
        try:
            auth.submit_2fa_code(cfg, body.code)
        except Exception as exc:
            logger.exception("Apple 2FA code submission failed.")
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/apple/session")
    def apple_import_session(body: AppleSessionImportIn):
        """Fallback for when the live login keeps failing with Apple's GSA 503
        - import a session generated elsewhere instead (see auth.import_session)."""
        try:
            auth.import_session(cfg, body.session_json)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    @app.delete("/api/apple")
    def apple_disconnect():
        auth.disconnect(cfg)
        return {"ok": True}

    @app.get("/api/apple/owner/status")
    def owner_apple_status():
        """Whether the owner-device-tracking Apple session (see owner_tracking.py) is
        connected, and which of the account's devices (if any) is currently marked
        primary - see owner_tracking.connection_status()."""
        with get_conn(cfg.database_url) as conn:
            return owner_tracking.connection_status(conn)

    @app.post("/api/apple/owner/login")
    def owner_apple_login(body: OwnerLoginIn):
        with get_conn(cfg.database_url) as conn:
            try:
                result = owner_tracking.start_owner_login(
                    cfg, conn, body.apple_id, body.password, body.include_family
                )
            except Exception as exc:
                logger.exception("Owner Apple login failed.")
                raise HTTPException(status_code=400, detail=f"Login failed: {exc}") from exc
        return result

    @app.post("/api/apple/owner/2fa/submit")
    def owner_apple_2fa_submit(body: AppleTwoFactorCodeIn):
        with get_conn(cfg.database_url) as conn:
            try:
                owner_tracking.submit_owner_2fa_code(cfg, conn, body.code)
            except Exception as exc:
                logger.exception("Owner Apple 2FA code submission failed.")
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    @app.delete("/api/apple/owner")
    def owner_apple_disconnect():
        with get_conn(cfg.database_url) as conn:
            owner_tracking.disconnect(conn)
        return {"ok": True}

    @app.get("/api/notifications/telegram")
    def telegram_status():
        """Whether Telegram notifications are configured (see notifiers/telegram.py) -
        entered via the dashboard's Settings panel, not TELEGRAM_BOT_TOKEN/
        TELEGRAM_CHAT_ID env vars. The bot token itself is never returned."""
        with get_conn(cfg.database_url) as conn:
            creds = get_telegram_credentials(conn)
        return {
            "connected": creds is not None,
            "chat_id": creds.chat_id if creds else None,
            "bot_commands_enabled": creds.bot_commands_enabled if creds else False,
        }

    @app.post("/api/notifications/telegram")
    def telegram_connect(body: TelegramCredentialsIn):
        if not body.bot_token.strip() or not body.chat_id.strip():
            raise HTTPException(status_code=400, detail="Bot-Token und Chat-ID dürfen nicht leer sein.")
        encrypted = keystore.encrypt(cfg.key_encryption_key, body.bot_token.strip())
        with get_conn(cfg.database_url) as conn:
            # Reconnecting invalidates any webhook already registered against
            # the previous token - set_telegram_credentials resets
            # bot_commands_enabled/webhook_secret, so re-enable from the panel
            # if still wanted.
            set_telegram_credentials(conn, encrypted, body.chat_id.strip())
        return {"connected": True, "chat_id": body.chat_id.strip(), "bot_commands_enabled": False}

    @app.delete("/api/notifications/telegram")
    def telegram_disconnect():
        with get_conn(cfg.database_url) as conn:
            creds = get_telegram_credentials(conn)
            if creds is not None and creds.bot_commands_enabled:
                bot_token = keystore.decrypt(cfg.key_encryption_key, creds.bot_token_encrypted)
                try:
                    telegram_bot.delete_webhook(bot_token)
                except requests.RequestException:
                    logger.exception("Failed to delete Telegram webhook while disconnecting; continuing.")
            delete_telegram_credentials(conn)
        return {"ok": True}

    @app.post("/api/notifications/telegram/commands")
    def telegram_commands_enable(request: Request):
        """Registers a webhook with Telegram so the bot can respond to /list,
        /where, /help (see telegram_bot.py). The webhook URL is derived from
        this very request's host, not a config value - cli.py's `serve` runs
        uvicorn with proxy_headers=True, so request.base_url already reflects
        the public host/scheme behind Coolify's edge TLS termination."""
        with get_conn(cfg.database_url) as conn:
            creds = get_telegram_credentials(conn)
            if creds is None:
                raise HTTPException(status_code=400, detail="Telegram ist noch nicht verbunden.")
            bot_token = keystore.decrypt(cfg.key_encryption_key, creds.bot_token_encrypted)
            webhook_secret = secrets.token_urlsafe(32)
            webhook_url = f"{str(request.base_url).rstrip('/')}/api/telegram/webhook"
            try:
                telegram_bot.set_webhook(bot_token, webhook_url, webhook_secret)
            except requests.RequestException as exc:
                logger.exception("Failed to register Telegram webhook.")
                raise HTTPException(
                    status_code=502, detail="Telegram-Webhook konnte nicht registriert werden."
                ) from exc
            set_telegram_bot_commands(conn, True, webhook_secret)
        return {"bot_commands_enabled": True}

    @app.delete("/api/notifications/telegram/commands")
    def telegram_commands_disable():
        with get_conn(cfg.database_url) as conn:
            creds = get_telegram_credentials(conn)
            if creds is not None and creds.bot_commands_enabled:
                bot_token = keystore.decrypt(cfg.key_encryption_key, creds.bot_token_encrypted)
                try:
                    telegram_bot.delete_webhook(bot_token)
                except requests.RequestException:
                    logger.exception("Failed to delete Telegram webhook; disabling locally anyway.")
            set_telegram_bot_commands(conn, False, None)
        return {"bot_commands_enabled": False}

    @app.post("/api/telegram/webhook")
    async def telegram_webhook(request: Request):
        """Public (see _PUBLIC_PATHS) - Telegram can't send our session
        cookie, so this authenticates the request itself via the secret
        Telegram echoes back in X-Telegram-Bot-Api-Secret-Token (set once in
        telegram_commands_enable via setWebhook's secret_token). Always
        returns 200 once the request is confirmed to be genuinely from
        Telegram, since a non-2xx makes Telegram retry the same update."""
        secret_header = request.headers.get("x-telegram-bot-api-secret-token")
        with get_conn(cfg.database_url) as conn:
            creds = get_telegram_credentials(conn)
            if (
                creds is None
                or not creds.bot_commands_enabled
                or not creds.webhook_secret
                or secret_header is None
                or not secrets.compare_digest(secret_header, creds.webhook_secret)
            ):
                raise HTTPException(status_code=401, detail="Unauthorized")
            bot_token = keystore.decrypt(cfg.key_encryption_key, creds.bot_token_encrypted)
            try:
                update = await request.json()
                telegram_bot.handle_update(conn, bot_token, creds.chat_id, update)
            except Exception:
                logger.exception("Telegram webhook handler failed.")
        return {"ok": True}

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
    app.mount("/", _CacheControlledStaticFiles(directory=STATIC_DIR, html=True), name="static")

    # Middleware order matters: Starlette wraps the most-recently-added middleware
    # outermost, so SessionMiddleware (added second) runs before AuthMiddleware and
    # populates request.session first.
    app.add_middleware(AuthMiddleware, cfg=cfg)
    app.add_middleware(SessionMiddleware, secret_key=cfg.auth.session_secret_key, https_only=True)

    return app
