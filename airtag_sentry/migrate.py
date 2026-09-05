"""Runs Alembic migrations to head. Called once at process startup by each
CLI subcommand (poll/run/serve) - not per-request, unlike the old hand-rolled
migration tracker this replaced.

Resolves alembic.ini relative to the current working directory, the same
convention .env already uses - this app is always run from its
project/deployment root (see Dockerfile's WORKDIR).
"""

from __future__ import annotations

from alembic import command
from alembic.config import Config as AlembicConfig


def upgrade_to_head() -> None:
    alembic_cfg = AlembicConfig("alembic.ini")
    command.upgrade(alembic_cfg, "head")
