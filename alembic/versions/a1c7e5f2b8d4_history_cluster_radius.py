"""history cluster radius

Revision ID: a1c7e5f2b8d4
Revises: b4d9f61a2c83
Create Date: 2026-09-14 00:00:00.000000

Supports collapsing consecutive same-spot reports/owner-locations into one
"stay" entry in the history list and map (see movement.py's stillstand-anchor
idea, reused client-side for this) - a dedicated setting rather than reusing
movement_distance_threshold_meters, since "same spot for display" and "moved
significantly enough to alert" are different questions with different
natural values.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c7e5f2b8d4'
down_revision: Union[str, Sequence[str], None] = 'b4d9f61a2c83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE settings ADD COLUMN history_cluster_radius_meters DOUBLE PRECISION NOT NULL DEFAULT 50"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE settings DROP COLUMN history_cluster_radius_meters")
