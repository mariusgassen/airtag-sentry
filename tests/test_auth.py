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
