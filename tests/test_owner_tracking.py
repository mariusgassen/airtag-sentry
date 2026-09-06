import pytest

from airtag_sentry import owner_tracking


def test_submit_owner_2fa_code_without_pending_login_raises():
    with pytest.raises(RuntimeError, match="No owner Apple login in progress"):
        owner_tracking.submit_owner_2fa_code(cfg=None, conn=None, code="123456")
