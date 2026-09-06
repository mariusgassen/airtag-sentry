"""FastAPI dashboard: read-only reports/status API, push subscription endpoints,
and the static PWA (Leaflet map + timeline + manifest/service worker).

Routes are plain `def` (not `async def`) so Starlette runs the sync psycopg calls
in its threadpool automatically - no async DB driver needed at this scale.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import secrets
import time
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from findmy import FindMyAccessory, KeyPair
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from airtag_sentry import keystore
from airtag_sentry.config import Config, load_config
from airtag_sentry.db import (
    AppSettings,
    PushSubscription,
    StoredKey,
    add_push_subscription,
    create_airtag,
    delete_airtag,
    delete_airtag_key,
    fetch_reports,
    get_conn,
    get_settings,
    latest_alert,
    latest_owner_location,
    list_airtags,
    list_keyed_airtag_ids,
    remove_push_subscription,
    rename_airtag,
    set_airtag_key,
    update_settings,
)

STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger(__name__)


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
    "/auth/callback",
    "/logout",
    "/manifest.webmanifest",
    "/registerSW.js",
    "/sw.js",
    "/favicon.ico",
    "/health",
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
    """
    return path in _PUBLIC_PATHS or path.startswith("/icons/")


_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"

# Comfortably longer than a GitHub consent-screen round trip. Pending states
# used to be capped to the last 5 instead of expired by age, which broke down
# whenever more than 5 background hits to /login (e.g. iOS waking the
# installed PWA in the background) landed during a single in-flight login,
# evicting the real state before the user got back from GitHub. Expiring by
# time tolerates any number of those, since they aren't the state a real
# login is waiting on.
_OAUTH_STATE_TTL_SECONDS = 600


