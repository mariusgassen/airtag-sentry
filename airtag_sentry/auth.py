"""Apple ID login flow for FindMy.py, including interactive 2FA handling.

`interactive_login()` MUST be run by a human with a TTY and the real Apple ID
credentials + a live 2FA code - it cannot be automated or run in a CI/build
sandbox. Run it once (`python -m airtag_sentry login`); after that, `restore_account()`
reloads the persisted session for the scheduler and dashboard.
"""

from __future__ import annotations

import getpass
import logging

from findmy import (
    AppleAccount,
    LocalAnisetteProvider,
    LoginState,
    RemoteAnisetteProvider,
    SmsSecondFactorMethod,
    TrustedDeviceSecondFactorMethod,
)

from airtag_sentry.config import Config

logger = logging.getLogger(__name__)


def _build_anisette_provider(cfg: Config):
    anisette_cfg = cfg.apple.anisette
    if anisette_cfg.mode == "remote":
        if not anisette_cfg.remote_url:
            raise ValueError("ANISETTE_REMOTE_URL must be set when ANISETTE_MODE=remote")
        return RemoteAnisetteProvider(anisette_cfg.remote_url)
    return LocalAnisetteProvider(libs_path=anisette_cfg.libs_path)


def interactive_login(cfg: Config) -> None:
    """Prompt for Apple ID credentials (and 2FA, if required), then persist the session."""
    account = AppleAccount(_build_anisette_provider(cfg))

    email = input("Apple ID email: ")
    password = getpass.getpass("Apple ID password: ")

    state = account.login(email, password)

    if state == LoginState.REQUIRE_2FA:
        methods = account.get_2fa_methods()
        for i, method in enumerate(methods):
            if isinstance(method, TrustedDeviceSecondFactorMethod):
                print(f"{i} - Trusted Device")
            elif isinstance(method, SmsSecondFactorMethod):
                print(f"{i} - SMS ({method.phone_number})")

        choice = int(input("Choose a 2FA method: "))
        method = methods[choice]
        method.request()
        code = input("Enter the code you received: ")
        method.submit(code)

    account.to_json(cfg.apple.store_path)
    print(f"Logged in as {account.account_name} ({account.first_name} {account.last_name}).")
    print(f"Session saved to {cfg.apple.store_path} - the scheduler and dashboard will reuse it.")


def restore_account(cfg: Config) -> AppleAccount:
    """Restore a previously saved session. Raises FileNotFoundError if none exists yet."""
    try:
        return AppleAccount.from_json(
            cfg.apple.store_path, anisette_libs_path=cfg.apple.anisette.libs_path
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"No saved Apple session at {cfg.apple.store_path}. Run "
            "`python -m airtag_sentry login` interactively first."
        ) from exc
