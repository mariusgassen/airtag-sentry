"""carto settings

Revision ID: 74c3d6026df7
Revises: 107c522e9374
Create Date: 2026-09-17T08:10:00.000000

CARTO's raster basemap tiles (used for the light/dark map style, see
MapCard.tsx's AppTileLayer) now require a free API key - anonymous requests
get a watermarked tile instead. Same encrypted-at-rest treatment as the
Telegram bot token/MQTT password (see telegram_settings/mqtt_settings),
entered via the dashboard's Settings panel. Single-row table (row absence =
"not configured", falls back to plain OSM tiles - see AppTileLayer).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '74c3d6026df7'
down_revision: Union[str, Sequence[str], None] = '107c522e9374'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE carto_settings (
            id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            api_key_encrypted TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS carto_settings")
