"""merge named places and settings heads

Revision ID: 107c522e9374
Revises: b2e91f4a7c56, d7b3e6a04f21
Create Date: 2026-09-16 00:00:00.000000

Named places (c4f8a2d91e56/d7b3e6a04f21) and the color-palette/battery-
reported/notify-on-reason settings work (f8a3c1d92e57/10ec7bc0de8c/
b2e91f4a7c56) both branched off history_cluster_radius (a1c7e5f2b8d4)
independently - this just joins the two heads back into one, no schema
change of its own.
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '107c522e9374'
down_revision: Union[str, Sequence[str], None] = ('b2e91f4a7c56', 'd7b3e6a04f21')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
