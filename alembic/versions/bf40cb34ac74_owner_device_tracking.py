"""owner device tracking

Revision ID: bf40cb34ac74
Revises: 2498586179a9
Create Date: 2026-09-07 18:00:00.000000

Generalizes owner-device tracking from a single unnamed device (whichever
one `api.devices` happened to return a location for first) into a proper
registry of named devices the user explicitly opts into tracking, each
with its own history. See owner_tracking.py for the full rationale -
`owner_locations` never actually recorded anything usable (a pyicloud API
mismatch made every fetch silently fail), so there's no real data to
preserve here; breaking change, no back-compat shim, per CLAUDE.md's
established convention.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'bf40cb34ac74'
down_revision: Union[str, Sequence[str], None] = '2498586179a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS owner_locations")
    op.execute(
        """
        CREATE TABLE owner_devices (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            device_type TEXT NOT NULL DEFAULT '',
            enabled BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE owner_device_locations (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            device_id TEXT NOT NULL REFERENCES owner_devices(id) ON DELETE CASCADE,
            recorded_at TIMESTAMPTZ NOT NULL,
            lat DOUBLE PRECISION NOT NULL,
            lon DOUBLE PRECISION NOT NULL,
            horizontal_accuracy DOUBLE PRECISION
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_owner_device_locations_device_recorded "
        "ON owner_device_locations (device_id, recorded_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS owner_device_locations")
    op.execute("DROP TABLE IF EXISTS owner_devices")
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
