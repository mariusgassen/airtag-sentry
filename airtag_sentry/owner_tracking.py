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
import inspect
import logging
from pathlib import Path
import threading
import time
from typing import Any

from airtag_sentry import keystore
from airtag_sentry.config import Config
from airtag_sentry.db import (
    OwnerAppleCredentials,
    OwnerDevice,
    OwnerLocation,
    delete_owner_apple_credentials,
    delete_owner_device,
    get_owner_apple_credentials,
    list_owner_devices as db_list_owner_devices,
    rename_owner_device,
    set_owner_apple_credentials,
    set_owner_apple_sync_status,
    set_owner_device_appearance,
    set_owner_device_away_alert_enabled,
    set_owner_device_enabled,
    set_owner_device_primary,
    set_owner_devices_order,
    set_owner_include_family_devices,
    upsert_owner_devices,
)

logger = logging.getLogger(__name__)

_PENDING_LOGIN_TTL_SECONDS = 600.0

_pending_lock = threading.Lock()
_session_lock = threading.Lock()
_pending_api = None
_pending_apple_id: str | None = None
_pending_password: str | None = None
_pending_include_family: bool = False
_pending_started_at: float | None = None
_login_in_progress_count = 0


class OwnerReauthRequiredError(RuntimeError):
    """Raised when a background owner-device poll encounters a 2FA requirement."""


def _cleanup_api_bridge(api) -> None:
    """Close any active HSA2 websocket and stop the FMIP monitor thread without
    triggering lazy .devices network calls."""
    if api is None:
        return
    clear_bridge = getattr(api, "_clear_trusted_device_bridge_state", None)
    if callable(clear_bridge):
        try:
            clear_bridge()
        except Exception:
            logger.debug("Ignoring error while closing pyicloud HSA2 bridge.", exc_info=True)
    devices_mgr = getattr(api, "_devices", None)
    stop_event = getattr(devices_mgr, "stop_event", None)
    if stop_event is not None:
        try:
            stop_event.set()
        except Exception:
            logger.debug("Ignoring error while stopping pyicloud devices thread.", exc_info=True)


def _clear_session_dir(session_dir: str | None) -> None:
    """Remove stale pyicloud `.session`/`.cookiejar` files before a fresh login
    or on disconnect so expired tokens/cookies cannot poison a new 2FA flow."""
    if not session_dir:
        return
    path = Path(session_dir)
    if not path.is_dir():
        return
    for pattern in ("*.session", "*.cookiejar"):
        for file_path in path.glob(pattern):
            file_path.unlink(missing_ok=True)


def _pop_pending_state():
    global _pending_api, _pending_apple_id, _pending_password, _pending_include_family, _pending_started_at
    api = _pending_api
    _pending_api = None
    _pending_apple_id = None
    _pending_password = None
    _pending_include_family = False
    _pending_started_at = None
    return api


def is_login_in_progress() -> bool:
    """Whether an interactive owner Apple login/2FA flow is currently active."""
    expired_api = None
    with _pending_lock:
        if _login_in_progress_count > 0:
            return True
        if _pending_api is None:
            return False
        if (
            _pending_started_at is not None
            and (time.monotonic() - _pending_started_at) > _PENDING_LOGIN_TTL_SECONDS
        ):
            expired_api = _pop_pending_state()
        else:
            return True
    if expired_api is not None:
        _cleanup_api_bridge(expired_api)
    return False


