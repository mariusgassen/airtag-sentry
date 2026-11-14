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

import asyncio
import dataclasses
import inspect
import json
import logging
from pathlib import Path
import threading
import time

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


_PENDING_LOGIN_TTL_SECONDS = 600.0

_pending_lock = threading.Lock()
_pending_account: AppleAccount | None = None
_pending_methods: list | None = None
_pending_chosen_method = None
_pending_started_at: float | None = None
_login_in_progress_count = 0


def close_account(account) -> None:
    """Close an AppleAccount's aiohttp session and event loop without raising."""
    if account is None:
        return
    close = getattr(account, "close", None)
    if not callable(close):
        return
    evt_loop = getattr(account, "_evt_loop", None)
    try:
        if inspect.iscoroutinefunction(close):
            if evt_loop is not None and not evt_loop.is_closed() and not evt_loop.is_running():
                evt_loop.run_until_complete(close())
            elif evt_loop is None:
                asyncio.run(close())
        else:
            close()
    except Exception:
        logger.debug("Ignoring error while closing AppleAccount.", exc_info=True)
    finally:
        if evt_loop is not None and not evt_loop.is_closed() and not evt_loop.is_running():
            try:
                evt_loop.close()
            except Exception:
                logger.debug("Ignoring error while closing AppleAccount event loop.", exc_info=True)


def _pop_pending_state():
    global _pending_account, _pending_methods, _pending_chosen_method, _pending_started_at
    account = _pending_account
    _pending_account = None
    _pending_methods = None
    _pending_chosen_method = None
    _pending_started_at = None
    return account


def is_login_in_progress() -> bool:
    """Whether an interactive AirTag Apple login/2FA flow is currently active."""
    expired_account = None
    with _pending_lock:
        if _login_in_progress_count > 0:
            return True
        if _pending_account is None:
            return False
        if (
            _pending_started_at is not None
            and (time.monotonic() - _pending_started_at) > _PENDING_LOGIN_TTL_SECONDS
        ):
            expired_account = _pop_pending_state()
        else:
            return True
    if expired_account is not None:
        close_account(expired_account)
    return False


def cancel_login() -> None:
    """Cancel any in-progress AirTag Apple login and close its AppleAccount."""
    with _pending_lock:
        old_account = _pop_pending_state()
    if old_account is not None:
        close_account(old_account)


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
    global _pending_account, _pending_methods, _pending_chosen_method, _pending_started_at
    global _login_in_progress_count

    with _pending_lock:
        _login_in_progress_count += 1
        old_account = _pop_pending_state()
    if old_account is not None:
        close_account(old_account)

    account = None
    try:
        account = AppleAccount(_build_anisette_provider(cfg))
        state = account.login(email, password)

        if state != LoginState.REQUIRE_2FA:
            account.to_json(cfg.apple.store_path)
            close_account(account)
            account = None
            return LoginResult(requires_2fa=False, methods=[])

        methods = account.get_2fa_methods()
        with _pending_lock:
            _pending_account = account
            _pending_methods = methods
            _pending_chosen_method = None
            _pending_started_at = time.monotonic()
        account = None
        return LoginResult(
            requires_2fa=True,
            methods=[_describe_method(i, m) for i, m in enumerate(methods)],
        )
    finally:
        if account is not None:
            close_account(account)
        with _pending_lock:
            _login_in_progress_count -= 1


def request_2fa_code(method_index: int) -> None:
    """Pick a 2FA method and trigger Apple to send the code to it."""
    global _pending_chosen_method
    if not is_login_in_progress():
        raise RuntimeError("No Apple login in progress.")
    with _pending_lock:
        methods = _pending_methods
    if not methods:
        raise RuntimeError("No Apple login in progress.")
    method = methods[method_index]
    method.request()
    with _pending_lock:
        if _pending_methods is methods:
            _pending_chosen_method = method


def submit_2fa_code(cfg: Config, code: str) -> None:
    """Complete the login with the received code and persist the session."""
    with _pending_lock:
        account = _pending_account
        chosen_method = _pending_chosen_method
        started_at = _pending_started_at

    if account is None or chosen_method is None:
        raise RuntimeError(
            "No Apple login in progress, or no 2FA method was selected yet."
        )
    if started_at is not None and (time.monotonic() - started_at) > _PENDING_LOGIN_TTL_SECONDS:
        cancel_login()
        raise RuntimeError("Apple login session expired - please sign in again.")

    chosen_method.submit(code)
    account.to_json(cfg.apple.store_path)
    with _pending_lock:
        if _pending_account is account:
            _pop_pending_state()
    close_account(account)


def is_connected(cfg: Config) -> bool:
    return Path(cfg.apple.store_path).exists()


def has_valid_session(cfg: Config) -> bool:
    """Whether store_path holds an authenticated (LOGGED_IN) FindMy.py session."""
    path = Path(cfg.apple.store_path)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    login = data.get("login")
    if not isinstance(login, dict):
        return False
    return login.get("state") == LoginState.LOGGED_IN.value


def disconnect(cfg: Config) -> None:
    cancel_login()
    Path(cfg.apple.store_path).unlink(missing_ok=True)


def import_session(cfg: Config, session_json: dict) -> None:
    """Import an Apple session generated elsewhere (e.g. AppleAccount.to_json()
    run on a machine with genuine Apple hardware) instead of performing the
    live SRP+2FA handshake here. Fallback for when Apple's anti-automation
    defenses reject fresh login attempts from this container's own anisette
    identity with `GSA request: 503` - see tasks/roadmap.md #12."""
    account = None
    try:
        account = AppleAccount.from_json(
            session_json, anisette_libs_path=cfg.apple.anisette.libs_path
        )
    except Exception as exc:
        raise ValueError(f"Invalid session file: {exc}") from exc
    try:
        account.to_json(cfg.apple.store_path)
    finally:
        close_account(account)


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
