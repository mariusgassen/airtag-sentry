import contextlib
import types

from airtag_sentry import tracker


def test_poll_once_still_updates_owner_devices_when_airtag_session_missing(monkeypatch):
    """Regression test: owner-device tracking and AirTag tracking are two
    independent Apple sessions (see owner_tracking.py's module docstring),
    but poll_once used to call restore_account() unconditionally as its very
    first line - so a user who connected only owner tracking (not AirTags)
    got a FileNotFoundError on every poll and owner-device locations were
    never recorded, contradicting the "entirely optional/independent"
    contract."""

    @contextlib.contextmanager
    def fake_get_conn(database_url):
        yield object()

    monkeypatch.setattr(tracker, "get_conn", fake_get_conn)
    monkeypatch.setattr(tracker, "get_settings", lambda conn: object())
    monkeypatch.setattr(tracker, "build_notifiers", lambda cfg, conn: [])
    monkeypatch.setattr(tracker, "is_connected", lambda cfg: False)

    def fail_restore_account(cfg):
        raise AssertionError("restore_account() must not be called when no AirTag session exists")

    monkeypatch.setattr(tracker, "restore_account", fail_restore_account)

    def fail_list_airtags(conn):
        raise AssertionError("list_airtags() must not be called when no AirTag session exists")

    monkeypatch.setattr(tracker, "list_airtags", fail_list_airtags)

    calls = []
    monkeypatch.setattr(tracker, "_update_owner_devices", lambda cfg, conn: calls.append((cfg, conn)))

    cfg = types.SimpleNamespace(database_url="unused")
    tracker.poll_once(cfg)

    assert len(calls) == 1
    assert calls[0][0] is cfg