def _prune_oauth_states(pending: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cutoff = time.time() - _OAUTH_STATE_TTL_SECONDS
    return [p for p in pending if p["minted_at"] >= cutoff]


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
        if request.session.get("user") != self._cfg.auth.allowed_login:
            if request.url.path.startswith("/api/"):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
            # The PWA service worker precaches the app shell ("/", "/assets/*")
            # in the background, independent of whatever page is open, and
            # redirecting those fetches to /login re-ran the login route as
            # if the user had clicked it, regenerating the OAuth state.
            # Browsers only ever send Sec-Fetch-Mode: navigate for an actual
            # top-level navigation (never from fetch()/a service worker), so
            # reject anything else outright instead of touching /login.
            #
            # A previous version also required Sec-Fetch-User: ?1 here to
            # filter out iOS's background PWA wake-ups (a genuine top-level
            # navigation with no user present, still Sec-Fetch-Mode:
            # navigate). That header is never sent for a plain page reload
            # either, though, so it also silently 401'd real users reloading
            # the dashboard instead of sending them to /login. The OAuth
            # state list below is now time-based rather than count-capped,
            # which is what actually needed fixing to tolerate background
            # wake-ups - see _prune_oauth_states.
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


class SettingsIn(BaseModel):
    polling_interval_minutes: int = Field(gt=0)
    movement_distance_threshold_meters: float = Field(gt=0)
    movement_stillstand_hours: float = Field(gt=0)
    movement_stillstand_movement_meters: float = Field(gt=0)
    movement_alert_on_backfill: bool
    movement_away_distance_meters: float = Field(gt=0)
    owner_location_max_age_minutes: float = Field(gt=0)


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
        # A single overwritten slot breaks whenever something other than the
        # user's own click reaches this route while a login is in flight -
        # e.g. the PWA service worker's Workbox precache fetching "/" while
        # logged out, which AuthMiddleware redirects here. That silently
        # replaced the state the user was about to come back with, so
        # /auth/callback rejected an otherwise valid login. Keeping a list of
        # pending states (expired by age, see _prune_oauth_states) tolerates
        # that without weakening the check: each one is still random,
        # single-use, and tied to this session.
        state = secrets.token_urlsafe(24)
        pending_states = _prune_oauth_states(request.session.get("oauth_states", []))
        pending_states.append({"state": state, "minted_at": time.time()})
        request.session["oauth_states"] = pending_states
        logger.info(
            "oauth login: minted state=%s… (pending now %d) sec-fetch-mode=%s ua=%s",
            state[:8],
            len(pending_states),
            request.headers.get("sec-fetch-mode"),
            request.headers.get("user-agent"),
        )
        authorize_url = (
            f"{_GITHUB_AUTHORIZE_URL}?client_id={cfg.auth.github_client_id}"
            f"&scope=read:user&state={state}"
        )
        html = f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#000000">
<link rel="icon" href="/favicon.ico" sizes="any">
<title>AirTagSentry - Anmelden</title>
<style>
  :root {{
    color-scheme: dark;
    --bg: #000000;
    --card: rgba(28, 28, 30, 0.72);
    --card-border: rgba(255, 255, 255, 0.08);
    --accent: #0a84ff;
    --accent-2: #5e5ce6;
    --text: #ffffff;
    --text-secondary: #8e8e93;
  }}
  @media (prefers-color-scheme: light) {{
    :root:not([data-theme="dark"]) {{
      color-scheme: light;
      --bg: #f2f2f7;
      --card: rgba(255, 255, 255, 0.72);
      --card-border: rgba(0, 0, 0, 0.06);
      --accent: #007aff;
      --accent-2: #5856d6;
      --text: #000000;
      --text-secondary: #8e8e93;
    }}
  }}
  :root[data-theme="light"] {{
    color-scheme: light;
    --bg: #f2f2f7;
    --card: rgba(255, 255, 255, 0.72);
    --card-border: rgba(0, 0, 0, 0.06);
    --accent: #007aff;
    --accent-2: #5856d6;
    --text: #000000;
    --text-secondary: #8e8e93;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ height: 100%; margin: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }}
  .backdrop {{
    position: fixed;
    inset: -20%;
    z-index: 0;
    background:
      radial-gradient(circle at 20% 20%, color-mix(in srgb, var(--accent) 35%, transparent), transparent 55%),
      radial-gradient(circle at 80% 75%, color-mix(in srgb, var(--accent-2) 30%, transparent), transparent 55%);
    filter: blur(60px);
  }}
  .card {{
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
  }}
  .glyph {{
    width: 64px;
    height: 64px;
    margin-bottom: 1rem;
    color: var(--accent);
  }}
  h1 {{
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    margin: 0 0 0.4rem;
  }}
  p.tagline {{
    font-size: 0.9rem;
    color: var(--text-secondary);
    margin: 0 0 1.75rem;
  }}
  .btn {{
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
  }}
  .btn:active {{
    transform: scale(0.97);
    opacity: 0.85;
  }}
  .btn svg {{ width: 20px; height: 20px; flex-shrink: 0; }}
</style>
<script>
  try {{
    var t = localStorage.getItem('airtagsentry.theme')
    if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t
  }} catch (e) {{}}
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
  <a class="btn" href="{authorize_url}">
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38
        0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13
        -.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66
        .07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15
        -.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0
        1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82
        1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01
        1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/>
    </svg>
    Mit GitHub anmelden
  </a>
</div>
</body>
</html>"""
        # This page mints a fresh, single-use OAuth state every time it's
        # rendered. Without an explicit no-store, a browser (or intermediate
        # proxy) is free to cache this dynamic HTML and hand the *same*
        # state back out on a later visit - e.g. via the back button, a
        # reopened tab, or plain heuristic caching - producing a GitHub
        # authorize link whose state no longer matches anything pending.
        return HTMLResponse(
            content=html,
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    @app.get("/auth/callback")
    def auth_callback(request: Request, code: str | None = None, state: str | None = None):
        pending_states = _prune_oauth_states(request.session.get("oauth_states", []))
        if not code or not state or not any(p["state"] == state for p in pending_states):
            logger.warning(
                "oauth callback rejected: code_present=%s state=%s… pending=%s referer=%s ua=%s",
                bool(code),
                (state or "")[:8],
                [p["state"][:8] for p in pending_states],
                request.headers.get("referer"),
                request.headers.get("user-agent"),
            )
            raise HTTPException(status_code=403, detail="Invalid OAuth state")
        pending_states = [p for p in pending_states if p["state"] != state]
        request.session["oauth_states"] = pending_states
        logger.info("oauth callback: accepted state=%s…", state[:8])

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

    @app.get("/api/owner-location")
    def get_owner_location():
        """Latest known location of the owner's own device (see owner_tracking.py),
        used to correlate AirTag movement against - null if the feature isn't
        configured or no location has been recorded yet."""
        with get_conn(cfg.database_url) as conn:
            location = latest_owner_location(conn)
        if location is None:
            return None
        return {
            "recorded_at": location.recorded_at.isoformat(),
            "lat": location.lat,
            "lon": location.lon,
            "horizontal_accuracy": location.horizontal_accuracy,
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
    app.mount("/", _CacheControlledStaticFiles(directory=STATIC_DIR, html=True), name="static")

    # Middleware order matters: Starlette wraps the most-recently-added middleware
    # outermost, so SessionMiddleware (added second) runs before AuthMiddleware and
    # populates request.session first.
    app.add_middleware(AuthMiddleware, cfg=cfg)
    app.add_middleware(SessionMiddleware, secret_key=cfg.auth.session_secret_key, https_only=True)

    return app
