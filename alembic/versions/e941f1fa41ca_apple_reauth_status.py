"""apple reauth status

Revision ID: e941f1fa41ca
Revises: b4d2e8f1a367
Create Date: 2026-11-14 18:37:57.307821

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e941f1fa41ca'
down_revision: Union[str, Sequence[str], None] = 'b4d2e8f1a367'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE owner_apple_credentials ADD COLUMN reauth_required BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute(
        """
        CREATE TABLE airtag_apple_sync_status (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_sync_at TIMESTAMPTZ,
            last_sync_error TEXT,
            reauth_required BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE airtag_apple_sync_status")
    op.execute("ALTER TABLE owner_apple_credentials DROP COLUMN reauth_required")
