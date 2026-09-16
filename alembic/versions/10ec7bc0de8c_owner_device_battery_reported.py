"""owner device battery reported flag

Revision ID: 10ec7bc0de8c
Revises: f8a3c1d92e57
Create Date: 2026-09-15 00:00:00.000000

record_owner_device_location (db.py) carries the previous battery_level/
battery_status forward onto a new location when the poll that produced it
didn't include a fresh reading (Apple's batteryStatus "Unknown", or a
device that just doesn't report battery at all) - otherwise the dashboard's
battery display would blank out until the next successful reading. That's
the right *display* behavior, but it overwrites the raw provenance: reading
battery_level back off a row no longer tells you whether Apple actually
reported a value for that specific fix, or whether it's inherited from an
earlier one. battery_reported records that provenance directly, so a later
feature (e.g. a battery-over-time chart) can tell a real reading from a
carried-forward gap-fill instead of just seeing an unbroken line of values.

Defaults to false for both new inserts (set explicitly by
record_owner_device_location) and existing rows - the carry-forward logic
is new as of this same change, so no historical row can be said to
definitely hold a fresh reading rather than an inherited or absent one.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '10ec7bc0de8c'
down_revision: Union[str, Sequence[str], None] = 'f8a3c1d92e57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE owner_device_locations "
        "ADD COLUMN battery_reported BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE owner_device_locations DROP COLUMN battery_reported")
