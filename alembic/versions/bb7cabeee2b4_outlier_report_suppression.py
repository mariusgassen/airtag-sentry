"""outlier report suppression

Revision ID: bb7cabeee2b4
Revises: e1a9c3f7b524
Create Date: 2026-09-17 21:00:00.000000

Crowd-sourced AirTag fixes can occasionally jump far off the real path (a
bad Bluetooth relay, not real movement) - flag reports whose implied travel
speed from the prior kept report is physically implausible so they're
excluded from the map trail/stays and never evaluated for movement alerts,
instead of distorting both. `movement_max_speed_kmh` is the tunable
threshold (see movement.py's is_speed_outlier).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'bb7cabeee2b4'
down_revision: Union[str, Sequence[str], None] = 'e1a9c3f7b524'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE location_reports ADD COLUMN is_outlier BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE settings ADD COLUMN movement_max_speed_kmh DOUBLE PRECISION NOT NULL DEFAULT 200"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE settings DROP COLUMN movement_max_speed_kmh")
    op.execute("ALTER TABLE location_reports DROP COLUMN is_outlier")
