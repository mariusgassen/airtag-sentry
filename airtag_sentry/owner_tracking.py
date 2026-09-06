"""Owner device location, via Apple's classic Find My iPhone web service (`pyicloud`) -
a different protocol than `FindMy.py`'s AirTag/search-party reports.

`FindMy.py`'s `fetch_location_history` queries Apple's offline-finding/crowd-sourced
network, which mostly only produces reports for a device that's off, dead, or in
airplane mode - not a live, connected phone. Apple's separate `fmipservice` (the one
behind icloud.com/find) gives a near-real-time location for the owner's own signed-in
devices instead, which is what "did the tag move without me" correlation needs. This
is a second, independent Apple session from the one `auth.py` manages for AirTags -
its own login, its own 2FA, its own persisted session.

Entirely optional: every function here is a no-op (or returns None) when
`cfg.apple.owner` isn't configured, so the rest of the app is unaffected if unset.
"""

from __future__ import annotations

import datetime as dt
import logging

from airtag_sentry.config import Config
from airtag_sentry.db import OwnerLocation

logger = logging.getLogger(__name__)


def _build_api(cfg: Config):
    from pyicloud import PyiCloudService

    owner = cfg.apple.owner
    if owner is None:
        raise RuntimeError(
            "Owner device tracking is not configured - set APPLE_OWNER_ID and "
            "APPLE_OWNER_PASSWORD to enable it."
        )
    return PyiCloudService(owner.apple_id, owner.password, cookie_directory=owner.session_dir)


def interactive_owner_login(cfg: Config) -> None:
    """Log in to the owner's Apple ID and persist a trusted session, so later polls
    don't need interactive 2FA again (~2 months per pyicloud's session lifetime).

    MUST be run by a human with a TTY and a live 2FA code - same constraint as
    `auth.interactive_login()`. Run it once (`python -m airtag_sentry login-owner`).
    """
    api = _build_api(cfg)

    if api.requires_2fa:
        code = input("Enter the 2FA code sent to your Apple devices: ")
        if not api.validate_2fa_code(code):
            raise RuntimeError("Failed to verify the 2FA code.")
        if not api.is_trusted_session:
            if not api.trust_session():
                logger.warning(
                    "Could not mark this session as trusted - you may be prompted "
                    "for a 2FA code again sooner than usual."
                )

    print(f"Logged in as {cfg.apple.owner.apple_id}.")
    print(f"Session saved to {cfg.apple.owner.session_dir} - future polls will reuse it.")


def fetch_owner_location(cfg: Config) -> OwnerLocation | None:
    """Fetch the owner's current device location, or None if the feature isn't
    configured or no device returned a location this call."""
    if cfg.apple.owner is None:
        return None

    api = _build_api(cfg)
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