def _build_api(
    apple_id: str,
    password: str,
    session_dir: str,
    include_family: bool = False,
    *,
    interactive: bool = True,
):
    from pyicloud import PyiCloudService
    from pyicloud.exceptions import (
        PyiCloud2FARequiredException,
        PyiCloud2SARequiredException,
        PyiCloudAuthRequiredException,
        PyiCloudFailedLoginException,
    )

    service_cls = PyiCloudService
    kwargs: dict[str, Any] = {
        "cookie_directory": session_dir,
        "with_family": include_family,
        "accept_terms": True,
    }
    if not interactive:
        class _NonInteractivePyiCloudService(PyiCloudService):
            # Never trigger Apple's HSA2 bridge / SMS 2FA delivery during
            # unattended background polls; fail immediately instead so the user
            # is not bombarded with 2FA prompts on their phone.
            def _get_mfa_auth_options(self):
                raise OwnerReauthRequiredError(
                    "Apple-Sitzung abgelaufen – erneute Anmeldung mit 2FA erforderlich."
                )

            def request_2fa_code(self):
                raise OwnerReauthRequiredError(
                    "Apple-Sitzung abgelaufen – erneute Anmeldung mit 2FA erforderlich."
                )

            def _login_with_paused_token(self) -> bool:
                return False

        service_cls = _NonInteractivePyiCloudService
        if "refresh_interval" in inspect.signature(PyiCloudService.__init__).parameters:
            kwargs["refresh_interval"] = None

    try:
        api = service_cls(apple_id, password, **kwargs)
    except OwnerReauthRequiredError:
        raise
    except (
        PyiCloud2FARequiredException,
        PyiCloud2SARequiredException,
        PyiCloudAuthRequiredException,
    ) as exc:
        if not interactive:
            raise OwnerReauthRequiredError(
                "Apple-Sitzung abgelaufen – erneute Anmeldung mit 2FA erforderlich."
            ) from exc
        raise
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

    if not interactive and (getattr(api, "requires_2fa", False) or getattr(api, "requires_2sa", False)):
        _cleanup_api_bridge(api)
        raise OwnerReauthRequiredError(
            "Apple-Sitzung abgelaufen – erneute Anmeldung mit 2FA erforderlich."
        )
    return api


def _persist(cfg: Config, conn, apple_id: str, password: str, include_family: bool) -> None:
    encrypted = keystore.encrypt(cfg.key_encryption_key, password)
    set_owner_apple_credentials(conn, apple_id, encrypted, include_family)


def start_owner_login(cfg: Config, conn, apple_id: str, password: str, include_family: bool = False) -> dict:
    """Submit the owner's Apple ID credentials. Persists them immediately (encrypted)
    if no 2FA is required, otherwise stashes the in-progress session for
    submit_owner_2fa_code().

    include_family mirrors the connect dialog's "shared with me" checkbox - it's
    pyicloud's PyiCloudService with_family flag, which otherwise defaults to True
    and pulls Family Sharing members' devices into api.devices alongside the
    account's own."""
    global _pending_api, _pending_apple_id, _pending_password, _pending_include_family, _pending_started_at
    global _login_in_progress_count

    with _pending_lock:
        _login_in_progress_count += 1
        old_api = _pop_pending_state()
    if old_api is not None:
        _cleanup_api_bridge(old_api)

    try:
        with _session_lock:
            _clear_session_dir(cfg.apple.owner_session_dir)
            api = _build_api(
                apple_id, password, cfg.apple.owner_session_dir, include_family, interactive=True
            )
            if getattr(api, "requires_2fa", False):
                if getattr(api, "two_factor_delivery_method", None) == "security_key":
                    _cleanup_api_bridge(api)
                    raise RuntimeError(
                        "Apple erfordert einen Hardware-Sicherheitsschlüssel für 2FA, "
                        "der hier nicht bestätigt werden kann."
                    )
                if not getattr(api, "_two_factor_code_requested", False):
                    try:
                        delivered = api.request_2fa_code()
                    except Exception as exc:
                        _cleanup_api_bridge(api)
                        raise RuntimeError(
                            f"2FA-Code konnte nicht von Apple angefordert werden: {exc}"
                        ) from exc
                    if not delivered:
                        _cleanup_api_bridge(api)
                        raise RuntimeError(
                            "2FA-Code konnte nicht angefordert werden. Bitte kurz warten und erneut versuchen."
                        )
                with _pending_lock:
                    _pending_api = api
                    _pending_apple_id = apple_id
                    _pending_password = password
                    _pending_include_family = include_family
                    _pending_started_at = time.monotonic()
                return {"requires_2fa": True}

            if getattr(api, "requires_2sa", False):
                _cleanup_api_bridge(api)
                raise RuntimeError("Ältere Apple-Bestätigung (2SA) wird nicht unterstützt.")

            _persist(cfg, conn, apple_id, password, include_family)
            _cleanup_api_bridge(api)
            return {"requires_2fa": False}
    finally:
        with _pending_lock:
            _login_in_progress_count -= 1


def cancel_owner_login() -> None:
    """Cancel any in-progress 2FA login and close its Apple bridge session."""
    with _pending_lock:
        old_api = _pop_pending_state()
    if old_api is not None:
        _cleanup_api_bridge(old_api)


