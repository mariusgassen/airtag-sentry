"""Ordered schema migrations, each applied at most once per database and
recorded in schema_migrations so history is auditable (`SELECT * FROM
schema_migrations ORDER BY applied_at`).

Never edit a migration that has already shipped - add a new one instead, the
same way you would in any other migration-based project. Fresh installs and
upgrades both replay the exact same history in order, so there's only one
code path to trust.
"""

from __future__ import annotations

MIGRATIONS: list[tuple[str, str]] = [
    (
        "0001_initial_schema",
        """
        CREATE TABLE IF NOT EXISTS location_reports (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            "timestamp" TIMESTAMPTZ NOT NULL UNIQUE,
            lat DOUBLE PRECISION NOT NULL,
            lon DOUBLE PRECISION NOT NULL,
            accuracy DOUBLE PRECISION,
            confidence SMALLINT,
            source TEXT NOT NULL DEFAULT 'findmy',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_location_reports_timestamp ON location_reports ("timestamp");

        CREATE TABLE IF NOT EXISTS alerts (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            "timestamp" TIMESTAMPTZ NOT NULL DEFAULT now(),
            reason TEXT NOT NULL,
            distance_meters DOUBLE PRECISION NOT NULL,
            report_id BIGINT NOT NULL REFERENCES location_reports(id)
        );

        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,
    ),
    (
        "0002_multi_airtag",
        """
        ALTER TABLE location_reports ADD COLUMN IF NOT EXISTS airtag_id TEXT NOT NULL DEFAULT 'default';
        ALTER TABLE location_reports ALTER COLUMN airtag_id DROP DEFAULT;
        ALTER TABLE location_reports DROP CONSTRAINT IF EXISTS location_reports_timestamp_key;
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'location_reports_airtag_timestamp_key'
            ) THEN
                ALTER TABLE location_reports
                    ADD CONSTRAINT location_reports_airtag_timestamp_key UNIQUE (airtag_id, "timestamp");
            END IF;
        END $$;

        ALTER TABLE alerts ADD COLUMN IF NOT EXISTS airtag_id TEXT NOT NULL DEFAULT 'default';
        ALTER TABLE alerts ALTER COLUMN airtag_id DROP DEFAULT;

        CREATE INDEX IF NOT EXISTS idx_location_reports_airtag_timestamp ON location_reports (airtag_id, "timestamp");
        CREATE INDEX IF NOT EXISTS idx_alerts_airtag_timestamp ON alerts (airtag_id, "timestamp");
        """,
    ),
    (
        "0003_airtag_keys",
        """
        CREATE TABLE IF NOT EXISTS airtag_keys (
            airtag_id TEXT PRIMARY KEY,
            key_type TEXT NOT NULL,
            encrypted_data TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,
    ),
]
