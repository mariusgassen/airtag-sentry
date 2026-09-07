"""telegram settings

Revision ID: f3a4c8e1d9b2
Revises: bf40cb34ac74
Create Date: 2026-09-07 09:00:00.000000

Moves Telegram notifications out of plaintext .env (TELEGRAM_BOT_TOKEN/
TELEGRAM_CHAT_ID) into the dashboard's Settings panel, encrypted at rest in
Postgres - same treatment owner-tracking's Apple password already got (see
owner_apple_credentials). Single-row table (row absence = "not configured"),
same shape as owner_apple_credentials.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3a4c8e1d9b2'
down_revision: Union[str, Sequence[str], None] = 'bf40cb34ac74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE telegram_settings (
            id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            bot_token_encrypted TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS telegram_settings")
