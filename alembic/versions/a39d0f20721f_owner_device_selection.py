"""owner device selection

Revision ID: a39d0f20721f
Revises: 8a7b73c5121e
Create Date: 2026-09-07 17:23:58.475470

owner_tracking.py's fetch_owner_location() used to just return whichever
device on the connected Apple account answered first with a location -
not deterministic, and not something the user could choose. This adds an
explicit pick: both the device id (to match against on every poll) and its
display name (so the dashboard can show "Verbunden · <name>" without an
extra Apple login just to resolve a label). Both nullable - absence means
"connected but no device chosen yet", which fetch_owner_location() now
treats as "nothing to fetch" rather than falling back to the old
first-responder behavior.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a39d0f20721f'
down_revision: Union[str, Sequence[str], None] = '8a7b73c5121e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE owner_apple_credentials
            ADD COLUMN selected_device_id TEXT,
            ADD COLUMN selected_device_name TEXT
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE owner_apple_credentials
            DROP COLUMN selected_device_id,
            DROP COLUMN selected_device_name
        """
    )
