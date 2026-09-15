"""per-reason notification toggles

Revision ID: b2e91f4a7c56
Revises: f8a3c1d92e57
Create Date: 2026-09-16T08:00:00.000000

Splits "was this recorded as an alert" from "should this send a
notification": the alerts table/Verlauf keeps recording every reason
unconditionally, but Telegram/push dispatch (tracker.py) now checks one of
these three switches per alert reason first. Defaults to TRUE (matches the
always-notify behavior every existing deployment already has) - the point
is to let someone turn plain `distance_threshold` notifications off (it
fires on every trip with no owner-absence signal at all) while keeping
`moved_without_owner` on, not to change anyone's alerts silently on
upgrade.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2e91f4a7c56'
down_revision: Union[str, Sequence[str], None] = 'f8a3c1d92e57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE settings
            ADD COLUMN notify_on_distance_threshold BOOLEAN NOT NULL DEFAULT true,
            ADD COLUMN notify_on_stillstand_movement BOOLEAN NOT NULL DEFAULT true,
            ADD COLUMN notify_on_moved_without_owner BOOLEAN NOT NULL DEFAULT true
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE settings
            DROP COLUMN notify_on_distance_threshold,
            DROP COLUMN notify_on_stillstand_movement,
            DROP COLUMN notify_on_moved_without_owner
        """
    )
