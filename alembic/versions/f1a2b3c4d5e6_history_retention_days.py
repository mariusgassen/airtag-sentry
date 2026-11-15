"""history retention days

Revision ID: f1a2b3c4d5e6
Revises: e941f1fa41ca
Create Date: 2026-11-15 12:00:00.000000

Adds nullable `history_retention_days` to `settings`. NULL keeps history
indefinitely (existing behavior); a positive integer configures automatic
pruning of older location reports, owner device locations, and alerts during
scheduled/manual polls.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e941f1fa41ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE settings ADD COLUMN history_retention_days INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE settings DROP COLUMN history_retention_days")
