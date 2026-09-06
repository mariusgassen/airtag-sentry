import types

import pytest

from airtag_sentry import auth


def _cfg(store_path) -> types.SimpleNamespace:
    return types.SimpleNamespace(apple=types.SimpleNamespace(store_path=str(store_path)))


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