def submit_owner_2fa_code(cfg: Config, conn, code: str) -> None:
    """Complete the login with the received code and persist the encrypted credentials."""
    with _pending_lock:
        api = _pending_api
        apple_id = _pending_apple_id
        password = _pending_password
        include_family = _pending_include_family
        started_at = _pending_started_at

    if api is None:
        raise RuntimeError("No owner Apple login in progress.")

    if started_at is not None and (time.monotonic() - started_at) > _PENDING_LOGIN_TTL_SECONDS:
        cancel_owner_login()
        raise RuntimeError("Owner Apple login session expired - please sign in again.")

    with _session_lock:
        was_sms = getattr(api, "two_factor_delivery_method", None) == "sms"
        try:
            valid = api.validate_2fa_code(code)
        except Exception as exc:
            if not was_sms:
                with _pending_lock:
                    if _pending_api is api:
                        _pop_pending_state()
                _cleanup_api_bridge(api)
            raise RuntimeError(f"2FA validation failed: {exc}") from exc

        if not valid:
            if not was_sms:
                with _pending_lock:
                    if _pending_api is api:
                        _pop_pending_state()
                _cleanup_api_bridge(api)
                raise RuntimeError("Invalid 2FA code or expired session - please sign in again.")
            raise RuntimeError("Invalid 2FA code.")

        if not api.is_trusted_session:
            if not api.trust_session():
                logger.warning(
                    "Could not mark the owner-tracking session as trusted - a 2FA code "
                    "may be required again sooner than usual."
                )

        _persist(cfg, conn, apple_id, password, include_family)
        with _pending_lock:
            if _pending_api is api:
                _pop_pending_state()
        _cleanup_api_bridge(api)


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
            "apple_id": None,
            "primary_device_id": None,
            "primary_device_name": None,
            "last_sync_error": None,
            "reauth_required": False,
            "include_family_devices": False,
        }
    primary = next((d for d in db_list_owner_devices(conn) if d.is_primary), None)
    return {
        "connected": True,
        "apple_id": creds.apple_id,
        "primary_device_id": primary.id if primary else None,
        "primary_device_name": primary.name if primary else None,
        "last_sync_error": creds.last_sync_error,
        "reauth_required": getattr(creds, "reauth_required", False),
        "include_family_devices": creds.include_family_devices,
    }


def set_include_family(cfg: Config, conn, include_family: bool) -> bool:
    """Flips the "shared with me" Family Sharing filter on an already-connected
    account. Unlike the connect dialog's checkbox, this needs no re-login: the
    flag is read fresh from Postgres on every _connect() call (a new
    PyiCloudService is built per poll/request anyway).

    Triggers an immediate fetch_owner_device_locations() re-sync rather than
    leaving the visible effect (a family member's devices disappearing from
    the dashboard/Settings, or newly-included ones appearing) to whenever the
    next scheduled poll happens to run - which could be minutes away, making
    the checkbox look like it did nothing. A failure here is only logged: the
    flag change itself already succeeded, and the regular poll will pick up
    the rest. Returns False if owner tracking isn't connected."""
    changed = set_owner_include_family_devices(conn, include_family)
    if changed:
        try:
            fetch_owner_device_locations(cfg, conn)
        except Exception:
            logger.exception(
                "Family Sharing filter changed, but the immediate re-sync to apply it failed - "
                "it'll still take effect on the next scheduled poll."
            )
    return changed


def disconnect(cfg: Config, conn) -> None:
    cancel_owner_login()
    with _session_lock:
        _clear_session_dir(cfg.apple.owner_session_dir)
    delete_owner_apple_credentials(conn)


def _connect(cfg: Config, conn):
    """Builds a live non-interactive pyicloud session from the stored owner
    credentials, or None if owner tracking was never connected via the dashboard."""
    creds: OwnerAppleCredentials | None = get_owner_apple_credentials(conn)
    if creds is None:
        logger.debug("Owner tracking not connected - no credentials stored.")
        return None
    password = keystore.decrypt(cfg.key_encryption_key, creds.encrypted_password)
    return _build_api(
        creds.apple_id,
        password,
        cfg.apple.owner_session_dir,
        creds.include_family_devices,
        interactive=False,
    )


# Apple answers a locate request asynchronously: the response right after
# refresh(locate=True) usually still carries the last cached fix flagged
# `isOld` (or `locationFinished` False) while the device is being pinged.
# icloud.com/find re-polls until the fresh fix lands, so do the same briefly.
_LOCATE_ATTEMPTS = 4
_LOCATE_RETRY_DELAY_SECONDS = 5


