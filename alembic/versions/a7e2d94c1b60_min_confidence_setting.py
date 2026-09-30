"""min confidence setting

Revision ID: a7e2d94c1b60
Revises: db009208d573
Create Date: 2026-09-30 12:00:00.000000

`movement_min_confidence` (FindMy.py's 1-3 report confidence): AirTag
reports below it are kept and displayed but never drive an alert (see
movement.is_low_confidence). 1 (the default) disables the filter.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7e2d94c1b60'
down_revision: Union[str, Sequence[str], None] = 'db009208d573'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE settings ADD COLUMN movement_min_confidence SMALLINT NOT NULL DEFAULT 1")


def downgrade() -> None:
    op.execute("ALTER TABLE settings DROP COLUMN movement_min_confidence")
