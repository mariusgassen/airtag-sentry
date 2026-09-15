"""geocoded points and place label corrections

Revision ID: d7b3e6a04f21
Revises: c4f8a2d91e56
Create Date: 2026-09-15 00:05:00.000000

Replaces geocode.py's in-memory `_cache` dict with a persisted table
populated by the poller (tracker.py) instead of lazily at render time - see
docs/superpowers/specs/2026-09-14-named-places-design.md. Both tables are
keyed by the same ~1m-precision rounded coordinate (see db.round_coord) so a
correction overrides exactly the same lookup the geocode cache uses.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7b3e6a04f21'
down_revision: Union[str, Sequence[str], None] = 'c4f8a2d91e56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE geocoded_points (
            lat_rounded DOUBLE PRECISION NOT NULL,
            lon_rounded DOUBLE PRECISION NOT NULL,
            address TEXT,
            poi_name TEXT,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (lat_rounded, lon_rounded)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE place_label_corrections (
            lat_rounded DOUBLE PRECISION NOT NULL,
            lon_rounded DOUBLE PRECISION NOT NULL,
            corrected_name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (lat_rounded, lon_rounded)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS place_label_corrections")
    op.execute("DROP TABLE IF EXISTS geocoded_points")
