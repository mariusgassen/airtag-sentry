"""airtag sort order

Revision ID: e1a9c3f7b524
Revises: c1d0347e01d7
Create Date: 2026-09-17 00:00:00.000000

Owner devices got manual reordering in 3f8b2d6a91c4 but AirTags never did -
CLAUDE.md's AirTag/owner-device parity rule says that's a gap, not a design
choice. Existing rows all default to 0, so the new `ORDER BY sort_order,
created_at` falls back to today's creation order until an AirTag is actually
reordered - no backfill needed.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e1a9c3f7b524'
down_revision: Union[str, Sequence[str], None] = 'c1d0347e01d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE airtags ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE airtags DROP COLUMN sort_order")
