"""airtag enabled flag

Revision ID: b4d2e8f1a367
Revises: a7e2d94c1b60
Create Date: 2026-10-02 00:00:00.000000

Lets an AirTag be hidden (not polled, not listed) without deleting it or its
key/history - mirrors owner_devices.enabled. Existing rows stay enabled.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b4d2e8f1a367'
down_revision: Union[str, Sequence[str], None] = 'a7e2d94c1b60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE airtags ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT TRUE")


def downgrade() -> None:
    op.execute("ALTER TABLE airtags DROP COLUMN enabled")
