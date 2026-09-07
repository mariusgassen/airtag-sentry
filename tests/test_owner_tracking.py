import pytest

from airtag_sentry import owner_tracking


def test_submit_owner_2fa_code_without_pending_login_raises():
    with pytest.raises(RuntimeError, match="No owner Apple login in progress"):
        owner_tracking.submit_owner_2fa_code(cfg=None, conn=None, code="123456")


def test_build_api_wraps_failed_login_with_app_specific_password_hint(monkeypatch):
    """Regression test for a real production failure: a user followed this
    project's own (incorrect, since fixed) README advice to use an app-specific
    password and got Apple's generic "-20101 Invalid email/password combination"
    with no indication of why. pyicloud doesn't support app-specific passwords at
    all, so _build_api() should turn that specific exception into a message that
    actually says so."""
    from pyicloud.exceptions import PyiCloudFailedLoginException

    class _FailingPyiCloudService:
        def __init__(self, apple_id, password, cookie_directory=None):
            raise PyiCloudFailedLoginException("Invalid email/password combination.")

    monkeypatch.setattr("pyicloud.PyiCloudService", _FailingPyiCloudService)

    with pytest.raises(RuntimeError, match="app-specific password"):
        owner_tracking._build_api("owner@example.com", "wrong-password", "/tmp/unused")


def test_pyicloud_imports_cleanly():
    """Regression test for a real production failure ("Login failed: No module
    named 'rich'"): pyicloud's own __init__ chain unconditionally imports
    pyicloud.services.notes.rendering.exporter, which does `from rich.console
    import Console` at module load time - but pyicloud doesn't declare rich as
    its own dependency. owner_tracking.py only imports pyicloud lazily inside
    _build_api(), so no other test here exercises this import at all; without
    rich pinned in pyproject.toml, every owner-tracking login attempt failed
    with ModuleNotFoundError as soon as `from pyicloud import PyiCloudService`
    ran."""
    import pyicloud  # noqa: F401
