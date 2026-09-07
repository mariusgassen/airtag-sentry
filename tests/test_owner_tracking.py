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


def test_fetch_owner_location_returns_none_without_device_selected(monkeypatch):
    """Connected but no device chosen yet (see set_selected_device()) - no
    Apple call should happen at all, not just an eventual None."""
    from airtag_sentry.db import OwnerAppleCredentials

    creds = OwnerAppleCredentials(
        apple_id="owner@example.com",
        encrypted_password="enc",
        selected_device_id=None,
        selected_device_name=None,
    )
    monkeypatch.setattr(owner_tracking, "get_owner_apple_credentials", lambda conn: creds)

    def _fail_build_api(*args, **kwargs):
        raise AssertionError("_build_api should not be called without a selected device")

    monkeypatch.setattr(owner_tracking, "_build_api", _fail_build_api)

    assert owner_tracking.fetch_owner_location(cfg=None, conn=None) is None


def test_list_owner_devices_returns_empty_when_not_connected(monkeypatch):
    monkeypatch.setattr(owner_tracking, "get_owner_apple_credentials", lambda conn: None)
    assert owner_tracking.list_owner_devices(cfg=None, conn=None) == []


def test_fetch_owner_location_reads_location_as_a_property(monkeypatch):
    """Regression test: pyicloud's AppleDevice.location is a @property (as of
    the pyicloud>=1.0 pin's current resolution, 2.7.0), returning the location
    dict directly - calling it like a method (the old `device.location()`)
    raises TypeError the moment a real account returns a location. Also
    exercises the "match the selected device by id" lookup added alongside
    the fix."""
    from airtag_sentry.db import OwnerAppleCredentials

    class _FakeAppleConfig:
        owner_session_dir = "/tmp/unused"

    class _FakeConfig:
        key_encryption_key = "irrelevant-here"
        apple = _FakeAppleConfig()

    creds = OwnerAppleCredentials(
        apple_id="owner@example.com",
        encrypted_password="enc",
        selected_device_id="device-1",
        selected_device_name="iPhone von Marius",
    )
    monkeypatch.setattr(owner_tracking, "get_owner_apple_credentials", lambda conn: creds)
    monkeypatch.setattr(owner_tracking.keystore, "decrypt", lambda key, enc: "password")

    class _FakeDevice:
        def __init__(self, device_id):
            self._id = device_id

        def __getitem__(self, key):
            if key == "id":
                return self._id
            raise KeyError(key)

        @property
        def location(self):
            return {"latitude": 1.5, "longitude": 2.5, "horizontalAccuracy": 10.0}

    class _FakeApi:
        devices = [_FakeDevice("other-device"), _FakeDevice("device-1")]

    monkeypatch.setattr(owner_tracking, "_build_api", lambda *a, **k: _FakeApi())

    location = owner_tracking.fetch_owner_location(_FakeConfig(), conn=None)
    assert location.lat == 1.5
    assert location.lon == 2.5
    assert location.horizontal_accuracy == 10.0


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
