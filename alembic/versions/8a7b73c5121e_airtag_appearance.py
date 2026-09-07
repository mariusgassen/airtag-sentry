"""airtag appearance (icon + color)

Revision ID: 8a7b73c5121e
Revises: 2498586179a9
Create Date: 2026-09-07 00:00:00.000000

Adds per-AirTag `icon`/`color` customization, nullable so existing rows
(and any AirTag that's never been customized) keep today's behavior: a
NULL value means "derive it" (fixed ring glyph, hash-of-id color from
`airtagColor.ts`) rather than something that needs backfilling.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8a7b73c5121e'
down_revision: Union[str, Sequence[str], None] = '2498586179a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE airtags ADD COLUMN icon TEXT, ADD COLUMN color TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE airtags DROP COLUMN icon, DROP COLUMN color")
