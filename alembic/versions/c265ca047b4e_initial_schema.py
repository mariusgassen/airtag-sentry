"""initial schema

Revision ID: c265ca047b4e
Revises:
Create Date: 2026-09-04 23:44:08.732545

Still in early development with no real deployed data to preserve, so this
is one clean schema rather than a replayed history of incremental changes -
no backward-compatibility guards needed. Once this ships to a real user,
future schema changes get their own migration instead of editing this one.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c265ca047b4e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE airtags (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE location_reports (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            airtag_id TEXT NOT NULL REFERENCES airtags(id) ON DELETE CASCADE,
            "timestamp" TIMESTAMPTZ NOT NULL,
            lat DOUBLE PRECISION NOT NULL,
            lon DOUBLE PRECISION NOT NULL,
            accuracy DOUBLE PRECISION,
            confidence SMALLINT,
            source TEXT NOT NULL DEFAULT 'findmy',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (airtag_id, "timestamp")
        )
        """
    )
    op.execute(
        'CREATE INDEX idx_location_reports_timestamp ON location_reports ("timestamp")'
    )
    op.execute(
        'CREATE INDEX idx_location_reports_airtag_timestamp ON location_reports (airtag_id, "timestamp")'
    )
    op.execute(
        """
        CREATE TABLE alerts (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            airtag_id TEXT NOT NULL REFERENCES airtags(id) ON DELETE CASCADE,
            "timestamp" TIMESTAMPTZ NOT NULL DEFAULT now(),
            reason TEXT NOT NULL,
            distance_meters DOUBLE PRECISION NOT NULL,
            report_id BIGINT NOT NULL REFERENCES location_reports(id)
        )
        """
    )
    op.execute('CREATE INDEX idx_alerts_airtag_timestamp ON alerts (airtag_id, "timestamp")')
    op.execute(
        """
        CREATE TABLE push_subscriptions (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE airtag_keys (
            airtag_id TEXT PRIMARY KEY REFERENCES airtags(id) ON DELETE CASCADE,
            key_type TEXT NOT NULL,
            encrypted_data TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS airtag_keys")
    op.execute("DROP TABLE IF EXISTS push_subscriptions")
    op.execute("DROP TABLE IF EXISTS alerts")
    op.execute("DROP TABLE IF EXISTS location_reports")
    op.execute("DROP TABLE IF EXISTS airtags")
