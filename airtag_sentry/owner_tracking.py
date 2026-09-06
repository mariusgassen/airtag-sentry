"""Owner device location, via Apple's classic Find My iPhone web service (`pyicloud`) -
a different protocol than `FindMy.py`'s AirTag/search-party reports.

`FindMy.py`'s `fetch_location_history` queries Apple's offline-finding/crowd-sourced
network, which mostly only produces reports for a device that's off, dead, or in
airplane mode - not a live, connected phone. Apple's separate `fmipservice` (the one
behind icloud.com/find) gives a near-real-time location for the owner's own signed-in
devices instead, which is what "did the tag move without me" correlation needs. This
is a second, independent Apple session from the one `auth.py` manages for AirTags -
its own login, its own 2FA, its own persisted session.

Unlike FindMy.py's AppleAccount, pyicloud has no "resume from a session token alone"
mode - the password must be supplied on every PyiCloudService construction, i.e. on
every poll, indefinitely. So (unlike auth.py, where the password is only needed
transiently for the one login request) it's encrypted and stored in Postgres
(owner_apple_credentials, via keystore.py) exactly like AirTag keys already are,
entered through the dashboard's login flow rather than an env var.

Entirely optional: every function here is a no-op (or returns None) when no
credentials are stored, so the rest of the app is unaffected if it's never connected.
"""

from __future__ import annotations

import datetime as dt
import logging

from airtag_sentry import keystore
from airtag_sentry.config import Config
from airtag_sentry.db import (
    OwnerAppleCredentials,
    OwnerLocation,
    delete_owner_apple_credentials,
    get_owner_apple_credentials,
    set_owner_apple_credentials,
)

logger = logging.getLogger(__name__)

_pending_api = None
_pending_apple_id: str | None = None
_pending_password: str | None = None


def _build_api(apple_id: str, password: str, session_dir: str):
    from pyicloud import PyiCloudService

    return PyiCloudService(apple_id, password, cookie_directory=session_dir)


def _persist(cfg: Config, conn, apple_id: str, password: str) -> None:
    encrypted = keystore.encrypt(cfg.key_encryption_key, password)
    set_owner_apple_credentials(conn, apple_id, encrypted)


def start_owner_login(cfg: Config, conn, apple_id: str, password: str) -> dict:
    """Submit the owner's Apple ID credentials. Persists them immediately (encrypted)
    if no 2FA is required, otherwise stashes the in-progress session for
    submit_owner_2fa_code()."""
    global _pending_api, _pending_apple_id, _pending_password

    api = _build_api(apple_id, password, cfg.apple.owner_session_dir)
    if api.requires_2fa:
        _pending_api = api
        _pending_apple_id = apple_id
        _pending_password = password
        return {"requires_2fa": True}

    _persist(cfg, conn, apple_id, password)
    return {"requires_2fa": False}


def submit_owner_2fa_code(cfg: Config, conn, code: str) -> None:
    """Complete the login with the received code and persist the encrypted credentials."""
    global _pending_api, _pending_apple_id, _pending_password
    if _pending_api is None:
        raise RuntimeError("No owner Apple login in progress.")

    if not _pending_api.validate_2fa_code(code):
        raise RuntimeError("Invalid 2FA code.")
    if not _pending_api.is_trusted_session:
        if not _pending_api.trust_session():
            logger.warning(
                "Could not mark the owner-tracking session as trusted - a 2FA code "
                "may be required again sooner than usual."
            )

    _persist(cfg, conn, _pending_apple_id, _pending_password)
    _pending_api = None
    _pending_apple_id = None
    _pending_password = None


def is_connected(conn) -> bool:
    return get_owner_apple_credentials(conn) is not None


def disconnect(conn) -> None:
    delete_owner_apple_credentials(conn)


def fetch_owner_location(cfg: Config, conn) -> OwnerLocation | None:
    """Fetch the owner's current device location, or None if it isn't connected or
    no device returned a location this call."""
    creds: OwnerAppleCredentials | None = get_owner_apple_credentials(conn)
    if creds is None:
        return None

    password = keystore.decrypt(cfg.key_encryption_key, creds.encrypted_password)
    api = _build_api(creds.apple_id, password, cfg.apple.owner_session_dir)
    for device in api.devices:
        location = device.location()
        if location is None:
            continue
        return OwnerLocation(
            id=None,
            recorded_at=dt.datetime.now(dt.timezone.utc),
            lat=location["latitude"],
            lon=location["longitude"],
            horizontal_accuracy=location.get("horizontalAccuracy"),
        )
    return None
