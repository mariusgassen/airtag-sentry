"""owner device tracking

Revision ID: bf40cb34ac74
Revises: a39d0f20721f
Create Date: 2026-09-07 18:00:00.000000

Generalizes owner-device tracking from a single unnamed device (whichever
one `api.devices` happened to return a location for first) into a proper
registry of named devices the user explicitly opts into tracking, each
with its own history. See owner_tracking.py for the full rationale -
`owner_locations` never actually recorded anything usable (a pyicloud API
mismatch made every fetch silently fail), so there's no real data to
preserve here; breaking change, no back-compat shim, per CLAUDE.md's
established convention.

Supersedes a39d0f20721f's single `selected_device_id`/`_name` columns on
owner_apple_credentials with an `is_primary` flag on owner_devices instead:
exactly one tracked device can be primary (a partial unique index enforces
this), used for "moved without you" away-correlation and the map trail,
while every enabled device (primary or not) still gets its own history.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'bf40cb34ac74'
down_revision: Union[str, Sequence[str], None] = 'a39d0f20721f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS owner_locations")
    op.execute(
        """
        ALTER TABLE owner_apple_credentials
            DROP COLUMN IF EXISTS selected_device_id,
            DROP COLUMN IF EXISTS selected_device_name
        """
    )
    op.execute(
        """
        CREATE TABLE owner_devices (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            device_type TEXT NOT NULL DEFAULT '',
            enabled BOOLEAN NOT NULL DEFAULT false,
            is_primary BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        # At most one primary device at a time - a partial index rather than a
        # second table/column elsewhere keeps "exactly one or none" enforced by
        # Postgres itself instead of application code.
        "CREATE UNIQUE INDEX idx_owner_devices_primary ON owner_devices (is_primary) WHERE is_primary"
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
        ALTER TABLE owner_apple_credentials
            ADD COLUMN selected_device_id TEXT,
            ADD COLUMN selected_device_name TEXT
        """
    )
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
