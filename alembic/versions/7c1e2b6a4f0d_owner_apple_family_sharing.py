"""owner apple family sharing toggle

Revision ID: 7c1e2b6a4f0d
Revises: 999c5f0d00a3
Create Date: 2026-09-08 13:00:00.000000

pyicloud's PyiCloudService defaults to `with_family=True`, which pulls Family
Sharing members' devices into `api.devices` alongside the account's own -
owner_tracking.py's _build_api never overrode this, so a connected account
with location sharing set up would list/track other people's devices too.
`owner_apple_credentials.include_family_devices` makes that opt-in instead,
surfaced as a checkbox in the dashboard's owner-tracking connect dialog
(default off - this app only ever wants "my own" devices).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7c1e2b6a4f0d'
down_revision: Union[str, Sequence[str], None] = '999c5f0d00a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE owner_apple_credentials "
        "ADD COLUMN include_family_devices BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE owner_apple_credentials DROP COLUMN include_family_devices")
