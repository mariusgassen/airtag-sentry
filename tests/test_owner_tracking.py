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


def test_list_owner_devices_returns_empty_when_not_connected(monkeypatch):
    monkeypatch.setattr(owner_tracking, "get_owner_apple_credentials", lambda conn: None)
    assert owner_tracking.list_owner_devices(cfg=None, conn=None) == []


class _FakeStopEvent:
    def __init__(self):
        self.was_set = False

    def set(self):
        self.was_set = True


class _FakeDevice:
    """Mirrors the two facts about pyicloud's real AppleDevice that matter here:
    `.location` is a plain attribute (a property in the real SDK, never a
    method), and `.location_available` gates whether it's populated."""

    def __init__(self, id, name, device_type, location):
        self.id = id
        self.name = name
        self.device_type = device_type
        self.location = location
        self.location_available = location is not None


class _FakeDeviceList:
    def __init__(self, devices):
        self._devices = devices
        self.stop_event = _FakeStopEvent()

    def __iter__(self):
        return iter(self._devices)


class _FakeApi:
    def __init__(self, devices):
        self.devices = _FakeDeviceList(devices)


def test_snapshot_devices_reads_location_as_a_property_and_stops_monitor_thread():
    """Regression test for a real production failure: fetch_owner_device_locations
    (formerly fetch_owner_location) called `device.location()` as a method, but
    pyicloud's AppleDevice.location is a property - every call raised TypeError,
    silently swallowed by tracker.py's broad except-and-log, so owner tracking
    never actually recorded a location despite looking connected. Separately:
    accessing `.devices` at all starts a background thread that re-polls Apple
    every 5 minutes and is otherwise never stopped - since a fresh PyiCloudService
    is built on every poll, that leaked one live thread per poll, forever.
    _snapshot_devices must read `.location` without calling it, and must stop
    that thread via `stop_event.set()` once it's done with `.devices`."""
    online = _FakeDevice(
        "d1", "MacBook Air", "Mac", {"latitude": 52.5, "longitude": 13.4, "horizontalAccuracy": 5.0}
    )
    offline = _FakeDevice("d2", "iPad", "iPad", None)
    api = _FakeApi([online, offline])

    snapshot = owner_tracking._snapshot_devices(api)

    assert snapshot == [
        {"id": "d1", "name": "MacBook Air", "device_type": "Mac", "location": online.location},
        {"id": "d2", "name": "iPad", "device_type": "iPad", "location": None},
    ]
    assert api.devices.stop_event.was_set is True


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
