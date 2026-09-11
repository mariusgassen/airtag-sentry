import pytest

from airtag_sentry import owner_tracking
from airtag_sentry.db import OwnerDevice


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
        def __init__(self, apple_id, password, cookie_directory=None, with_family=False):
            raise PyiCloudFailedLoginException("Invalid email/password combination.")

    monkeypatch.setattr("pyicloud.PyiCloudService", _FailingPyiCloudService)

    with pytest.raises(RuntimeError, match="app-specific password"):
        owner_tracking._build_api("owner@example.com", "wrong-password", "/tmp/unused")


def test_fetch_owner_device_locations_returns_empty_when_not_connected(monkeypatch):
    monkeypatch.setattr(owner_tracking, "get_owner_apple_credentials", lambda conn: None)
    assert owner_tracking.fetch_owner_device_locations(cfg=None, conn=None) == []


class _FakeStopEvent:
    def __init__(self):
        self.was_set = False

    def set(self):
        self.was_set = True


class _FakeDevice:
    """Mirrors the two facts about pyicloud's real AppleDevice that matter here:
    `.location` is a plain attribute (a property in the real SDK, never a
    method), and `.location_available` gates whether it's populated. `.data`
    mirrors the real SDK's raw content dict, read by _snapshot_devices's
    diagnostic log for a device with no location."""

    def __init__(self, id, name, device_type, location, data=None):
        self.id = id
        self.name = name
        self.device_type = device_type
        self.location = location
        self.location_available = location is not None
        self.data = data if data is not None else {}


class _FakeDeviceList:
    def __init__(self, devices):
        self._devices = devices
        self.stop_event = _FakeStopEvent()
        self.refresh_calls = []

    def __iter__(self):
        return iter(self._devices)

    def refresh(self, locate=True):
        self.refresh_calls.append(locate)


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
        {
            "id": "d1",
            "name": "MacBook Air",
            "device_type": "Mac",
            "location": online.location,
            "battery_level": None,
            "battery_status": None,
        },
        {
            "id": "d2",
            "name": "iPad",
            "device_type": "iPad",
            "location": None,
            "battery_level": None,
            "battery_status": None,
        },
    ]
    assert api.devices.stop_event.was_set is True


def test_snapshot_devices_reads_battery_from_device_data():
    device = _FakeDevice(
        "d1", "iPhone", "iPhone", {"latitude": 1.0, "longitude": 2.0}, data={"batteryLevel": 0.42, "batteryStatus": "Charging"}
    )
    api = _FakeApi([device])

    snapshot = owner_tracking._snapshot_devices(api)

    assert snapshot[0]["battery_level"] == 0.42
    assert snapshot[0]["battery_status"] == "Charging"


def test_snapshot_devices_forces_a_live_locate_before_reading_locations():
    """Regression test for a real production failure: every tracked device showed
    no location at all, even after the two bugs above were fixed. Confirmed
    against the real pyicloud source: the manager's very first `.devices` access
    only performs Apple's identity-only `initClient` call - the block that asks
    Apple to actually locate devices (`shouldLocate`/`isUpdatingAllLocations`) is
    gated behind an internal `_server_ctx` that doesn't exist yet on that first
    call. Since this app never touches `.devices` a second time on its own,
    location data was always whatever Apple happened to have cached (often
    nothing). _snapshot_devices must explicitly call the manager's own
    `refresh(locate=True)` to force that second, locate-flagged request."""
    device = _FakeDevice("d1", "MacBook Air", "Mac", {"latitude": 1.0, "longitude": 2.0})
    api = _FakeApi([device])

    owner_tracking._snapshot_devices(api)

    assert api.devices.refresh_calls == [True]


def test_fetch_owner_device_locations_persists_identity_for_every_device_not_just_enabled(monkeypatch):
    """Regression test: device identity used to only get persisted as a side
    effect of a live *dashboard* request (the old list_owner_devices(), called
    from GET /api/owner-devices) - if that request never succeeded, or nobody
    ever opened the dashboard, owner_devices stayed empty forever even though
    the background poller (tracker.py -> fetch_owner_device_locations) was
    running the whole time, which also meant devices silently vanished from
    the Objekte view and Telegram's /list (both pure DB reads). Now the
    poller itself upserts identity for every device it sees, enabled or not,
    on every poll cycle."""
    enabled_device = _FakeDevice("d1", "MacBook Air", "Mac", {"latitude": 1.0, "longitude": 2.0})
    disabled_device = _FakeDevice("d2", "iPhone", "iPhone", None)
    api = _FakeApi([enabled_device, disabled_device])
    monkeypatch.setattr(owner_tracking, "get_owner_apple_credentials", lambda conn: object())
    monkeypatch.setattr(owner_tracking, "_connect", lambda cfg, conn: api)

    upserted = []
    monkeypatch.setattr(
        owner_tracking,
        "upsert_owner_devices",
        lambda conn, devices, seen_at: upserted.extend(devices),
    )
    sync_status_calls = []
    monkeypatch.setattr(
        owner_tracking,
        "set_owner_apple_sync_status",
        lambda conn, synced_at, error: sync_status_calls.append(error),
    )
    monkeypatch.setattr(
        owner_tracking,
        "db_list_owner_devices",
        lambda conn: [
            OwnerDevice(id="d1", name="MacBook Air", device_type="Mac", enabled=True, is_primary=False),
            OwnerDevice(id="d2", name="iPhone", device_type="iPhone", enabled=False, is_primary=False),
        ],
    )

    locations = owner_tracking.fetch_owner_device_locations(cfg=None, conn=None)

    assert upserted == [
        {"id": "d1", "name": "MacBook Air", "device_type": "Mac"},
        {"id": "d2", "name": "iPhone", "device_type": "iPhone"},
    ]
    assert [loc.device_id for loc in locations] == ["d1"]
    assert sync_status_calls == [None]  # a successful sync clears any prior error


