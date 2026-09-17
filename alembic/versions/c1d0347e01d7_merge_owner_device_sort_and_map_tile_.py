"""merge owner-device-sort-order/carto-settings and map-tile-provider heads

Revision ID: c1d0347e01d7
Revises: 8c1f2e6b4a97, dc7fc78bae01
Create Date: 2026-09-17 09:45:00.000000

map_tile_provider (dc7fc78bae01) branched off 74c3d6026df7 (carto_settings)
independently of 8c1f2e6b4a97 (which already joined carto_settings back
together with the owner-device sort-order branch) - this just joins the two
remaining heads back into one, no schema change of its own.
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'c1d0347e01d7'
down_revision: Union[str, Sequence[str], None] = ('8c1f2e6b4a97', 'dc7fc78bae01')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
