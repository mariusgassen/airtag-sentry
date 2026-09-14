"""named places

Revision ID: c4f8a2d91e56
Revises: a1c7e5f2b8d4
Create Date: 2026-09-15 00:00:00.000000

User-defined circular geofences ("Home", "Office") - see
docs/superpowers/specs/2026-09-14-named-places-design.md. Global, not
per-device: a place is a physical location, meaningful regardless of which
AirTag/owner device visits it (single-user app, see CLAUDE.md).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4f8a2d91e56'
down_revision: Union[str, Sequence[str], None] = 'a1c7e5f2b8d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE named_places (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name TEXT NOT NULL,
            lat DOUBLE PRECISION NOT NULL,
            lon DOUBLE PRECISION NOT NULL,
            radius_meters DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS named_places")
