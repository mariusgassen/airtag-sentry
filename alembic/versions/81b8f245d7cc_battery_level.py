"""battery level

Revision ID: 81b8f245d7cc
Revises: 7c1e2b6a4f0d
Create Date: 2026-09-10 00:00:00.000000

Adds battery surfacing for both AirTags and owner devices (see
CLAUDE.md's parity constraint). The two sides encode battery differently
at the source, so they get differently-typed columns instead of a shared
name: FindMy.py's LocationReport.status only exposes a qualitative 2-bit
reading ("full"/"medium"/"low"/"very_low", decoded in tracker.py), while
pyicloud's AppleDevice exposes an exact 0.0-1.0 fraction plus a separate
charging-state string. All nullable - existing rows, and any future
report a battery-less source doesn't provide, just mean "unknown".
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '81b8f245d7cc'
down_revision: Union[str, Sequence[str], None] = '7c1e2b6a4f0d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE location_reports ADD COLUMN battery_level TEXT")
    op.execute(
        "ALTER TABLE owner_device_locations "
        "ADD COLUMN battery_level DOUBLE PRECISION, "
        "ADD COLUMN battery_status TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE location_reports DROP COLUMN battery_level")
    op.execute(
        "ALTER TABLE owner_device_locations DROP COLUMN battery_level, DROP COLUMN battery_status"
    )
