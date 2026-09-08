"""owner device sync status (last seen, last sync error)

Revision ID: 999c5f0d00a3
Revises: d4f19a6e3b2c
Create Date: 2026-09-08 12:00:00.000000

A persisted device could silently go stale with no visible signal why: a
device removed from the owner's iCloud account (Find My unenrolled, device
signed out) just stopped getting refreshed by upsert_owner_devices, and a
lapsed pyicloud session or a transient Apple/network error was only ever
logged, never surfaced to the dashboard - both looked identical to "not
polled yet" from the UI's point of view.

`owner_devices.last_seen_at`: set to the poll's timestamp every time this
device appears in a *successful* Apple device listing (fetch_owner_device_
locations upserts every device it sees, not just enabled ones - see
tasks/todo.md). `owner_apple_credentials.last_sync_at`/`last_sync_error`:
set on every *attempted* live listing, success or failure - `last_sync_at`
always advances, `last_sync_error` holds the exception message on failure
and is cleared on the next success. Comparing a device's `last_seen_at`
against the credentials' `last_sync_at` (same poll's timestamp, so an exact
match rather than a fuzzy age check) tells the dashboard whether a device
was actually present in the most recent successful sync.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '999c5f0d00a3'
down_revision: Union[str, Sequence[str], None] = 'd4f19a6e3b2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE owner_devices ADD COLUMN last_seen_at TIMESTAMPTZ")
    op.execute(
        "ALTER TABLE owner_apple_credentials "
        "ADD COLUMN last_sync_at TIMESTAMPTZ, ADD COLUMN last_sync_error TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE owner_devices DROP COLUMN last_seen_at")
    op.execute(
        "ALTER TABLE owner_apple_credentials DROP COLUMN last_sync_at, DROP COLUMN last_sync_error"
    )
