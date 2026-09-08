"""telegram bot commands

Revision ID: 9d21b6f4a7c3
Revises: f3a4c8e1d9b2
Create Date: 2026-09-08 09:00:00.000000

Adds inbound Telegram bot-commands support on top of the existing outbound-only
telegram_settings row: whether the webhook is enabled, and the random anti-spoofing
token handed to Telegram's setWebhook (compared against the
X-Telegram-Bot-Api-Secret-Token header on every inbound request) - not user secret
material, so unlike bot_token_encrypted this is stored in plaintext.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9d21b6f4a7c3'
down_revision: Union[str, Sequence[str], None] = 'f3a4c8e1d9b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE telegram_settings
            ADD COLUMN bot_commands_enabled BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN webhook_secret TEXT
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE telegram_settings
            DROP COLUMN bot_commands_enabled,
            DROP COLUMN webhook_secret
        """
    )
