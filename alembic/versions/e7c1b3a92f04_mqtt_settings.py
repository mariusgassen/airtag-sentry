"""mqtt settings

Revision ID: e7c1b3a92f04
Revises: 81b8f245d7cc
Create Date: 2026-09-11 09:00:00.000000

Home Assistant MQTT Discovery publisher settings (see
notifiers/homeassistant.py): broker host/port/credentials, entered via the
dashboard's Settings panel, same encrypted-at-rest treatment as
telegram_settings.bot_token_encrypted. Single-row table (row absence = "not
configured").
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e7c1b3a92f04'
down_revision: Union[str, Sequence[str], None] = '81b8f245d7cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE mqtt_settings (
            id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            username TEXT,
            password_encrypted TEXT,
            use_tls BOOLEAN NOT NULL DEFAULT false,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mqtt_settings")
