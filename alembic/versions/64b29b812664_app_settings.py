"""app settings

Revision ID: 64b29b812664
Revises: c265ca047b4e
Create Date: 2026-09-05 09:30:00.000000

Polling interval and movement thresholds used to be env vars
(POLLING_INTERVAL_MINUTES, MOVEMENT_*). Moving them into the database lets
the dashboard expose them as an editable setting instead of requiring a
redeploy, and lets the `app` scheduler process pick up a change without a
restart. Single-row table (`id` pinned to 1 via CHECK) since there is
exactly one set of these for the whole instance.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '64b29b812664'
down_revision: Union[str, Sequence[str], None] = 'c265ca047b4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE settings (
            id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            polling_interval_minutes INTEGER NOT NULL DEFAULT 15,
            movement_distance_threshold_meters DOUBLE PRECISION NOT NULL DEFAULT 100,
            movement_stillstand_hours DOUBLE PRECISION NOT NULL DEFAULT 24,
            movement_stillstand_movement_meters DOUBLE PRECISION NOT NULL DEFAULT 15,
            movement_alert_on_backfill BOOLEAN NOT NULL DEFAULT false,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("INSERT INTO settings (id) VALUES (1)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS settings")
