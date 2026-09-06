"""owner location tracking

Revision ID: cadd4e0af38f
Revises: 64b29b812664
Create Date: 2026-09-06 12:00:00.000000

Supports the "moved without you" alert correlation: the owner's own device
location (fetched via a separate Apple Find My iPhone session, see
owner_tracking.py) is recorded each poll so a movement alert can check
whether the AirTag's new position is far from where the owner actually was.
Append-only history table (no dedup needed - one row per poll) plus two new
tunable settings alongside the existing movement thresholds.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'cadd4e0af38f'
down_revision: Union[str, Sequence[str], None] = '64b29b812664'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE owner_locations (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            recorded_at TIMESTAMPTZ NOT NULL,
            lat DOUBLE PRECISION NOT NULL,
            lon DOUBLE PRECISION NOT NULL,
            horizontal_accuracy DOUBLE PRECISION
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_owner_locations_recorded_at ON owner_locations (recorded_at DESC)"
    )
    op.execute(
        """
        ALTER TABLE settings
            ADD COLUMN movement_away_distance_meters DOUBLE PRECISION NOT NULL DEFAULT 150,
            ADD COLUMN owner_location_max_age_minutes DOUBLE PRECISION NOT NULL DEFAULT 60
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE settings
            DROP COLUMN movement_away_distance_meters,
            DROP COLUMN owner_location_max_age_minutes
        """
    )
    op.execute("DROP TABLE IF EXISTS owner_locations")
