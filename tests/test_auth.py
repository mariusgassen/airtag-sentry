import types

import pytest
from findmy import LoginState

from airtag_sentry import auth


def _cfg(store_path) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        apple=types.SimpleNamespace(
            store_path=str(store_path),
            anisette=types.SimpleNamespace(libs_path=None),
        )
    )


def test_request_2fa_code_without_pending_login_raises():
    with pytest.raises(RuntimeError, match="No Apple login in progress"):
        auth.request_2fa_code(0)


def test_submit_2fa_code_without_pending_login_raises():
    with pytest.raises(RuntimeError, match="No Apple login in progress"):
        auth.submit_2fa_code(_cfg("unused"), "123456")


def test_is_connected_reflects_store_path_existence(tmp_path):
    store_path = tmp_path / "account.json"
    cfg = _cfg(store_path)

    assert auth.is_connected(cfg) is False

    store_path.write_text("{}")
    assert auth.is_connected(cfg) is True


def test_disconnect_removes_store_path_file(tmp_path):
    store_path = tmp_path / "account.json"
    store_path.write_text("{}")
    cfg = _cfg(store_path)

    auth.disconnect(cfg)
    assert not store_path.exists()

    # Idempotent - disconnecting an already-disconnected session is not an error.
    auth.disconnect(cfg)


_VALID_SESSION_JSON = {
    "ids": {"uid": "test-uid", "devid": "test-devid"},
    "account": {"username": "user@example.com", "password": None, "info": None},
    "login": {"state": 3, "data": {}},  # 3 == LoginState.LOGGED_IN
    "anisette": {"type": "aniRemote", "url": "http://anisette:6969"},
}


def test_import_session_writes_valid_session_to_store_path(tmp_path):
    store_path = tmp_path / "account.json"
    cfg = _cfg(store_path)

    auth.import_session(cfg, _VALID_SESSION_JSON)

    assert auth.is_connected(cfg)
    restored = auth.restore_account(cfg)
    assert restored.login_state == LoginState.LOGGED_IN


def test_import_session_rejects_malformed_session_json(tmp_path):
    cfg = _cfg(tmp_path / "account.json")

    with pytest.raises(ValueError, match="Invalid session file"):
        auth.import_session(cfg, {"not": "a valid session"})

    assert not auth.is_connected(cfg)


def test_has_valid_session_checks_login_state(tmp_path):
    import json

    store_path = tmp_path / "account.json"
    cfg = _cfg(store_path)

    assert auth.has_valid_session(cfg) is False

    store_path.write_text("{not-json")
    assert auth.has_valid_session(cfg) is False

    expired = {
        **_VALID_SESSION_JSON,
        "login": {"state": LoginState.REQUIRE_2FA.value, "data": {}},
    }
    store_path.write_text(json.dumps(expired))
    assert auth.is_connected(cfg) is True
    assert auth.has_valid_session(cfg) is False

    store_path.write_text(json.dumps(_VALID_SESSION_JSON))
    assert auth.has_valid_session(cfg) is True


def test_close_account_runs_async_close_and_closes_event_loop():
    import asyncio

    loop = asyncio.new_event_loop()
    closed = []

    class _FakeAccount:
        def __init__(self):
            self._evt_loop = loop

        async def close(self):
            closed.append(True)

    auth.close_account(_FakeAccount())
    assert closed == [True]
    assert loop.is_closed()


def test_cancel_login_and_disconnect_close_pending_account(tmp_path):
    import time

    closed = []

    class _FakePendingAccount:
        def close(self):
            closed.append(True)

    auth._pending_account = _FakePendingAccount()
    auth._pending_started_at = time.monotonic()
    assert auth.is_login_in_progress() is True

    auth.cancel_login()
    assert closed == [True]
    assert auth.is_login_in_progress() is False

    store_path = tmp_path / "account.json"
    store_path.write_text("{}")
    auth._pending_account = _FakePendingAccount()
    auth._pending_started_at = time.monotonic()
    auth.disconnect(_cfg(store_path))
    assert closed == [True, True]
    assert not store_path.exists()
    assert auth.is_login_in_progress() is False

