"""webpush settings

Revision ID: c7d3f9a1e246
Revises: f8a3c1d92e57
Create Date: 2026-09-15 10:00:00.000000

Moves the Web Push VAPID keypair out of CLI-generated .env vars
(VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY/VAPID_SUBJECT, previously produced by
scripts/generate_vapid_keys.py) into Postgres - the keypair is now generated
automatically on first use and the private key encrypted at rest, same
treatment as telegram_settings.bot_token_encrypted. Single-row table (row
absence = "not generated yet").
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7d3f9a1e246'
down_revision: Union[str, Sequence[str], None] = 'f8a3c1d92e57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE webpush_settings (
            id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            public_key TEXT NOT NULL,
            private_key_encrypted TEXT NOT NULL,
            subject TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS webpush_settings")
