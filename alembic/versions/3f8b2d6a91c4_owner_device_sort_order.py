"""owner device sort order

Revision ID: 3f8b2d6a91c4
Revises: 107c522e9374
Create Date: 2026-09-17 00:00:00.000000

Lets Objekte's device list be manually reordered - previously it was always
alphabetical-by-name (list_owner_devices' own ORDER BY) with the primary
device pinned first on top of that, client-side in ObjectsList.tsx, with no
way for the user to otherwise control it. Existing rows all default to 0, so
the new `ORDER BY sort_order, name` falls back to today's alphabetical order
until a device is actually reordered - no backfill needed.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3f8b2d6a91c4'
down_revision: Union[str, Sequence[str], None] = '107c522e9374'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE owner_devices ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE owner_devices DROP COLUMN sort_order")
