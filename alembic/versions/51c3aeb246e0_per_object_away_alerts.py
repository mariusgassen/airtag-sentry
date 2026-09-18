"""per-object away alerts

Revision ID: 51c3aeb246e0
Revises: bb7cabeee2b4
Create Date: 2026-09-17 21:30:00.000000

"You left without X" alerts, opt-in per object rather than the single
account-wide notify_on_moved_without_owner switch deciding for every
AirTag/device at once: an AirTag already got this alert unconditionally
(away_alert_enabled defaults true, preserving that), owner devices (a
laptop, AirPods) never did (defaults false - introducing this shouldn't
suddenly start alerting on every device in the account).

alerts becomes polymorphic to let a device trigger one too: airtag_id/
report_id are now nullable, and a new owner_device_id/owner_location_id
pair covers the device case - a CHECK enforces exactly one source per row.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '51c3aeb246e0'
down_revision: Union[str, Sequence[str], None] = 'bb7cabeee2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE airtags ADD COLUMN away_alert_enabled BOOLEAN NOT NULL DEFAULT true"
    )
    op.execute(
        "ALTER TABLE owner_devices ADD COLUMN away_alert_enabled BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        """
        ALTER TABLE alerts
            ALTER COLUMN airtag_id DROP NOT NULL,
            ALTER COLUMN report_id DROP NOT NULL,
            ADD COLUMN owner_device_id TEXT REFERENCES owner_devices(id) ON DELETE CASCADE,
            ADD COLUMN owner_location_id BIGINT REFERENCES owner_device_locations(id) ON DELETE CASCADE,
            ADD CONSTRAINT alerts_source_xor CHECK (
                (airtag_id IS NOT NULL AND report_id IS NOT NULL
                    AND owner_device_id IS NULL AND owner_location_id IS NULL)
                OR
                (owner_device_id IS NOT NULL AND owner_location_id IS NOT NULL
                    AND airtag_id IS NULL AND report_id IS NULL)
            )
        """
    )
    op.execute(
        "CREATE INDEX idx_alerts_owner_device_timestamp ON alerts (owner_device_id, \"timestamp\")"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_alerts_owner_device_timestamp")
    op.execute(
        """
        ALTER TABLE alerts
            DROP CONSTRAINT alerts_source_xor,
            DROP COLUMN owner_device_id,
            DROP COLUMN owner_location_id,
            ALTER COLUMN airtag_id SET NOT NULL,
            ALTER COLUMN report_id SET NOT NULL
        """
    )
    op.execute("ALTER TABLE owner_devices DROP COLUMN away_alert_enabled")
    op.execute("ALTER TABLE airtags DROP COLUMN away_alert_enabled")
