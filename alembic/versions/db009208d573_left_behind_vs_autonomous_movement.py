"""left behind vs autonomous movement

Revision ID: db009208d573
Revises: 51c3aeb246e0
Create Date: 2026-09-17 22:15:00.000000

Splits the single "moved_without_owner" away alert into two distinct
reasons - see CLAUDE.md's "you left it" vs "it left you" constraint:
"left_behind" (the object stayed put, you moved away from it - routine)
and "autonomous_movement" (the object itself moved without you - the
actual signal this app exists to catch). notify_on_moved_without_owner
becomes two independently toggleable settings so one can be silenced
without silencing the other.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'db009208d573'
down_revision: Union[str, Sequence[str], None] = '51c3aeb246e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE settings
            ADD COLUMN notify_on_left_behind BOOLEAN NOT NULL DEFAULT true,
            ADD COLUMN notify_on_autonomous_movement BOOLEAN NOT NULL DEFAULT true,
            DROP COLUMN notify_on_moved_without_owner
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE settings
            ADD COLUMN notify_on_moved_without_owner BOOLEAN NOT NULL DEFAULT true,
            DROP COLUMN notify_on_left_behind,
            DROP COLUMN notify_on_autonomous_movement
        """
    )
