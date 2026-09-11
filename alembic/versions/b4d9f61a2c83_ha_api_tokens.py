"""ha api tokens

Revision ID: b4d9f61a2c83
Revises: e7c1b3a92f04
Create Date: 2026-09-11 14:00:00.000000

Bearer token for GET /api/ha/state (see web/app.py, notifiers/homeassistant.py's
module docstring) - lets a cloud-hosted AirTag Sentry be *polled* by a
local-only Home Assistant instead of requiring AirTag Sentry to reach a
broker/HA that has no inbound access of its own. Complements, doesn't
replace, the MQTT Discovery publisher added by e7c1b3a92f04, which is still
the better fit when both run on the same network.

Stores a hash, not an encrypted token, since the plaintext is never needed
back - only comparison against a presented bearer token.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b4d9f61a2c83'
down_revision: Union[str, Sequence[str], None] = 'e7c1b3a92f04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ha_api_tokens (
            id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            token_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ha_api_tokens")
