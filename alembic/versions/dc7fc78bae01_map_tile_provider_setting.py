"""map tile provider setting

Revision ID: dc7fc78bae01
Revises: 74c3d6026df7
Create Date: 2026-09-17T10:00:00.000000

Lets the map tile style (mapTiles.ts) be an explicit dashboard setting,
alongside color_palette - 'auto' keeps the existing behavior (CARTO
Voyager/Dark Matter when an API key is configured, plain OSM otherwise),
'osm' forces plain OSM tiles even with a key configured, for anyone who
doesn't like the CARTO look. Defaults to 'auto' (the pre-existing behavior).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'dc7fc78bae01'
down_revision: Union[str, Sequence[str], None] = '74c3d6026df7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE settings ADD COLUMN map_tile_provider TEXT NOT NULL DEFAULT 'auto' "
        "CHECK (map_tile_provider IN ('auto', 'osm'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE settings DROP COLUMN map_tile_provider")
