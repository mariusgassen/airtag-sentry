"""merge sort order and carto settings heads

Revision ID: 8c1f2e6b4a97
Revises: 3f8b2d6a91c4, 74c3d6026df7
Create Date: 2026-09-17 00:00:00.000000

Owner-device sort order (3f8b2d6a91c4) and CARTO settings (74c3d6026df7)
both branched off 107c522e9374 independently - this just joins the two
heads back into one, no schema change of its own.
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '8c1f2e6b4a97'
down_revision: Union[str, Sequence[str], None] = ('3f8b2d6a91c4', '74c3d6026df7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