def _location_is_stale(location: dict[str, Any] | None) -> bool:
    return location is not None and (location.get("isOld") is True or location.get("locationFinished") is False)


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
    try:
        for attempt in range(_LOCATE_ATTEMPTS):
            api.devices.refresh(locate=True)
            if not any(_location_is_stale(d.location if d.location_available else None) for d in api.devices):
                break
            logger.info("Owner locate attempt %d/%d: still waiting on a fresh fix from Apple.", attempt + 1, _LOCATE_ATTEMPTS)
            if attempt < _LOCATE_ATTEMPTS - 1:
                time.sleep(_LOCATE_RETRY_DELAY_SECONDS)
        snapshot = []
        available = 0
        for device in api.devices:
            location = device.location if device.location_available else None
            if location is not None:
                logger.debug(
                    "Owner device '%s' (%s): location from Apple timeStamp=%s isOld=%s locationFinished=%s "
                    "positionType=%s horizontalAccuracy=%s.",
                    device.name,
                    device.id,
                    location.get("timeStamp"),
                    location.get("isOld"),
                    location.get("locationFinished"),
                    location.get("positionType"),
                    location.get("horizontalAccuracy"),
                )
            if _location_is_stale(location):
                # Still Apple's cached fix after retrying - recording it would stamp
                # an old position (e.g. where AirPods were hours ago) as "now".
                logger.info("Owner device '%s' (%s): only a stale cached location from Apple, skipping.", device.name, device.id)
                location = None
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
            # batteryLevel is a 0.0-1.0 fraction, batteryStatus a raw Apple string
            # ("Charging"/"NotCharging"/"Unplugged") - both absent from .data on
            # devices that don't report battery at all (e.g. Macs). But when Apple
            # *does* advertise battery support, a round yet to include a real
            # reading (e.g. this snapshot's own locate-focused refresh, or a
            # session that hasn't fully checked in) comes back as batteryStatus
            # "Unknown" paired with a *meaningless* batteryLevel of 0 rather than
            # an absent key - confirmed against Home Assistant's icloud
            # integration, which explicitly discards readings in that state for
            # the same reason. Trusting battery_level at face value here made the
            # dashboard show a permanent, wrong "0 %" instead of hiding it like a
            # genuinely absent reading.
            battery_status = device.data.get("batteryStatus")
            battery_level = None if battery_status == "Unknown" else device.data.get("batteryLevel")
            snapshot.append(
                {
                    "id": device.id,
                    "name": device.name,
                    "device_type": device.device_type,
                    "location": location,
                    "battery_level": battery_level,
                    "battery_status": battery_status,
                }
            )
    finally:
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


def set_device_away_alert_enabled(conn, device_id: str, enabled: bool) -> OwnerDevice | None:
    return set_owner_device_away_alert_enabled(conn, device_id, enabled)


def set_devices_order(conn, device_ids: list[str]) -> None:
    set_owner_devices_order(conn, device_ids)


def play_sound(cfg: Config, conn, device_id: str) -> None:
    """Live "play sound" request (icloud.com/find's speaker icon), via pyicloud's
    AppleDevice.play_sound(). This is AirTag/FindMy.py's dashboard counterpart
    to CLAUDE.md's owner/AirTag feature-parity rule, but has none: FindMy.py
    only implements the read-only offline-finding reports API an AirTag
    broadcasts over Bluetooth to nearby strangers' phones - making one chirp on
    demand needs Apple's own Find My app to relay an encrypted command through
    a phone within Bluetooth range of the tag right now, a different,
    unreverse-engineered protocol this app has no way to speak. Raises
    RuntimeError if not connected, LookupError if device_id isn't one of the
    account's current devices."""
    with _session_lock:
        api = _connect(cfg, conn)
        if api is None:
            raise RuntimeError("Owner tracking not connected.")
        try:
            device = next((d for d in api.devices if d.id == device_id), None)
            if device is None:
                raise LookupError(f"Unknown device_id '{device_id}'")
            device.play_sound()
        finally:
            # See _snapshot_devices's docstring: accessing api.devices starts a
            # background re-poll thread that must be stopped explicitly.
            api.devices.stop_event.set()
            _cleanup_api_bridge(api)


