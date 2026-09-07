"""Owner device tracking, via Apple's classic Find My iPhone web service (`pyicloud`) -
a different protocol than `FindMy.py`'s AirTag/search-party reports.

`FindMy.py`'s `fetch_location_history` queries Apple's offline-finding/crowd-sourced
network, which mostly only produces reports for a device that's off, dead, or in
airplane mode - not a live, connected phone. Apple's separate `fmipservice` (the one
behind icloud.com/find) gives a near-real-time location for the owner's own signed-in
devices instead (Macs, iPhones, iPads, Watches - anything that shows up under
icloud.com/find's "Devices" tab), which is what "did the tag move without me"
correlation needs. This is a second, independent Apple session from the one `auth.py`
manages for AirTags - its own login, its own 2FA, its own persisted session.

Multiple devices can be tracked, each with its own history - see `owner_devices`/
`owner_device_locations` in db.py. Discovering a device (via list_owner_devices) only
records its identity; a device only gets its location polled and historized once
explicitly enabled via set_device_enabled, so connecting the account never silently
starts recording history for every device on it.

AirPods are deliberately out of scope here even though the user may think of them as
"another device": Find My-capable AirPods (Pro/Max) use the same offline-finding
network as AirTags, not this service - they're tracked the same way an AirTag is,
via the dashboard's "Manage AirTags" key-upload flow (`python -m findmy decrypt`
extracts a key per paired accessory, AirPods included).

Unlike FindMy.py's AppleAccount, pyicloud has no "resume from a session token alone"
mode - the password must be supplied on every PyiCloudService construction, i.e. on
every poll, indefinitely. So (unlike auth.py, where the password is only needed
transiently for the one login request) it's encrypted and stored in Postgres
(owner_apple_credentials, via keystore.py) exactly like AirTag keys already are,
entered through the dashboard's login flow rather than an env var.

Entirely optional: every function here is a no-op (or returns an empty result) when
no credentials are stored, so the rest of the app is unaffected if it's never
connected.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from airtag_sentry import keystore
from airtag_sentry.config import Config
from airtag_sentry.db import (
    OwnerAppleCredentials,
    OwnerDevice,
    OwnerLocation,
    delete_owner_apple_credentials,
    get_owner_apple_credentials,
    list_owner_devices as db_list_owner_devices,
    set_owner_apple_credentials,
    set_owner_device_enabled,
    upsert_owner_devices,
)

logger = logging.getLogger(__name__)

_pending_api = None
_pending_apple_id: str | None = None
_pending_password: str | None = None


def _build_api(apple_id: str, password: str, session_dir: str):
    from pyicloud import PyiCloudService
    from pyicloud.exceptions import PyiCloudFailedLoginException

    try:
        return PyiCloudService(apple_id, password, cookie_directory=session_dir)
    except PyiCloudFailedLoginException as exc:
        # Apple's own error here ("-20101: Invalid email/password combination") is
        # the same generic message for a genuinely wrong password AND for the most
        # common real mistake: entering an app-specific password. pyicloud
        # authenticates the same way icloud.com/find does and needs the real
        # account password + a live 2FA code - it doesn't support app-specific
        # passwords at all (they don't produce the tokens this login step needs).
        raise RuntimeError(
            f"{exc} If you used an app-specific password, use your real Apple ID "
            "password instead - pyicloud doesn't support app-specific passwords."
        ) from exc


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


def _connect(cfg: Config, conn):
    """Builds a live pyicloud session from the stored owner credentials, or None
    if owner tracking was never connected via the dashboard."""
    creds: OwnerAppleCredentials | None = get_owner_apple_credentials(conn)
    if creds is None:
        return None
    password = keystore.decrypt(cfg.key_encryption_key, creds.encrypted_password)
    return _build_api(creds.apple_id, password, cfg.apple.owner_session_dir)


def _snapshot_devices(api) -> list[dict[str, Any]]:
    """One pass over api.devices, collected into plain data.

    `AppleDevice.location` is a *property*, not a method - calling it as
    `device.location()` (as this code used to) raises TypeError on every device,
    which tracker.py's broad except-and-log swallowed silently, so owner tracking
    has never actually recorded a location. Also: accessing `.devices` starts a
    background thread that re-polls Apple every 5 minutes and is never otherwise
    stopped - since a fresh PyiCloudService is built on every poll (_build_api),
    that leaks one live thread per poll, forever. Collecting everything needed in
    one pass here, then stopping that thread via stop_event.set() as the very
    last thing (any further .devices access after that restarts it), fixes both.
    """
    snapshot = []
    for device in api.devices:
        location = device.location if device.location_available else None
        snapshot.append(
            {
                "id": device.id,
                "name": device.name,
                "device_type": device.device_type,
                "location": location,
            }
        )
    api.devices.stop_event.set()
    return snapshot


def list_owner_devices(cfg: Config, conn) -> list[OwnerDevice]:
    """Live-refreshes device identity (name/type) from the Apple account and
    returns the full known list, DB `enabled` flags intact. Empty if not
    connected."""
    api = _connect(cfg, conn)
    if api is None:
        return []
    snapshot = _snapshot_devices(api)
    upsert_owner_devices(
        conn,
        [{"id": d["id"], "name": d["name"], "device_type": d["device_type"]} for d in snapshot],
    )
    return db_list_owner_devices(conn)


def set_device_enabled(conn, device_id: str, enabled: bool) -> OwnerDevice | None:
    return set_owner_device_enabled(conn, device_id, enabled)


def fetch_owner_device_locations(cfg: Config, conn) -> list[OwnerLocation]:
    """Current location of every *enabled* device, or [] if not connected or none
    of the enabled devices returned a location this call."""
    api = _connect(cfg, conn)
    if api is None:
        return []

    enabled_ids = {d.id for d in db_list_owner_devices(conn) if d.enabled}
    if not enabled_ids:
        return []

    now = dt.datetime.now(dt.timezone.utc)
    locations = []
    for device in _snapshot_devices(api):
        if device["id"] not in enabled_ids or device["location"] is None:
            continue
        location = device["location"]
        locations.append(
            OwnerLocation(
                id=None,
                device_id=device["id"],
                recorded_at=now,
                lat=location["latitude"],
                lon=location["longitude"],
                horizontal_accuracy=location.get("horizontalAccuracy"),
            )
        )
    return locations
