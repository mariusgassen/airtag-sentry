"""owner apple credentials

Revision ID: 2498586179a9
Revises: cadd4e0af38f
Create Date: 2026-09-06 12:30:00.000000

Moves the owner-tracking Apple ID password out of plaintext .env
(APPLE_OWNER_ID/APPLE_OWNER_PASSWORD, introduced one migration ago) into an
encrypted Postgres column, entered via a dashboard login flow instead of a
CLI command - same treatment AirTag keys already got in an earlier
migration (see airtag_keys), and for the same reason: pyicloud has no
"resume from a session token alone" mode like FindMy.py does, so the
password must remain available to every poll indefinitely, not just at
login time. Single-row table (row absence = "not connected"), same shape
as airtag_keys rather than the always-present settings singleton.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2498586179a9'
down_revision: Union[str, Sequence[str], None] = 'cadd4e0af38f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE owner_apple_credentials (
            id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            apple_id TEXT NOT NULL,
            encrypted_password TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS owner_apple_credentials")
