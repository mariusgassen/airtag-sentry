"""Apple ID login flow for FindMy.py, driven from the dashboard UI (see
web/app.py's /api/apple/* routes) rather than the CLI - Apple's login protocol
doesn't need a terminal, only a live 2FA code from the account owner.

The flow is a small stateful wizard: start_login() submits credentials and,
if 2FA is required, returns the available methods; request_2fa_code() picks
one and triggers Apple to send the code; submit_2fa_code() finishes and
persists the session. The partially-authenticated AppleAccount is held in a
module-level variable between requests - this is a single-user app with one
human stepping through one login attempt at a time, so no session-keyed
store is needed. After that, restore_account() reloads the persisted session
for the scheduler and dashboard, same as before.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

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


@dataclasses.dataclass(frozen=True)
class TwoFactorMethodInfo:
    index: int
    kind: str  # "trusted_device" | "sms"
    phone_number: str | None


@dataclasses.dataclass(frozen=True)
class LoginResult:
    requires_2fa: bool
    methods: list[TwoFactorMethodInfo]


_pending_account: AppleAccount | None = None
_pending_methods: list | None = None
_pending_chosen_method = None


def _build_anisette_provider(cfg: Config):
    anisette_cfg = cfg.apple.anisette
    if anisette_cfg.mode == "remote":
        if not anisette_cfg.remote_url:
            raise ValueError("ANISETTE_REMOTE_URL must be set when ANISETTE_MODE=remote")
        return RemoteAnisetteProvider(anisette_cfg.remote_url)
    return LocalAnisetteProvider(libs_path=anisette_cfg.libs_path)


def _describe_method(index: int, method) -> TwoFactorMethodInfo:
    if isinstance(method, TrustedDeviceSecondFactorMethod):
        return TwoFactorMethodInfo(index=index, kind="trusted_device", phone_number=None)
    if isinstance(method, SmsSecondFactorMethod):
        return TwoFactorMethodInfo(index=index, kind="sms", phone_number=method.phone_number)
    return TwoFactorMethodInfo(index=index, kind="unknown", phone_number=None)


def start_login(cfg: Config, email: str, password: str) -> LoginResult:
    """Submit Apple ID credentials. Persists the session immediately if no 2FA
    is required, otherwise stashes the in-progress account and returns the
    available 2FA methods for request_2fa_code()/submit_2fa_code()."""
    global _pending_account, _pending_methods, _pending_chosen_method

    account = AppleAccount(_build_anisette_provider(cfg))
    state = account.login(email, password)

    if state != LoginState.REQUIRE_2FA:
        account.to_json(cfg.apple.store_path)
        return LoginResult(requires_2fa=False, methods=[])

    methods = account.get_2fa_methods()
    _pending_account = account
    _pending_methods = methods
    _pending_chosen_method = None
    return LoginResult(
        requires_2fa=True,
        methods=[_describe_method(i, m) for i, m in enumerate(methods)],
    )


def request_2fa_code(method_index: int) -> None:
    """Pick a 2FA method and trigger Apple to send the code to it."""
    global _pending_chosen_method
    if not _pending_methods:
        raise RuntimeError("No Apple login in progress.")
    method = _pending_methods[method_index]
    method.request()
    _pending_chosen_method = method


def submit_2fa_code(cfg: Config, code: str) -> None:
    """Complete the login with the received code and persist the session."""
    global _pending_account, _pending_methods, _pending_chosen_method
    if _pending_account is None or _pending_chosen_method is None:
        raise RuntimeError(
            "No Apple login in progress, or no 2FA method was selected yet."
        )
    _pending_chosen_method.submit(code)
    _pending_account.to_json(cfg.apple.store_path)
    _pending_account = None
    _pending_methods = None
    _pending_chosen_method = None


def is_connected(cfg: Config) -> bool:
    return Path(cfg.apple.store_path).exists()


def disconnect(cfg: Config) -> None:
    Path(cfg.apple.store_path).unlink(missing_ok=True)


def restore_account(cfg: Config) -> AppleAccount:
    """Restore a previously saved session. Raises FileNotFoundError if none exists yet."""
    try:
        return AppleAccount.from_json(
            cfg.apple.store_path, anisette_libs_path=cfg.apple.anisette.libs_path
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"No saved Apple session at {cfg.apple.store_path}. Connect your Apple ID "
            "from the dashboard's Settings panel first."
        ) from exc