def _is_reauth_exception(exc: BaseException, api=None) -> bool:
    if isinstance(exc, OwnerReauthRequiredError):
        return True
    if api is not None and (getattr(api, "requires_2fa", False) or getattr(api, "requires_2sa", False)):
        return True
    try:
        from pyicloud.exceptions import (
            PyiCloud2FARequiredException,
            PyiCloud2SARequiredException,
            PyiCloudAuthRequiredException,
        )

        return isinstance(
            exc,
            (
                PyiCloud2FARequiredException,
                PyiCloud2SARequiredException,
                PyiCloudAuthRequiredException,
            ),
        )
    except ImportError:
        return False


def fetch_owner_device_locations(cfg: Config, conn) -> list[OwnerLocation]:
    """Refreshes every device's identity (name/type) in `owner_devices` - not just
    enabled ones, so a newly-seen device is toggleable from the dashboard as soon
    as this poll runs, without needing a live Apple call from the dashboard itself
    (see module docstring; tasks/todo.md) - then returns a fresh location for
    every *enabled* device, or [] if not connected or none of the enabled devices
    returned a location this call. Also disables (or, if never enabled,
    deletes) any previously-seen device that's dropped out of this listing -
    see the cleanup step below.

    Also records this attempt's outcome on `owner_apple_credentials`
    (last_sync_at/last_sync_error/reauth_required - see
    db.set_owner_apple_sync_status), so a lapsed session or a transient
    Apple/network error surfaces on the dashboard instead of only ever being
    logged, and expired-session polls stop before triggering interactive 2FA
    prompts on the user's phone."""
    if is_login_in_progress():
        logger.info("Owner Apple login in progress - skipping owner device sync this cycle.")
        return []
    creds = get_owner_apple_credentials(conn)
    if creds is None:
        return []
    if getattr(creds, "reauth_required", False):
        logger.info("Owner Apple session requires re-authentication - skipping owner device sync.")
        return []

    now = dt.datetime.now(dt.timezone.utc)
    api = None
    try:
        with _session_lock:
            if is_login_in_progress():
                logger.info("Owner Apple login in progress - skipping owner device sync this cycle.")
                return []
            api = _connect(cfg, conn)
            if api is None:
                return []
            snapshot = _snapshot_devices(api)
    except OwnerReauthRequiredError as exc:
        set_owner_apple_sync_status(conn, now, str(exc), reauth_required=True)
        raise
    except Exception as exc:
        if _is_reauth_exception(exc, api):
            set_owner_apple_sync_status(conn, now, str(exc), reauth_required=True)
        else:
            set_owner_apple_sync_status(conn, now, str(exc))
        raise
    finally:
        _cleanup_api_bridge(api)
    set_owner_apple_sync_status(conn, now, None)

    upsert_owner_devices(
        conn,
        [{"id": d["id"], "name": d["name"], "device_type": d["device_type"]} for d in snapshot],
        seen_at=now,
    )

    # A device Apple stops listing here - removed from iCloud, or (see
    # set_include_family) dropped because Family Sharing was just turned off -
    # can never get a fresh location again. An *enabled* device is disabled
    # instead of deleted, mirroring the existing invariant that a disabled
    # device never gets a fresh location (set_owner_device_enabled already
    # clears is_primary too) and preserving its history/on_account badge. A
    # device that was never enabled has no history or customization worth
    # keeping, so it's deleted outright - otherwise it would keep cluttering
    # Settings -> Eigene Geräte forever from having been observed just once
    # (e.g. a family member's device, seen only while Family Sharing was on).
    all_devices = db_list_owner_devices(conn)
    snapshot_ids = {d["id"] for d in snapshot}
    for device in all_devices:
        if device.id in snapshot_ids:
            continue
        if device.enabled:
            set_owner_device_enabled(conn, device.id, False)
            logger.info(
                "Owner device '%s' (%s) is no longer on the Apple account - disabling tracking.",
                device.name,
                device.id,
            )
        else:
            delete_owner_device(conn, device.id)
            logger.info(
                "Owner device '%s' (%s) is no longer on the Apple account and was never tracked - forgetting it.",
                device.name,
                device.id,
            )

    enabled_ids = {d.id for d in all_devices if d.enabled} & snapshot_ids
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
                battery_level=device["battery_level"],
                battery_status=device["battery_status"],
            )
        )
    logger.info(
        "Fetched a fresh location for %d of %d enabled owner device(s) this poll.",
        len(locations),
        len(enabled_ids),
    )
    return locations
