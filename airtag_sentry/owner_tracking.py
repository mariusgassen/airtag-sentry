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
`owner_device_locations` in db.py. Device *identity* (name/type) is persisted on
every background poll (fetch_owner_device_locations, called from tracker.py) for
every device the Apple account has, whether tracked or not - there's no separate
live "discovery" call, so a device shows up (toggleable) as soon as the poller has
seen it once, without needing a dashboard visit to trigger a live Apple round trip.
A device only gets its *location* polled and historized once explicitly enabled via
set_device_enabled, so connecting the account never silently starts recording
history for every device on it.

Exactly one enabled device can additionally be marked primary (set_device_primary) -
that's the one used for "moved without you" away-correlation and the map's location
trail. Every other enabled device is still tracked/listed with its own history, it
just doesn't affect correlation - a deliberate choice over "any enabled device counts"
so the user has one definite answer to "where does the app think I am."

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
    rename_owner_device,
    set_owner_apple_credentials,
    set_owner_apple_sync_status,
    set_owner_device_appearance,
    set_owner_device_enabled,
    set_owner_device_primary,
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


def connection_status(conn) -> dict:
    """Connection + primary-device status for the dashboard's Apple-Konten panel.
    `last_sync_error` is the most recent background poll's live Apple call
    failure (a lapsed session, a transient network error, ...), if any -
    cleared on the next successful sync, so the dashboard can surface it
    instead of it only ever showing up in the logs."""
    creds: OwnerAppleCredentials | None = get_owner_apple_credentials(conn)
    if creds is None:
        return {
            "connected": False,
            "primary_device_id": None,
            "primary_device_name": None,
            "last_sync_error": None,
        }
    primary = next((d for d in db_list_owner_devices(conn) if d.is_primary), None)
    return {
        "connected": True,
        "primary_device_id": primary.id if primary else None,
        "primary_device_name": primary.name if primary else None,
        "last_sync_error": creds.last_sync_error,
    }


def disconnect(conn) -> None:
    delete_owner_apple_credentials(conn)


def _connect(cfg: Config, conn):
    """Builds a live pyicloud session from the stored owner credentials, or None
    if owner tracking was never connected via the dashboard."""
    creds: OwnerAppleCredentials | None = get_owner_apple_credentials(conn)
    if creds is None:
        logger.debug("Owner tracking not connected - no credentials stored.")
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

    A third, separate bug (confirmed against the real installed pyicloud source,
    services/findmyiphone.py): the *very first* `.devices` access only performs
    Apple's `initClient` call, which fires before `FindMyiPhoneServiceManager`
    has a `_server_ctx` yet - and the block that sets `isUpdatingAllLocations`/
    `shouldLocate`/`selectedDevice` in `_refresh_client()` is gated behind
    `if self._server_ctx:`, so it's unreachable on that first call. Since this
    app builds a brand-new PyiCloudService every poll and never touches
    `.devices` a second time, it has only ever sent Apple the plain identity
    call, never an explicit "locate now" - so `location`/`location_available`
    reflects whatever Apple happened to have cached, often nothing for a fresh
    session, which is why tracked devices showed no location even after the
    bug above was fixed. `refresh(locate=True)` is the manager's own public
    method for forcing that second, locate-flagged round trip once a
    `_server_ctx` exists (it does, after the first access) - call it explicitly
    rather than relying on the constructor's implicit first call.
    """
    api.devices.refresh(locate=True)
    snapshot = []
    available = 0
    for device in api.devices:
        location = device.location if device.location_available else None
        if location is not None:
            available += 1
        else:
            logger.debug(
                "Owner device '%s' (%s): no location this snapshot (feature "
                "advertised=%s, content has 'location' key=%s).",
                device.name,
                device.id,
                bool(device.data.get("features", {}).get("LOC", False)),
                "location" in device.data,
            )
        snapshot.append(
            {
                "id": device.id,
                "name": device.name,
                "device_type": device.device_type,
                "location": location,
            }
        )
    api.devices.stop_event.set()
    logger.info("Fetched %d owner device(s) from Apple, %d with a location.", len(snapshot), available)
    return snapshot


def set_device_enabled(conn, device_id: str, enabled: bool) -> OwnerDevice | None:
    return set_owner_device_enabled(conn, device_id, enabled)


def set_device_primary(conn, device_id: str | None) -> OwnerDevice | None:
    return set_owner_device_primary(conn, device_id)


def rename_device(conn, device_id: str, display_name: str | None) -> OwnerDevice | None:
    return rename_owner_device(conn, device_id, display_name)


def set_device_appearance(conn, device_id: str, icon: str | None, color: str | None) -> OwnerDevice | None:
    return set_owner_device_appearance(conn, device_id, icon, color)


def fetch_owner_device_locations(cfg: Config, conn) -> list[OwnerLocation]:
    """Refreshes every device's identity (name/type) in `owner_devices` - not just
    enabled ones, so a newly-seen device is toggleable from the dashboard as soon
    as this poll runs, without needing a live Apple call from the dashboard itself
    (see module docstring; tasks/todo.md) - then returns a fresh location for
    every *enabled* device, or [] if not connected or none of the enabled devices
    returned a location this call.

    Also records this attempt's outcome on `owner_apple_credentials`
    (last_sync_at/last_sync_error - see db.set_owner_apple_sync_status), so a
    lapsed session or a transient Apple/network error surfaces on the
    dashboard instead of only ever being logged. A failure here still
    propagates to the caller unchanged (tracker.py's own broad except-and-log
    around the whole poll) - only the persisting is new."""
    if get_owner_apple_credentials(conn) is None:
        return []

    now = dt.datetime.now(dt.timezone.utc)
    try:
        api = _connect(cfg, conn)
        snapshot = _snapshot_devices(api)
    except Exception as exc:
        set_owner_apple_sync_status(conn, now, str(exc))
        raise
    set_owner_apple_sync_status(conn, now, None)

    upsert_owner_devices(
        conn,
        [{"id": d["id"], "name": d["name"], "device_type": d["device_type"]} for d in snapshot],
        seen_at=now,
    )

    enabled_ids = {d.id for d in db_list_owner_devices(conn) if d.enabled}
    if not enabled_ids:
        logger.info("No owner devices enabled for tracking - skipping location fetch.")
        return []

    locations = []
    for device in snapshot:
        if device["id"] not in enabled_ids:
            continue
        if device["location"] is None:
            logger.debug("Enabled owner device '%s' (%s) has no location this poll.", device["name"], device["id"])
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
    logger.info(
        "Fetched a fresh location for %d of %d enabled owner device(s) this poll.",
        len(locations),
        len(enabled_ids),
    )
    return locations