def test_fetch_owner_device_locations_disables_a_device_no_longer_on_the_account(monkeypatch):
    """Regression test: turning off Family Sharing (set_include_family) - or a
    device simply being removed from iCloud - stops Apple from listing it in
    future polls, but a previously-enabled device's `enabled` flag was never
    cleared, so it kept showing up as a tracked device in the dashboard's
    Objekte list forever, with nothing but an easy-to-miss on_account badge to
    explain why it never updates. The poller must disable tracking for any
    enabled device that drops out of the live listing."""
    still_present = _FakeDevice("d1", "MacBook Air", "Mac", {"latitude": 1.0, "longitude": 2.0})
    api = _FakeApi([still_present])
    monkeypatch.setattr(owner_tracking, "get_owner_apple_credentials", lambda conn: object())
    monkeypatch.setattr(owner_tracking, "_connect", lambda cfg, conn: api)
    monkeypatch.setattr(owner_tracking, "upsert_owner_devices", lambda conn, devices, seen_at: None)
    monkeypatch.setattr(owner_tracking, "set_owner_apple_sync_status", lambda conn, synced_at, error: None)
    monkeypatch.setattr(
        owner_tracking,
        "db_list_owner_devices",
        lambda conn: [
            OwnerDevice(id="d1", name="MacBook Air", device_type="Mac", enabled=True, is_primary=False),
            OwnerDevice(id="d2", name="Kid's iPhone", device_type="iPhone", enabled=True, is_primary=True),
        ],
    )
    disabled = []
    monkeypatch.setattr(
        owner_tracking, "set_owner_device_enabled", lambda conn, device_id, enabled: disabled.append((device_id, enabled))
    )

    locations = owner_tracking.fetch_owner_device_locations(cfg=None, conn=None)

    assert disabled == [("d2", False)]
    assert [loc.device_id for loc in locations] == ["d1"]


def test_fetch_owner_device_locations_forgets_a_never_enabled_device_no_longer_on_the_account(monkeypatch):
    """Regression test: a device that was merely observed once - e.g. a family
    member's, seen only while Family Sharing was on - but never opted into
    tracking has no history or customization worth keeping. Disabling it (like
    an enabled device) would still leave a stale row cluttering Settings ->
    Eigene Geräte forever, since that panel lists every device ever seen with
    no on_account filtering. The poller must delete it outright once it drops
    out of the live listing, instead of just disabling it."""
    still_present = _FakeDevice("d1", "MacBook Air", "Mac", {"latitude": 1.0, "longitude": 2.0})
    api = _FakeApi([still_present])
    monkeypatch.setattr(owner_tracking, "get_owner_apple_credentials", lambda conn: object())
    monkeypatch.setattr(owner_tracking, "_connect", lambda cfg, conn: api)
    monkeypatch.setattr(owner_tracking, "upsert_owner_devices", lambda conn, devices, seen_at: None)
    monkeypatch.setattr(owner_tracking, "set_owner_apple_sync_status", lambda conn, synced_at, error: None)
    monkeypatch.setattr(
        owner_tracking,
        "db_list_owner_devices",
        lambda conn: [
            OwnerDevice(id="d1", name="MacBook Air", device_type="Mac", enabled=True, is_primary=False),
            OwnerDevice(id="d2", name="Kid's iPhone", device_type="iPhone", enabled=False, is_primary=False),
        ],
    )
    disabled = []
    deleted = []
    monkeypatch.setattr(
        owner_tracking, "set_owner_device_enabled", lambda conn, device_id, enabled: disabled.append((device_id, enabled))
    )
    monkeypatch.setattr(owner_tracking, "delete_owner_device", lambda conn, device_id: deleted.append(device_id))

    locations = owner_tracking.fetch_owner_device_locations(cfg=None, conn=None)

    assert deleted == ["d2"]
    assert disabled == []
    assert [loc.device_id for loc in locations] == ["d1"]


