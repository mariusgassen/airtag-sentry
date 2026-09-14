"""color palette setting

Revision ID: f8a3c1d92e57
Revises: a1c7e5f2b8d4
Create Date: 2026-09-14 00:00:00.000000

Lets the badge/pin color palette (airtagColor.ts's PALETTE, shared by every
AirTag and owner device) be a dashboard setting instead of a hardcoded
constant - some users want the saturated iOS system colors, others prefer a
softer pastel set. Defaults to 'pastel' per user preference.

'pastel' pairs the soft backgrounds with a dark glyph (better contrast than
white on a light background); 'pastel_white' keeps the same backgrounds but
a white glyph instead, for anyone who prefers that look. Three values
because those are the two real "does the pastel look good" tradeoffs, not
because color/glyph are independent settings.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f8a3c1d92e57'
down_revision: Union[str, Sequence[str], None] = 'a1c7e5f2b8d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE settings ADD COLUMN color_palette TEXT NOT NULL DEFAULT 'pastel' "
        "CHECK (color_palette IN ('vivid', 'pastel', 'pastel_white'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE settings DROP COLUMN color_palette")
