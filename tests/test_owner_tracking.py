import pytest

from airtag_sentry import owner_tracking


def test_submit_owner_2fa_code_without_pending_login_raises():
    with pytest.raises(RuntimeError, match="No owner Apple login in progress"):
        owner_tracking.submit_owner_2fa_code(cfg=None, conn=None, code="123456")


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