def test_fetch_owner_device_locations_records_sync_error_and_reraises(monkeypatch):
    """Regression test: a live Apple call failure (lapsed pyicloud session,
    transient network error, ...) used to only ever be logged by tracker.py's
    broad except-and-log around the whole poll - invisible from the
    dashboard. Now it's also persisted (OwnerAppleCredentials.last_sync_error,
    surfaced via GET /api/apple/owner/status), and the exception still
    propagates unchanged so tracker.py's existing handling is untouched."""
    monkeypatch.setattr(owner_tracking, "get_owner_apple_credentials", lambda conn: object())

    def _raise_connect(cfg, conn):
        raise RuntimeError("Invalid email/password combination.")

    monkeypatch.setattr(owner_tracking, "_connect", _raise_connect)

    recorded = []
    monkeypatch.setattr(
        owner_tracking,
        "set_owner_apple_sync_status",
        lambda conn, synced_at, error: recorded.append(error),
    )

    with pytest.raises(RuntimeError, match="Invalid email/password combination"):
        owner_tracking.fetch_owner_device_locations(cfg=None, conn=None)

    assert recorded == ["Invalid email/password combination."]


def test_set_include_family_delegates_to_db_layer_and_resyncs_immediately(monkeypatch):
    """Regression test: flipping the checkbox used to only take effect on the
    next *scheduled* poll (could be minutes away), making it look like the
    toggle did nothing. A successful flag change must trigger an immediate
    fetch_owner_device_locations() re-sync instead."""
    calls = []
    monkeypatch.setattr(
        owner_tracking, "set_owner_include_family_devices", lambda conn, include: calls.append(include) or True
    )
    resync_calls = []
    monkeypatch.setattr(
        owner_tracking, "fetch_owner_device_locations", lambda cfg, conn: resync_calls.append((cfg, conn)) or []
    )
    assert owner_tracking.set_include_family(cfg="cfg", conn="conn", include_family=True) is True
    assert calls == [True]
    assert resync_calls == [("cfg", "conn")]


def test_set_include_family_skips_resync_when_not_connected(monkeypatch):
    """The db layer returns False when owner tracking isn't connected at all -
    there's nothing to re-sync in that case."""
    monkeypatch.setattr(owner_tracking, "set_owner_include_family_devices", lambda conn, include: False)
    resync_calls = []
    monkeypatch.setattr(
        owner_tracking, "fetch_owner_device_locations", lambda cfg, conn: resync_calls.append((cfg, conn)) or []
    )
    assert owner_tracking.set_include_family(cfg="cfg", conn="conn", include_family=True) is False
    assert resync_calls == []


def test_set_include_family_survives_a_resync_failure(monkeypatch):
    """A failed live re-sync (lapsed session, transient network error) must not
    make the flag change itself look like it failed - the regular poll will
    still pick it up."""
    monkeypatch.setattr(owner_tracking, "set_owner_include_family_devices", lambda conn, include: True)

    def _raise(cfg, conn):
        raise RuntimeError("boom")

    monkeypatch.setattr(owner_tracking, "fetch_owner_device_locations", _raise)
    assert owner_tracking.set_include_family(cfg="cfg", conn="conn", include_family=True) is True


class _FakeDeviceWithSound(_FakeDevice):
    def __init__(self, id, name, device_type, location):
        super().__init__(id, name, device_type, location)
        self.play_sound_calls = 0

    def play_sound(self):
        self.play_sound_calls += 1


def test_play_sound_sends_to_the_matching_device_and_stops_monitor_thread(monkeypatch):
    target = _FakeDeviceWithSound("d1", "MacBook Air", "Mac", None)
    other = _FakeDeviceWithSound("d2", "iPhone", "iPhone", None)
    api = _FakeApi([target, other])
    monkeypatch.setattr(owner_tracking, "_connect", lambda cfg, conn: api)

    owner_tracking.play_sound(cfg=None, conn=None, device_id="d1")

    assert target.play_sound_calls == 1
    assert other.play_sound_calls == 0
    assert api.devices.stop_event.was_set is True


def test_play_sound_raises_lookup_error_for_unknown_device(monkeypatch):
    api = _FakeApi([_FakeDeviceWithSound("d1", "MacBook Air", "Mac", None)])
    monkeypatch.setattr(owner_tracking, "_connect", lambda cfg, conn: api)

    with pytest.raises(LookupError, match="unknown-id"):
        owner_tracking.play_sound(cfg=None, conn=None, device_id="unknown-id")
    # Still stops the monitor thread even though no device matched.
    assert api.devices.stop_event.was_set is True


def test_play_sound_raises_runtime_error_when_not_connected(monkeypatch):
    monkeypatch.setattr(owner_tracking, "_connect", lambda cfg, conn: None)

    with pytest.raises(RuntimeError, match="not connected"):
        owner_tracking.play_sound(cfg=None, conn=None, device_id="d1")


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
