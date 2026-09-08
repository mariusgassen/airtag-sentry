"""owner device display name + appearance (icon + color)

Revision ID: d4f19a6e3b2c
Revises: 9d21b6f4a7c3
Create Date: 2026-09-08 00:00:00.000000

Adds per-device `display_name`/`icon`/`color` customization, mirroring
8a7b73c5121e's AirTag appearance columns. All nullable: `icon`/`color`
follow the same "NULL = derive it" convention as AirTags, and `display_name`
NULL means "show the Apple-synced technical name" (`owner_devices.name`,
which `upsert_owner_devices` keeps refreshing from Apple on every live
listing - `display_name` is the one column that refresh never touches, so a
user-chosen name survives it).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4f19a6e3b2c'
down_revision: Union[str, Sequence[str], None] = '9d21b6f4a7c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE owner_devices ADD COLUMN display_name TEXT, ADD COLUMN icon TEXT, ADD COLUMN color TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE owner_devices DROP COLUMN display_name, DROP COLUMN icon, DROP COLUMN color")
